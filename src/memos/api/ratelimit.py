"""Standalone rate limiting middleware for MemOS REST API.

Features:
- Token bucket algorithm (smooth burst handling)
- Per-endpoint configurable limits
- Works with or without authentication
- Rate limit headers on every response
- Status endpoint for monitoring
"""

from __future__ import annotations

import ipaddress
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

# ── Rate limiter configuration ──────────────────────────────────

_TRUSTED_CLIENTS: frozenset[str] = frozenset(
    c.strip() for c in os.environ.get("MEMOS_TRUSTED_CLIENTS", "").split(",") if c.strip()
)

_MAX_BUCKETS: int = int(os.environ.get("MEMOS_RATELIMIT_MAX_BUCKETS", "10000"))

_STALE_BUCKET_TTL: float = float(os.environ.get("MEMOS_RATELIMIT_BUCKET_TTL", "3600"))

_MAX_RULE_CACHE: int = max(1, int(os.environ.get("MEMOS_RATELIMIT_MAX_RULE_CACHE", "4096")))


@dataclass
class TokenBucket:
    """Token bucket rate limiter for a single client.

    Tokens replenish at a steady rate (refill_rate per second).
    Each request consumes one token. Bursts are allowed up to max_tokens.
    """

    max_tokens: int
    refill_rate: float  # tokens per second
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)
    last_access: float = field(default_factory=time.monotonic)

    def consume(self, n: int = 1) -> bool:
        """Try to consume n tokens. Returns True if allowed."""
        self._refill()
        self.last_access = time.monotonic()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    @property
    def remaining(self) -> int:
        self._refill()
        return int(self.tokens)


@dataclass
class EndpointRule:
    """Rate limit rule for an endpoint pattern.

    Attributes:
        pattern: URL prefix to match (e.g. "/api/v1/learn")
        max_requests: Maximum tokens in the bucket
        window_seconds: Time window in seconds for token replenishment
    """

    pattern: str
    max_requests: int
    window_seconds: float = 60.0

    @property
    def refill_rate(self) -> float:
        return self.max_requests / self.window_seconds


# Default endpoint rules — write-heavy endpoints get stricter limits
DEFAULT_RULES: list[EndpointRule] = [
    EndpointRule(pattern="/api/v1/learn", max_requests=30, window_seconds=60.0),
    EndpointRule(pattern="/api/v1/prune", max_requests=10, window_seconds=60.0),
    EndpointRule(pattern="/api/v1/consolidate", max_requests=5, window_seconds=60.0),
    EndpointRule(pattern="/api/v1/memory", max_requests=30, window_seconds=60.0),
    EndpointRule(pattern="/api/v1/namespaces", max_requests=20, window_seconds=60.0),
    EndpointRule(pattern="/api/v1/recall", max_requests=60, window_seconds=60.0),
    EndpointRule(pattern="/api/v1/search", max_requests=60, window_seconds=60.0),
    EndpointRule(pattern="/api/v1/stats", max_requests=30, window_seconds=60.0),
    EndpointRule(pattern="/api/v1/events", max_requests=30, window_seconds=60.0),
    EndpointRule(pattern="/api/v1/export", max_requests=10, window_seconds=60.0),
]


