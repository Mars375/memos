"""Tests for the rate limiting module."""

import time

from freezegun import freeze_time

from memos.api.ratelimit import (
    DEFAULT_RULES,
    EndpointRule,
    RateLimiter,
    TokenBucket,
    create_rate_limit_middleware,
)


class MockURL:
    def __init__(self, path: str):
        self.path = path


class MockClient:
    def __init__(self, host: str):
        self.host = host


class MockRequest:
    def __init__(self, path: str = "/api/v1/learn", client_host: str = "127.0.0.1", headers: dict | None = None):
        self.url = MockURL(path)
        self.client = MockClient(client_host)
        self.headers = headers or {}


class TestTokenBucket:
    """Tests for the TokenBucket class."""

    def test_initial_state(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=1.0, tokens=10.0)
        assert bucket.remaining == 10

    def test_consume_within_limit(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=1.0, tokens=10.0)
        assert bucket.consume() is True
        assert bucket.remaining == 9

    def test_consume_multiple(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=1.0, tokens=10.0)
        assert bucket.consume(5) is True
        assert bucket.remaining == 5

    def test_consume_exceeds_limit(self):
        bucket = TokenBucket(max_tokens=3, refill_rate=1.0, tokens=3.0)
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is False

    def test_refill(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=100.0, tokens=0.0)
        bucket.last_refill = time.monotonic() - 0.1  # 100ms ago
        assert bucket.remaining >= 9

    def test_refill_cap_at_max(self):
        bucket = TokenBucket(max_tokens=5, refill_rate=1000.0, tokens=5.0)
        bucket.last_refill = time.monotonic() - 10  # Way in the past
        assert bucket.remaining == 5  # Capped at max

    def test_consume_then_refill(self):
        with freeze_time("2024-01-01 12:00:00") as frozen:
            bucket = TokenBucket(max_tokens=5, refill_rate=10.0, tokens=5.0)
            for _ in range(5):
                assert bucket.consume()
            assert bucket.consume() is False
            frozen.tick(0.2)  # ~2 tokens refilled at 10/s
            assert bucket.remaining >= 1

    def test_remaining_reflects_refill(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=10.0, tokens=0.0)
        bucket.last_refill = time.monotonic() - 0.5
        remaining = bucket.remaining
        assert 4 <= remaining <= 10


