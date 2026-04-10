"""Tests for MemOS API authentication."""

import os
import time

import pytest

from memos.core import MemOS
from memos.api.auth import APIKeyManager, RateLimiter


class TestAPIKeyManager:
    def test_no_keys_auth_disabled(self):
        mgr = APIKeyManager()
        assert not mgr.auth_enabled
        assert mgr.key_count == 0
        assert mgr.validate("anything") is True
        assert mgr.open_context().mode == "open"

    def test_add_and_validate_master_key(self):
        mgr = APIKeyManager(keys=["sk-test-123"])
        assert mgr.auth_enabled
        assert mgr.key_count == 1
        ctx = mgr.authenticate("sk-test-123")
        assert ctx is not None
        assert ctx.mode == "master"
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
        assert "sk-secret" not in str(mgr._master_keys)
        assert mgr.validate("sk-secret") is True

    def test_multiple_keys(self):
        mgr = APIKeyManager(keys=["key-a", "key-b", "key-c"])
        assert mgr.key_count == 3
        assert mgr.validate("key-a") is True
        assert mgr.validate("key-b") is True
        assert mgr.validate("key-d") is False

    def test_namespace_key_authenticates_scoped_identity(self):
        mgr = APIKeyManager(namespace_keys={"orion": "key-orion"})
        ctx = mgr.authenticate("key-orion")
        assert ctx is not None
        assert ctx.mode == "namespace"
        assert ctx.namespace == "orion"
        assert "namespace:orion" in ctx.permissions

    def test_from_env_loads_master_and_namespace_keys(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "master-123")
        monkeypatch.setenv("MEMOS_NAMESPACE_KEYS", '{"orion": "orion-123", "specter": "specter-123"}')
        mgr = APIKeyManager.from_env()
        assert mgr.auth_enabled
        assert mgr.master_key_count == 1
        assert mgr.namespace_key_count == 2
        assert mgr.authenticate("master-123").mode == "master"
        assert mgr.authenticate("orion-123").namespace == "orion"


class TestRateLimiter:
    def test_basic_allow(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60.0)
        allowed, headers = limiter.check("key-1")
        assert allowed is True
        assert headers["X-RateLimit-Limit"] == "5"
        assert headers["X-RateLimit-Remaining"] == "4"

    def test_rate_limit_exceeded(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60.0)
        for _ in range(3):
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
        limiter = RateLimiter(max_requests=2, window_seconds=0.1)
        limiter.check("key-1")
        limiter.check("key-1")
        assert limiter.check("key-1")[0] is False
        time.sleep(0.15)
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
    def app_no_auth(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("MEMOS_API_KEY", raising=False)
        monkeypatch.delenv("MEMOS_NAMESPACE_KEYS", raising=False)
        from memos.api import create_fastapi_app

        return create_fastapi_app(api_keys=None)

    @pytest.fixture
    def app_with_auth(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("MEMOS_API_KEY", raising=False)
        monkeypatch.delenv("MEMOS_NAMESPACE_KEYS", raising=False)
        from memos.api import create_fastapi_app

        return create_fastapi_app(api_keys=["sk-test-123"])

    @pytest.fixture
    def app_rate_limited(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("MEMOS_API_KEY", raising=False)
        monkeypatch.delenv("MEMOS_NAMESPACE_KEYS", raising=False)
        from memos.api import create_fastapi_app

        return create_fastapi_app(api_keys=["sk-test"], rate_limit=2)

    def test_no_auth_allows_requests(self, app_no_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_no_auth)
        resp = client.get("/api/v1/stats")
        assert resp.status_code == 200
        assert resp.headers["X-Memos-Auth-Mode"] == "open"

    def test_auth_blocks_no_token(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/api/v1/stats")
        assert resp.status_code == 401

    def test_auth_blocks_wrong_token(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/api/v1/stats", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 403

    def test_auth_allows_valid_bearer(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get("/api/v1/stats", headers={"Authorization": "Bearer sk-test-123"})
        assert resp.status_code == 200
        assert resp.headers["X-Memos-Auth-Mode"] == "master"

    def test_auth_allows_legacy_header(self, app_with_auth):
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
        assert data["auth_enabled"] is True
        assert data["active_keys"] == 1
        assert data["master_keys"] == 1
        assert data["namespace_keys"] == 0

    def test_whoami_returns_master_identity(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.get(
            "/api/v1/auth/whoami",
            headers={"Authorization": "Bearer sk-test-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_mode"] == "master"
        assert data["namespace"] is None
        assert "admin" in data["permissions"]

    def test_rate_limit_enforced(self, app_rate_limited):
        from fastapi.testclient import TestClient

        client = TestClient(app_rate_limited)
        headers = {"Authorization": "Bearer sk-test"}
        resp1 = client.get("/api/v1/auth/whoami", headers=headers)
        assert resp1.status_code == 200
        resp2 = client.get("/api/v1/auth/whoami", headers=headers)
        assert resp2.status_code == 200
        resp3 = client.get("/api/v1/auth/whoami", headers=headers)
        assert resp3.status_code == 429

    def test_learn_with_auth(self, app_with_auth):
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth)
        resp = client.post(
            "/api/v1/learn",
            json={"content": "test memory"},
            headers={"Authorization": "Bearer sk-test-123"},
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

    def test_namespace_key_forces_namespace_isolation(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("MEMOS_API_KEY", raising=False)
        monkeypatch.delenv("MEMOS_NAMESPACE_KEYS", raising=False)
        from fastapi.testclient import TestClient
        from memos.api import create_fastapi_app

        memos = MemOS(backend="memory")
        app = create_fastapi_app(
            memos=memos,
            api_keys=["master-123"],
            namespace_keys={"orion": "orion-123"},
        )
        client = TestClient(app)

        seed = client.post(
            "/api/v1/learn",
            json={"content": "orion private memory", "namespace": "specter"},
            headers={"Authorization": "Bearer orion-123"},
        )
        assert seed.status_code == 200
        assert len(memos._store.list_all(namespace="orion")) == 1
        assert len(memos._store.list_all(namespace="specter")) == 0
        assert memos.namespace == ""

        recall = client.post(
            "/api/v1/recall",
            json={"query": "private", "top": 5},
            headers={"Authorization": "Bearer orion-123"},
        )
        assert recall.status_code == 200
        assert recall.json()["results"]

        whoami = client.get(
            "/api/v1/auth/whoami",
            headers={"Authorization": "Bearer orion-123"},
        )
        assert whoami.status_code == 200
        assert whoami.json()["auth_mode"] == "namespace"
        assert whoami.json()["namespace"] == "orion"
