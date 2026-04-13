"""API Key authentication and rate limiting for MemOS."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Optional


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
            return True, self._headers(1, self.max_requests, now, key)

        entry.count += 1
        allowed = entry.count <= self.max_requests
        return allowed, self._headers(entry.count, self.max_requests, now, key)

    def _headers(self, current: int, limit: int, now: float, key: str) -> dict[str, str]:
        entry = self._counters[key]
        reset_at = entry.window_start + self.window_seconds
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, limit - current)),
            "X-RateLimit-Reset": str(int(reset_at)),
        }


class APIKeyManager:
    """Manages API keys for MemOS authentication."""

    def __init__(self, keys: Optional[list[str]] = None):
        """Initialize with optional list of valid API keys.

        If no keys provided, authentication is disabled.
        """
        self._hashed_keys: set[str] = set()
        self._key_names: dict[str, str] = {}  # hashed -> name for logging
        self.rate_limiter = RateLimiter()

        if keys:
            for i, key in enumerate(keys):
                self.add_key(key, name=f"key-{i+1}")

    @staticmethod
    def _hash_key(key: str) -> str:
        """Hash an API key for secure storage."""
        return hashlib.sha256(key.encode()).hexdigest()

    def add_key(self, key: str, name: str = "") -> str:
        """Add an API key. Returns the hashed key."""
        hashed = self._hash_key(key)
        self._hashed_keys.add(hashed)
        if name:
            self._key_names[hashed] = name
        return hashed

    def remove_key(self, key: str) -> bool:
        """Remove an API key."""
        hashed = self._hash_key(key)
        self._hashed_keys.discard(hashed)
        self._key_names.pop(hashed, None)
        return True

    def validate(self, key: str) -> bool:
        """Validate an API key."""
        if not self._hashed_keys:
            return True  # No keys configured = auth disabled
        hashed = self._hash_key(key)
        return hmac.compare_digest(hashed, hashed in self._hashed_keys and hashed or "")

    @property
    def auth_enabled(self) -> bool:
        return len(self._hashed_keys) > 0

    @property
    def key_count(self) -> int:
        return len(self._hashed_keys)


def create_auth_middleware(key_manager: APIKeyManager):
    """Create ASGI middleware for API key auth and rate limiting.

    Usage with FastAPI:
        from memos.api.auth import APIKeyManager, create_auth_middleware
        key_mgr = APIKeyManager(keys=["sk-test-123"])
        app = create_fastapi_app()
        app.middleware("http")(create_auth_middleware(key_mgr))
    """
    async def middleware(request, call_next):
        # Skip auth for health and dashboard
        path = request.url.path
        if path in ("/", "/health", "/docs", "/openapi.json"):
            return await call_next(request)

        if key_manager.auth_enabled:
            api_key = request.headers.get("X-API-Key", "")
            if not api_key:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"status": "error", "message": "Missing X-API-Key header"},
                )
            if not key_manager.validate(api_key):
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=403,
                    content={"status": "error", "message": "Invalid API key"},
                )

            # Rate limiting
            allowed, headers = key_manager.rate_limiter.check(api_key)
            response = await call_next(request)
            for k, v in headers.items():
                response.headers[k] = v
            if not allowed:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"status": "error", "message": "Rate limit exceeded"},
                    headers=headers,
                )
            return response

        return await call_next(request)

    return middleware