class TestEndpointRule:
    """Tests for EndpointRule."""

    def test_refill_rate(self):
        rule = EndpointRule(pattern="/api/v1/learn", max_requests=30, window_seconds=60.0)
        assert rule.refill_rate == 0.5

    def test_refill_rate_custom_window(self):
        rule = EndpointRule(pattern="/api/v1/test", max_requests=100, window_seconds=10.0)
        assert rule.refill_rate == 10.0

    def test_default_window(self):
        rule = EndpointRule(pattern="/api/v1/test", max_requests=50)
        assert rule.window_seconds == 60.0


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    def test_default_config(self):
        limiter = RateLimiter()
        assert limiter.default_max == 100
        assert len(limiter.rules) == len(DEFAULT_RULES)

    def test_custom_rules(self):
        rules = [EndpointRule(pattern="/api/v1/test", max_requests=5)]
        limiter = RateLimiter(rules=rules)
        assert len(limiter.rules) == 1

    def test_check_allows_initial_request(self):
        limiter = RateLimiter(
            rules=[
                EndpointRule(pattern="/api/v1/learn", max_requests=5, window_seconds=60.0),
            ]
        )
        req = MockRequest("/api/v1/learn")
        allowed, headers, rule = limiter.check(req)
        assert allowed is True
        assert headers["X-RateLimit-Limit"] == "5"
        assert headers["X-RateLimit-Remaining"] == "4"
        assert rule.pattern == "/api/v1/learn"

    def test_check_blocks_after_exhausting_tokens(self):
        limiter = RateLimiter(
            rules=[
                EndpointRule(pattern="/api/v1/learn", max_requests=3, window_seconds=60.0),
            ]
        )
        req = MockRequest("/api/v1/learn")
        for _ in range(3):
            allowed, _, _ = limiter.check(req)
            assert allowed is True
        # 4th request should be blocked
        allowed, headers, rule = limiter.check(req)
        assert allowed is False
        assert headers["X-RateLimit-Remaining"] == "0"

    def test_different_endpoints_independent(self):
        limiter = RateLimiter(
            rules=[
                EndpointRule(pattern="/api/v1/learn", max_requests=2, window_seconds=60.0),
                EndpointRule(pattern="/api/v1/recall", max_requests=10, window_seconds=60.0),
            ]
        )
        # Exhaust learn
        req_learn = MockRequest("/api/v1/learn")
        limiter.check(req_learn)
        limiter.check(req_learn)
        allowed, _, _ = limiter.check(req_learn)
        assert allowed is False
        # Recall should still work
        req_recall = MockRequest("/api/v1/recall")
        allowed, _, _ = limiter.check(req_recall)
        assert allowed is True

    def test_different_clients_independent(self):
        limiter = RateLimiter(
            rules=[
                EndpointRule(pattern="/api/v1/learn", max_requests=2, window_seconds=60.0),
            ]
        )
        req1 = MockRequest("/api/v1/learn", "192.168.1.1")
        req2 = MockRequest("/api/v1/learn", "192.168.1.2")
        limiter.check(req1)
        limiter.check(req1)
        allowed, _, _ = limiter.check(req1)
        assert allowed is False
        # Different client should still have tokens
        allowed, _, _ = limiter.check(req2)
        assert allowed is True

    def test_default_rule_for_unknown_endpoint(self):
        limiter = RateLimiter(default_max=50, rules=[])
        req = MockRequest("/api/v1/unknown")
        allowed, headers, rule = limiter.check(req)
        assert allowed is True
        assert rule.pattern == "__default__"
        assert headers["X-RateLimit-Limit"] == "50"

    def test_custom_key_func(self):
        limiter = RateLimiter(
            default_max=2,
            rules=[],
            key_func=lambda req: "fixed-key",
        )
        req1 = MockRequest("/api/v1/test", "1.1.1.1")
        req2 = MockRequest("/api/v1/test", "2.2.2.2")
        limiter.check(req1)
        limiter.check(req1)
        # Both share the same key via key_func
        allowed, _, _ = limiter.check(req2)
        assert allowed is False

    def test_forwarded_for_header(self):
        limiter = RateLimiter(default_max=2, rules=[])
        req = MockRequest("/api/v1/test", headers={"x-forwarded-for": "10.0.0.1, 10.0.0.2"})
        allowed, _, _ = limiter.check(req)
        assert allowed is True

    def test_get_status(self):
        limiter = RateLimiter(
            default_max=100,
            rules=[
                EndpointRule(pattern="/api/v1/learn", max_requests=10, window_seconds=60.0),
            ],
        )
        req = MockRequest("/api/v1/learn")
        limiter.check(req)
        status = limiter.get_status(req)
        assert status["client"] == "127.0.0.1"
        assert status["total_policies"] == 1
        assert status["policies"][0]["endpoint"] == "/api/v1/learn"
        assert status["policies"][0]["remaining"] == 9

    def test_reset_specific_client(self):
        limiter = RateLimiter(default_max=1, rules=[])
        req = MockRequest("/api/v1/test", "1.1.1.1")
        limiter.check(req)
        count = limiter.reset(client="1.1.1.1")
        assert count >= 1
        allowed, _, _ = limiter.check(req)
        assert allowed is True

    def test_reset_all(self):
        limiter = RateLimiter(default_max=1, rules=[])
        req1 = MockRequest("/api/v1/test", "1.1.1.1")
        req2 = MockRequest("/api/v1/test", "2.2.2.2")
        limiter.check(req1)
        limiter.check(req2)
        count = limiter.reset()
        assert count >= 2

    def test_headers_format(self):
        limiter = RateLimiter(
            rules=[
                EndpointRule(pattern="/api/v1/learn", max_requests=30, window_seconds=60.0),
            ]
        )
        req = MockRequest("/api/v1/learn")
        allowed, headers, rule = limiter.check(req)
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Window" in headers
        assert "X-RateLimit-Policy" in headers

    def test_anonymous_client_fallback(self):
        """Test that requests without client info use 'anonymous'."""
        limiter = RateLimiter(default_max=5, rules=[])

        class MinimalReq:
            url = MockURL("/api/v1/test")
            client = None
            headers = {}

        req = MinimalReq()
        allowed, _, _ = limiter.check(req)
        assert allowed is True
        status = limiter.get_status(req)
        assert status["client"] == "anonymous"