class RateLimiter:
    """Per-client, per-endpoint token bucket rate limiter.

    Args:
        default_max: Default max requests per window when no rule matches.
        default_window: Default window in seconds.
        rules: List of EndpointRule patterns. Uses first match (most specific first).
        key_func: Optional callable(request) -> str to extract client identifier.
                  Defaults to X-Forwarded-For or client IP.
        max_buckets: Maximum number of client buckets before eviction.
        max_rule_cache: Maximum number of endpoint path rule-cache entries.
        trusted_clients: Set of client identifiers that bypass rate limiting.
    """

    def __init__(
        self,
        default_max: int = 100,
        default_window: float = 60.0,
        rules: Optional[list[EndpointRule]] = None,
        key_func: Any = None,
        max_buckets: int = _MAX_BUCKETS,
        max_rule_cache: int = _MAX_RULE_CACHE,
        trusted_clients: Optional[set[str]] = None,
    ) -> None:
        self.default_max = default_max
        self.default_window = default_window
        self.rules = rules or list(DEFAULT_RULES)
        self.key_func = key_func
        self.max_buckets = max(1, int(max_buckets))
        self.max_rule_cache = max(1, int(max_rule_cache))
        self.trusted_clients = trusted_clients if trusted_clients is not None else set(_TRUSTED_CLIENTS)
        self._rule_cache: OrderedDict[str, EndpointRule] = OrderedDict()
        self._buckets: OrderedDict[str, dict[str, TokenBucket]] = OrderedDict()

    def _client_key(self, request: Any) -> str:
        if self.key_func:
            return self.key_func(request)
        forwarded = None
        if hasattr(request, "headers"):
            forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first and not _is_spoofed_xff(first):
                return first
        if hasattr(request, "client") and request.client:
            return str(request.client.host)
        return "anonymous"

    def _match_rule(self, path: str) -> EndpointRule:
        cached = self._rule_cache.get(path)
        if cached is not None:
            self._rule_cache.move_to_end(path)
            return cached
        for rule in self.rules:
            if path.startswith(rule.pattern):
                self._cache_rule(path, rule)
                return rule
        default = EndpointRule(
            pattern="__default__",
            max_requests=self.default_max,
            window_seconds=self.default_window,
        )
        self._cache_rule(path, default)
        return default

    def _cache_rule(self, path: str, rule: EndpointRule) -> None:
        """Store a matched rule in the bounded path cache."""
        self._rule_cache[path] = rule
        self._rule_cache.move_to_end(path)
        while len(self._rule_cache) > self.max_rule_cache:
            self._rule_cache.popitem(last=False)

    def _get_bucket(self, client: str, rule: EndpointRule) -> TokenBucket:
        if client not in self._buckets:
            self._evict_if_needed()
            self._buckets[client] = {}
            self._buckets.move_to_end(client)
        else:
            self._buckets.move_to_end(client)
        if rule.pattern not in self._buckets[client]:
            self._buckets[client][rule.pattern] = TokenBucket(
                max_tokens=rule.max_requests,
                refill_rate=rule.refill_rate,
                tokens=float(rule.max_requests),
            )
        return self._buckets[client][rule.pattern]

    def _evict_if_needed(self) -> int:
        evicted = self._evict_stale()
        while len(self._buckets) >= self.max_buckets and self._buckets:
            oldest_key, _ = self._buckets.popitem(last=False)
            evicted += 1
        return evicted

    def _evict_stale(self) -> int:
        if _STALE_BUCKET_TTL <= 0:
            return 0
        now = time.monotonic()
        stale_keys: list[str] = []
        for key, client_buckets in self._buckets.items():
            newest_access = max((b.last_access for b in client_buckets.values()), default=None)
            if newest_access is None:
                stale_keys.append(key)
                continue
            if (now - newest_access) > _STALE_BUCKET_TTL:
                stale_keys.append(key)
        for key in stale_keys:
            del self._buckets[key]
        return len(stale_keys)

    def check(self, request: Any) -> tuple[bool, dict[str, str], EndpointRule]:
        self._evict_stale()
        path = str(request.url.path) if hasattr(request, "url") else "/"
        client = self._client_key(request)

        if client in self.trusted_clients:
            rule = self._match_rule(path)
            return (
                True,
                {
                    "X-RateLimit-Limit": str(rule.max_requests),
                    "X-RateLimit-Remaining": str(rule.max_requests),
                    "X-RateLimit-Window": str(rule.window_seconds),
                    "X-RateLimit-Policy": rule.pattern,
                    "X-RateLimit-Trusted": "true",
                },
                rule,
            )

        rule = self._match_rule(path)
        bucket = self._get_bucket(client, rule)
        allowed = bucket.consume()

        headers = {
            "X-RateLimit-Limit": str(rule.max_requests),
            "X-RateLimit-Remaining": str(bucket.remaining),
            "X-RateLimit-Window": str(rule.window_seconds),
            "X-RateLimit-Policy": rule.pattern,
        }
        return allowed, headers, rule

    def get_status(self, request: Any) -> dict[str, Any]:
        self._evict_stale()
        client = self._client_key(request)
        buckets = self._buckets.get(client, {})
        policies = []
        for pattern, bucket in buckets.items():
            policies.append(
                {
                    "endpoint": pattern,
                    "limit": bucket.max_tokens,
                    "remaining": bucket.remaining,
                    "refill_rate": round(bucket.refill_rate, 2),
                }
            )
        return {
            "client": client,
            "trusted": client in self.trusted_clients,
            "policies": policies,
            "total_policies": len(policies),
            "default_limit": self.default_max,
            "default_window": self.default_window,
            "active_clients": len(self._buckets),
            "max_clients": self.max_buckets,
            "rule_cache_size": len(self._rule_cache),
            "max_rule_cache": self.max_rule_cache,
        }

    def reset(self, client: Optional[str] = None) -> int:
        if client:
            count = len(self._buckets.pop(client, {}))
        else:
            count = sum(len(v) for v in self._buckets.values())
            self._buckets.clear()
        return count


_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.\-]*[a-zA-Z0-9])?$")


def _is_spoofed_xff(value: str) -> bool:
    """Detect obviously malformed XFF values that look spoofed."""
    stripped = value.strip()
    if not stripped:
        return True
    # Valid IPv4 or IPv6
    try:
        ipaddress.ip_address(stripped)
        return False
    except ValueError:
        pass
    # Valid hostname (letters, digits, hyphens, dots)
    if _HOSTNAME_RE.match(stripped):
        return False
    return True


def create_rate_limit_middleware(limiter: RateLimiter):
    """Create ASGI middleware for rate limiting.

    Can be used independently or alongside auth middleware.
    Applies to all API endpoints except health/docs.

    Usage:
        from memos.api.ratelimit import RateLimiter, create_rate_limit_middleware
        limiter = RateLimiter(default_max=100)
        app.middleware("http")(create_rate_limit_middleware(limiter))
    """

    async def middleware(request, call_next):
        path = str(request.url.path) if hasattr(request, "url") else "/"

        # Skip non-API paths
        if path in ("/", "/health", "/api/v1/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        allowed, headers, rule = limiter.check(request)

        if not allowed:
            from starlette.responses import JSONResponse

            headers["Retry-After"] = str(int(rule.window_seconds))
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "message": "Rate limit exceeded",
                    "policy": rule.pattern,
                    "limit": rule.max_requests,
                    "window_seconds": rule.window_seconds,
                },
                headers=headers,
            )

        response = await call_next(request)
        for k, v in headers.items():
            response.headers[k] = v
        return response

    return middleware
