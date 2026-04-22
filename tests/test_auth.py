"""Tests for API key authentication and rate limiting."""

import pytest
from freezegun import freeze_time

from memos.api.auth import APIKeyManager, RateLimiter


class TestAPIKeyManager:
    def test_no_keys_auth_disabled(self):
        mgr = APIKeyManager()
        assert not mgr.auth_enabled
        assert mgr.key_count == 0
        assert mgr.validate("anything") is True

    def test_add_and_validate_key(self):
        mgr = APIKeyManager(keys=["sk-test-123"])
        assert mgr.auth_enabled
        assert mgr.key_count == 1
        assert mgr.validate("sk-test-123") is True
        assert mgr.validate("wrong-key") is False

    def test_remove_key(self):
        mgr = APIKeyManager(keys=["sk-test-123"])
        mgr.remove_key("sk-test-123")
        assert mgr.key_count == 0
        assert not mgr.auth_enabled

    def test_key_hashing(self):
        """Keys are stored hashed, not plaintext."""
        mgr = APIKeyManager(keys=["sk-secret"])
        assert "sk-secret" not in str(mgr._hashed_keys)
        assert mgr.validate("sk-secret") is True

    def test_multiple_keys(self):
        mgr = APIKeyManager(keys=["key-a", "key-b", "key-c"])
        assert mgr.key_count == 3
        assert mgr.validate("key-a") is True
        assert mgr.validate("key-b") is True
        assert mgr.validate("key-d") is False

    def test_add_key_with_name(self):
        mgr = APIKeyManager()
        mgr.add_key("sk-admin", name="admin")
        assert mgr.auth_enabled
        assert mgr.validate("sk-admin") is True
        assert mgr._key_names  # name stored


class TestRateLimiter:
    def test_basic_allow(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60.0)
        allowed, headers = limiter.check("key-1")
        assert allowed is True
        assert headers["X-RateLimit-Limit"] == "5"
        assert headers["X-RateLimit-Remaining"] == "4"

    def test_rate_limit_exceeded(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60.0)
        for i in range(3):
            allowed, _ = limiter.check("key-1")
            assert allowed is True
        allowed, headers = limiter.check("key-1")
        assert allowed is False
        assert headers["X-RateLimit-Remaining"] == "0"

    def test_separate_keys_independent(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60.0)
        limiter.check("key-a")
        limiter.check("key-a")
        assert limiter.check("key-a")[0] is False
        assert limiter.check("key-b")[0] is True

    def test_window_reset(self):
        with freeze_time("2024-01-01 12:00:00") as frozen:
            limiter = RateLimiter(max_requests=2, window_seconds=0.1)
            limiter.check("key-1")
            limiter.check("key-1")
            assert limiter.check("key-1")[0] is False
            frozen.tick(1)  # Advance past 0.1s window
            assert limiter.check("key-1")[0] is True

    def test_headers_format(self):
        limiter = RateLimiter(max_requests=10, window_seconds=60.0)
        _, headers = limiter.check("key-1")
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers
        assert int(headers["X-RateLimit-Reset"]) > 0


class TestFastAPIAuth:
    @pytest.fixture
    def app_no_auth(self):
        from memos.api import create_fastapi_app

        return create_fastapi_app(api_keys=None)

    @pytest.fixture
    def app_with_auth(self):
        from memos.api import create_fastapi_app

        return create_fastapi_app(api_keys=["sk-test-123"])

    @pytest.fixture
    def app_rate_limited(self):
        from memos.api import create_fastapi_app

        return create_fastapi_app(api_keys=["sk-test"], rate_limit=2)

    def test_no_auth_allows_requests(self, app_no_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_no_auth)
        resp = client.get("/api/v1/stats")
        assert resp.status_code == 200

    def test_auth_blocks_no_key(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/api/v1/stats")
        assert resp.status_code == 401

    def test_auth_blocks_wrong_key(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/api/v1/stats", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 403

    def test_auth_allows_valid_key(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/api/v1/stats", headers={"X-API-Key": "sk-test-123"})
        assert resp.status_code == 200

    def test_health_no_auth_required(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_enabled" not in data
        assert "active_keys" not in data
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_authenticated_exposes_auth_state(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/api/v1/health", headers={"X-API-Key": "sk-test-123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_enabled"] is True
        assert data["active_keys"] == 1

    def test_health_no_auth_required_on_prefixed_route(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["auth_enabled"] is True
        assert data["active_keys"] == 1

    def test_health_unauthenticated_no_auth_state(self):
        from memos.api import create_fastapi_app

        app = create_fastapi_app(api_keys=None)
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_enabled"] is False
        assert data["active_keys"] == 0

    def test_dashboard_no_auth_required(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/")
        assert resp.status_code == 200

    def test_dashboard_alias_no_auth_required(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_redoc_no_auth_required(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/redoc")
        assert resp.status_code == 200

    def test_static_assets_no_auth_required(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/static/dashboard.css")
        assert resp.status_code == 200

    def test_rate_limit_enforced(self, app_rate_limited):
        from fastapi.testclient import TestClient

        client = TestClient(app_rate_limited)
        headers = {"X-API-Key": "sk-test"}
        resp1 = client.get("/api/v1/stats", headers=headers)
        assert resp1.status_code == 200
        resp2 = client.get("/api/v1/stats", headers=headers)
        assert resp2.status_code == 200
        resp3 = client.get("/api/v1/stats", headers=headers)
        assert resp3.status_code == 429

    def test_learn_with_auth(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.post(
            "/api/v1/learn",
            json={"content": "test memory"},
            headers={"X-API-Key": "sk-test-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_learn_blocked_without_auth(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.post(
            "/api/v1/learn",
            json={"content": "test memory"},
        )
        assert resp.status_code == 401


class TestWebSocketAuth:
    """WebSocket /ws must enforce authentication when keys are configured."""

    @pytest.fixture
    def app_with_auth(self):
        from memos.api import create_fastapi_app

        return create_fastapi_app(api_keys=["sk-ws-test"])

    @pytest.fixture
    def app_no_auth(self):
        from memos.api import create_fastapi_app

        return create_fastapi_app(api_keys=None)

    def test_ws_rejects_no_key(self, app_with_auth):
        from fastapi.testclient import TestClient

        with TestClient(app_with_auth) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/ws"):
                    pass

    def test_ws_rejects_wrong_key(self, app_with_auth):
        from fastapi.testclient import TestClient

        with TestClient(app_with_auth) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/ws?api_key=wrong-key"):
                    pass

    def test_ws_accepts_valid_key(self, app_with_auth):
        from fastapi.testclient import TestClient

        with TestClient(app_with_auth) as client:
            with client.websocket_connect("/ws?api_key=sk-ws-test") as ws:
                ws.send_text("ping")
                data = ws.receive_json()
                assert data["type"] == "pong"

    def test_ws_no_auth_allows_anonymous(self, app_no_auth):
        from fastapi.testclient import TestClient

        with TestClient(app_no_auth) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_text("ping")
                data = ws.receive_json()
                assert data["type"] == "pong"