class TestCreateMiddleware:
    """Tests for the middleware factory."""

    def test_middleware_creation(self):
        limiter = RateLimiter()
        middleware = create_rate_limit_middleware(limiter)
        assert callable(middleware)


class TestTrustedClients:
    def test_trusted_client_bypasses_limit(self):
        limiter = RateLimiter(
            default_max=1,
            rules=[],
            trusted_clients={"internal-service"},
        )
        req = MockRequest("/api/v1/learn", client_host="10.0.0.1")
        req.headers["x-forwarded-for"] = "internal-service"

        for _ in range(20):
            allowed, headers, _ = limiter.check(req)
            assert allowed is True
        assert headers.get("X-RateLimit-Trusted") == "true"

    def test_trusted_client_shows_in_status(self):
        limiter = RateLimiter(default_max=5, rules=[], trusted_clients={"10.0.0.1"})
        req = MockRequest("/api/v1/test", client_host="10.0.0.1")
        status = limiter.get_status(req)
        assert status["trusted"] is True

    def test_non_trusted_client_not_flagged(self):
        limiter = RateLimiter(default_max=5, rules=[], trusted_clients={"10.0.0.1"})
        req = MockRequest("/api/v1/test", client_host="192.168.1.1")
        status = limiter.get_status(req)
        assert status["trusted"] is False


class TestBucketEviction:
    def test_max_buckets_evicts_oldest(self):
        limiter = RateLimiter(default_max=5, rules=[], max_buckets=3)
        for i in range(5):
            req = MockRequest("/api/v1/test", client_host=f"1.1.1.{i}")
            limiter.check(req)
        assert len(limiter._buckets) <= 3

    def test_stale_buckets_evicted_on_access(self):
        limiter = RateLimiter(default_max=5, rules=[], max_buckets=1000)
        req = MockRequest("/api/v1/test", client_host="1.1.1.1")
        limiter.check(req)

        for _client_buckets in limiter._buckets.values():
            for bucket in _client_buckets.values():
                bucket.last_access = time.monotonic() - 7200

        req2 = MockRequest("/api/v1/test", client_host="2.2.2.2")
        limiter.check(req2)
        assert "1.1.1.1" not in limiter._buckets

    def test_status_includes_active_clients(self):
        limiter = RateLimiter(default_max=5, rules=[], max_buckets=50)
        for i in range(3):
            req = MockRequest("/api/v1/test", client_host=f"1.1.1.{i}")
            limiter.check(req)
        req = MockRequest("/api/v1/test", client_host="1.1.1.0")
        status = limiter.get_status(req)
        assert status["active_clients"] == 3
        assert status["max_clients"] == 50


class TestXFFHardening:
    def test_malformed_xff_falls_back_to_client_ip(self):
        limiter = RateLimiter(default_max=1, rules=[])
        req = MockRequest("/api/v1/test", client_host="10.0.0.1")
        req.headers["x-forwarded-for"] = "!!!spoofed!!!"
        allowed, _, _ = limiter.check(req)
        assert allowed is True

        req2 = MockRequest("/api/v1/test", client_host="10.0.0.1")
        allowed2, _, _ = limiter.check(req2)
        assert allowed2 is False

    def test_valid_xff_used_as_key(self):
        limiter = RateLimiter(default_max=1, rules=[])
        req = MockRequest("/api/v1/test", client_host="10.0.0.1")
        req.headers["x-forwarded-for"] = "1.2.3.4"
        allowed, _, _ = limiter.check(req)
        assert allowed is True
        status = limiter.get_status(req)
        assert status["client"] == "1.2.3.4"

    def test_empty_xff_falls_back(self):
        limiter = RateLimiter(default_max=1, rules=[])
        req = MockRequest("/api/v1/test", client_host="10.0.0.1")
        req.headers["x-forwarded-for"] = ""
        status = limiter.get_status(req)
        assert status["client"] == "10.0.0.1"
