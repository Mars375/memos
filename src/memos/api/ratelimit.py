"""Standalone rate limiting middleware for MemOS REST API.

Features:
- Token bucket algorithm (smooth burst handling)
- Per-endpoint configurable limits
- Works with or without authentication
- Rate limit headers on every response
- Status endpoint for monitoring
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


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

    def consume(self, n: int = 1) -> bool:
        """Try to consume n tokens. Returns True if allowed."""
        self._refill()
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
    """

    def __init__(
        self,
        default_max: int = 100,
        default_window: float = 60.0,
        rules: Optional[list[EndpointRule]] = None,
        key_func: Any = None,
    ) -> None:
        self.default_max = default_max
        self.default_window = default_window
        self.rules = rules or list(DEFAULT_RULES)
        self.key_func = key_func
        # {client_key: {endpoint_pattern: TokenBucket}}
        self._buckets: dict[str, dict[str, TokenBucket]] = {}

    def _client_key(self, request: Any) -> str:
        """Extract client identifier from request."""
        if self.key_func:
            return self.key_func(request)
        forwarded = None
        if hasattr(request, "headers"):
            forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if hasattr(request, "client") and request.client:
            return str(request.client.host)
        return "anonymous"

    def _match_rule(self, path: str) -> EndpointRule:
        """Find the first matching rule for the given path."""
        for rule in self.rules:
            if path.startswith(rule.pattern):
                return rule
        return EndpointRule(
            pattern="__default__",
            max_requests=self.default_max,
            window_seconds=self.default_window,
        )

    def _get_bucket(self, client: str, rule: EndpointRule) -> TokenBucket:
        """Get or create a token bucket for a client+rule combination."""
        if client not in self._buckets:
            self._buckets[client] = {}
        if rule.pattern not in self._buckets[client]:
            self._buckets[client][rule.pattern] = TokenBucket(
                max_tokens=rule.max_requests,
                refill_rate=rule.refill_rate,
                tokens=float(rule.max_requests),
            )
        return self._buckets[client][rule.pattern]

    def check(self, request: Any) -> tuple[bool, dict[str, str], EndpointRule]:
        """Check if a request is allowed.

        Returns:
            (allowed, headers, matched_rule)
        """
        path = str(request.url.path) if hasattr(request, "url") else "/"
        client = self._client_key(request)
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
        """Get rate limit status for the requesting client."""
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
            "policies": policies,
            "total_policies": len(policies),
            "default_limit": self.default_max,
            "default_window": self.default_window,
        }

    def reset(self, client: Optional[str] = None) -> int:
        """Reset rate limit counters.

        Args:
            client: If provided, reset only for this client. Otherwise reset all.

        Returns:
            Number of buckets reset.
        """
        if client:
            count = len(self._buckets.pop(client, {}))
        else:
            count = sum(len(v) for v in self._buckets.values())
            self._buckets.clear()
        return count


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
        if path in ("/", "/health", "/docs", "/openapi.json", "/redoc"):
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
