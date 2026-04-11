"""Bearer authentication and auth context helpers for MemOS."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthIdentity:
    """Resolved identity for an API key."""

    name: str
    namespace: str = ""
    is_master: bool = False

    @property
    def permissions(self) -> list[str]:
        return ["read", "write", "admin"] if self.is_master else ["read", "write"]


@dataclass
class RateLimitEntry:
    """Tracks request counts per window."""

    count: int = 0
    window_start: float = 0.0


@dataclass
class RateLimiter:
    """Sliding-window rate limiter per API key."""

    max_requests: int = 100
    window_seconds: float = 60.0
    _counters: dict[str, RateLimitEntry] = field(default_factory=dict)

    def check(self, key: str) -> tuple[bool, dict[str, str]]:
        """Check if request is allowed. Returns (allowed, headers)."""
        now = time.time()
        entry = self._counters.get(key)

        if entry is None or (now - entry.window_start) >= self.window_seconds:
            self._counters[key] = RateLimitEntry(count=1, window_start=now)
            return True, self._headers(1, self.max_requests, key)

        entry.count += 1
        allowed = entry.count <= self.max_requests
        return allowed, self._headers(entry.count, self.max_requests, key)

    def _headers(self, current: int, limit: int, key: str) -> dict[str, str]:
        entry = self._counters[key]
        reset_at = entry.window_start + self.window_seconds
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, limit - current)),
            "X-RateLimit-Reset": str(int(reset_at)),
        }


class APIKeyManager:
    """Manages master and namespace-scoped API keys for MemOS."""

    def __init__(
        self,
        keys: Optional[list[str]] = None,
        *,
        master_key: Optional[str] = None,
        namespace_keys: Optional[dict[str, str]] = None,
    ):
        self._identities: dict[str, AuthIdentity] = {}
        self._key_names: dict[str, str] = {}
        self.rate_limiter = RateLimiter()

        for i, key in enumerate(keys or []):
            self.add_master_key(key, name=f"key-{i+1}")
        if master_key:
            self.add_master_key(master_key, name="master")
        for namespace, key in (namespace_keys or {}).items():
            if key:
                self.add_namespace_key(namespace=namespace, key=key)

    @classmethod
    def from_env(cls, *, keys: Optional[list[str]] = None) -> "APIKeyManager":
        import os

        master_key = os.environ.get("API_KEY") or None
        namespace_keys: dict[str, str] = {}
        raw_namespace_keys = os.environ.get("MEMOS_NAMESPACE_KEYS", "").strip()
        if raw_namespace_keys:
            try:
                parsed = json.loads(raw_namespace_keys)
                if isinstance(parsed, dict):
                    namespace_keys = {
                        str(namespace): str(key)
                        for namespace, key in parsed.items()
                        if namespace and key
                    }
                else:
                    logger.warning("MEMOS_NAMESPACE_KEYS must be a JSON object, got %s", type(parsed).__name__)
            except json.JSONDecodeError as exc:
                logger.warning("Failed to parse MEMOS_NAMESPACE_KEYS: %s", exc)

        return cls(keys=keys, master_key=master_key, namespace_keys=namespace_keys)

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def add_master_key(self, key: str, name: str = "master") -> str:
        hashed = self._hash_key(key)
        self._identities[hashed] = AuthIdentity(name=name, is_master=True)
        self._key_names[hashed] = name
        return hashed

    def add_namespace_key(self, namespace: str, key: str, name: str | None = None) -> str:
        hashed = self._hash_key(key)
        resolved_name = name or f"namespace:{namespace}"
        self._identities[hashed] = AuthIdentity(name=resolved_name, namespace=namespace)
        self._key_names[hashed] = resolved_name
        return hashed

    def add_key(self, key: str, name: str = "") -> str:
        """Backward-compatible alias for adding a master key."""
        return self.add_master_key(key, name=name or "master")

    def remove_key(self, key: str) -> bool:
        hashed = self._hash_key(key)
        self._identities.pop(hashed, None)
        self._key_names.pop(hashed, None)
        return True

    def authenticate(self, key: str) -> AuthIdentity | None:
        hashed = self._hash_key(key)
        identity = self._identities.get(hashed)
        if identity is None:
            return None
        return identity if hmac.compare_digest(hashed, self._hash_key(key)) else None

    def validate(self, key: str) -> bool:
        if not self._identities:
            return True
        return self.authenticate(key) is not None

    @property
    def auth_enabled(self) -> bool:
        return bool(self._identities)

    @property
    def key_count(self) -> int:
        return len(self._identities)

    @property
    def _hashed_keys(self) -> set[str]:
        return set(self._identities.keys())

    @property
    def namespace_key_count(self) -> int:
        return sum(1 for identity in self._identities.values() if not identity.is_master)

    @property
    def master_key_count(self) -> int:
        return sum(1 for identity in self._identities.values() if identity.is_master)


def _extract_api_key(request) -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.headers.get("X-API-Key", "").strip()


def create_auth_middleware(key_manager: APIKeyManager):
    """Create ASGI middleware for auth, namespace forcing, and rate limiting."""

    async def middleware(request, call_next):
        from starlette.responses import JSONResponse

        path = request.url.path
        if path in {"/", "/health", "/docs", "/openapi.json"}:
            return await call_next(request)

        if not key_manager.auth_enabled:
            request.state.auth_identity = AuthIdentity(name="anonymous", is_master=True)
            request.state.namespace = ""
            return await call_next(request)

        api_key = _extract_api_key(request)
        if not api_key:
            logger.warning("Missing API credentials for %s", path)
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "Missing Authorization: Bearer <key> header"},
            )

        identity = key_manager.authenticate(api_key)
        if identity is None:
            logger.warning("Invalid API credentials for %s", path)
            return JSONResponse(
                status_code=403,
                content={"status": "error", "message": "Invalid API key"},
            )

        allowed, headers = key_manager.rate_limiter.check(api_key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"status": "error", "message": "Rate limit exceeded"},
                headers=headers,
            )

        request.state.auth_identity = identity
        requested_namespace = request.headers.get("X-Memos-Namespace", "").strip()
        effective_namespace = requested_namespace if identity.is_master else identity.namespace
        request.state.namespace = effective_namespace

        memos = getattr(request.app.state, "memos", None)
        previous_namespace = getattr(memos, "namespace", "") if memos is not None else ""
        if memos is not None:
            memos.namespace = effective_namespace

        try:
            response = await call_next(request)
        finally:
            if memos is not None:
                memos.namespace = previous_namespace

        for key, value in headers.items():
            response.headers[key] = value
        response.headers["X-Memos-Auth-Mode"] = "master" if identity.is_master else "namespace"
        if effective_namespace:
            response.headers["X-Memos-Namespace"] = effective_namespace
        return response

    return middleware
