"""Authentication helpers for the MemOS REST API."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

_LOG = logging.getLogger("memos.api.auth")
_OPEN_PATHS = frozenset({"/", "/health", "/docs", "/openapi.json", "/redoc"})


@dataclass
class RateLimitEntry:
    """Tracks request counts per window."""

    count: int = 0
    window_start: float = 0.0


@dataclass
class RateLimiter:
    """Sliding-window rate limiter per API key.

    Kept for backward compatibility with the existing test surface.
    """

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


@dataclass(frozen=True)
class AuthContext:
    """Resolved identity for one API request."""

    mode: str
    token_name: str
    namespace: str | None = None
    permissions: tuple[str, ...] = ()
    source: str = "none"

    @property
    def is_master(self) -> bool:
        return self.mode in {"master", "open"}

    @property
    def rate_limit_key(self) -> str:
        if self.mode == "namespace" and self.namespace:
            return f"namespace:{self.namespace}"
        return self.token_name or self.mode

    @property
    def agent_id(self) -> str:
        if self.namespace:
            return self.namespace
        return self.token_name or self.mode

    def to_dict(self) -> dict[str, Any]:
        return {
            "auth_mode": self.mode,
            "token_name": self.token_name,
            "namespace": self.namespace,
            "permissions": list(self.permissions),
            "source": self.source,
        }


class APIKeyManager:
    """Manages master and per-namespace API keys for MemOS authentication."""

    def __init__(
        self,
        keys: Optional[list[str]] = None,
        *,
        master_key: str | None = None,
        namespace_keys: dict[str, str] | None = None,
    ):
        self._master_keys: dict[str, str] = {}
        self._namespace_keys: dict[str, str] = {}
        self.rate_limiter = RateLimiter()

        if keys:
            for i, key in enumerate(keys):
                self.add_key(key, name=f"key-{i + 1}")
        if master_key:
            self.add_master_key(master_key, name="master")
        for namespace, key in (namespace_keys or {}).items():
            self.add_namespace_key(namespace, key)

    @classmethod
    def from_env(cls) -> "APIKeyManager":
        master_key = os.environ.get("API_KEY") or os.environ.get("MEMOS_API_KEY")
        raw_namespace_keys = os.environ.get("MEMOS_NAMESPACE_KEYS", "").strip()
        namespace_keys: dict[str, str] = {}
        if raw_namespace_keys:
            try:
                payload = json.loads(raw_namespace_keys)
            except json.JSONDecodeError as exc:
                raise ValueError("MEMOS_NAMESPACE_KEYS must be valid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("MEMOS_NAMESPACE_KEYS must be a JSON object")
            namespace_keys = {}
            for namespace, key in payload.items():
                if not isinstance(namespace, str) or not namespace.strip():
                    raise ValueError("MEMOS_NAMESPACE_KEYS keys must be non-empty strings")
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(
                        f"MEMOS_NAMESPACE_KEYS[{namespace!r}] must be a non-empty string"
                    )
                namespace_keys[namespace.strip()] = key.strip()
        return cls(master_key=master_key, namespace_keys=namespace_keys)

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def add_key(self, key: str, name: str = "") -> str:
        """Backward-compatible alias for adding a master key."""
        return self.add_master_key(key, name=name or "master")

    def add_master_key(self, key: str, name: str = "master") -> str:
        hashed = self._hash_key(key)
        self._master_keys[hashed] = name or "master"
        return hashed

    def add_namespace_key(self, namespace: str, key: str) -> str:
        hashed = self._hash_key(key)
        self._namespace_keys[hashed] = namespace.strip()
        return hashed

    def remove_key(self, key: str) -> bool:
        hashed = self._hash_key(key)
        removed = False
        if hashed in self._master_keys:
            self._master_keys.pop(hashed, None)
            removed = True
        if hashed in self._namespace_keys:
            self._namespace_keys.pop(hashed, None)
            removed = True
        return removed

    def validate(self, key: str) -> bool:
        if not self.auth_enabled:
            return True
        return self.authenticate(key) is not None

    def authenticate(self, key: str, *, source: str = "authorization") -> AuthContext | None:
        if not self.auth_enabled:
            return self.open_context()

        hashed = self._hash_key(key)
        for candidate, name in self._master_keys.items():
            if hmac.compare_digest(hashed, candidate):
                return AuthContext(
                    mode="master",
                    token_name=name,
                    namespace=None,
                    permissions=("read", "write", "delete", "admin", "cross_namespace"),
                    source=source,
                )

        for candidate, namespace in self._namespace_keys.items():
            if hmac.compare_digest(hashed, candidate):
                return AuthContext(
                    mode="namespace",
                    token_name=f"namespace:{namespace}",
                    namespace=namespace,
                    permissions=("read", "write", "delete", f"namespace:{namespace}"),
                    source=source,
                )

        return None

    def open_context(self) -> AuthContext:
        return AuthContext(
            mode="open",
            token_name="open-mode",
            namespace=None,
            permissions=("read", "write", "delete", "admin", "cross_namespace"),
            source="none",
        )

    @property
    def auth_enabled(self) -> bool:
        return bool(self._master_keys or self._namespace_keys)

    @property
    def key_count(self) -> int:
        return len(self._master_keys) + len(self._namespace_keys)

    @property
    def namespace_key_count(self) -> int:
        return len(self._namespace_keys)

    @property
    def master_key_count(self) -> int:
        return len(self._master_keys)


def extract_api_token(request: Any) -> tuple[str | None, str]:
    """Extract a bearer token, with X-API-Key kept for backward compatibility."""
    authorization = request.headers.get("Authorization", "") if hasattr(request, "headers") else ""
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip(), "authorization"
    legacy = request.headers.get("X-API-Key", "").strip() if hasattr(request, "headers") else ""
    if legacy:
        return legacy, "x-api-key"
    return None, "none"


def get_auth_context(request: Any, key_manager: APIKeyManager | None = None) -> AuthContext:
    state = getattr(request, "state", None)
    ctx = getattr(state, "memos_auth", None) if state is not None else None
    if ctx is not None:
        return ctx
    if key_manager is not None:
        return key_manager.open_context()
    return AuthContext(mode="open", token_name="open-mode")


def create_auth_middleware(key_manager: APIKeyManager, *, memos: Any | None = None):
    """Create ASGI middleware for MemOS bearer authentication."""

    async def middleware(request, call_next):
        path = str(request.url.path) if hasattr(request, "url") else "/"
        if path in _OPEN_PATHS:
            return await call_next(request)

        if key_manager.auth_enabled:
            token, source = extract_api_token(request)
            if not token:
                _LOG.warning(
                    "unauthorized request missing token",
                    extra={"path": path, "client": getattr(getattr(request, "client", None), "host", "unknown")},
                )
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=401,
                    content={
                        "status": "error",
                        "message": "Missing Authorization: Bearer <token> header",
                    },
                )

            context = key_manager.authenticate(token, source=source)
            if context is None:
                _LOG.warning(
                    "unauthorized request invalid token",
                    extra={"path": path, "client": getattr(getattr(request, "client", None), "host", "unknown")},
                )
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=403,
                    content={"status": "error", "message": "Invalid API token"},
                )
        else:
            context = key_manager.open_context()

        request.state.memos_auth = context

        previous_namespace = None
        can_scope_namespace = memos is not None and hasattr(memos, "namespace")
        if can_scope_namespace:
            previous_namespace = memos.namespace
            if context.namespace is not None:
                memos.namespace = context.namespace

        try:
            response = await call_next(request)
        finally:
            if can_scope_namespace:
                if previous_namespace is not None:
                    memos.namespace = previous_namespace

        response.headers["X-Memos-Auth-Mode"] = context.mode
        if context.namespace:
            response.headers["X-Memos-Namespace"] = context.namespace
        return response

    return middleware
