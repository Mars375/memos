"""Tests for health endpoint and configurable rate limiting."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from memos.api import create_fastapi_app
from memos.core import MemOS

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def memos():
    return MemOS(backend="memory")


@pytest.fixture()
def app(memos):
    return create_fastapi_app(memos=memos)


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def auth_rate_limited_client():
    app = create_fastapi_app(memos=MemOS(backend="memory"), api_keys=["sk-test"], rate_limit=1)
    return TestClient(app)


# ── Health endpoint ───────────────────────────────────────────


class TestHealthEndpoint:
    """GET /api/v1/health returns status, version and uptime."""

    def test_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_status_ok(self, client):
        data = client.get("/api/v1/health").json()
        assert data["status"] == "ok"

    def test_health_has_version(self, client):
        data = client.get("/api/v1/health").json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_health_has_uptime(self, client):
        data = client.get("/api/v1/health").json()
        assert "uptime" in data
        assert isinstance(data["uptime"], float)
        assert data["uptime"] >= 0

    def test_health_uptime_increases(self, client):
        import time

        d1 = client.get("/api/v1/health").json()
        time.sleep(0.05)
        d2 = client.get("/api/v1/health").json()
        assert d2["uptime"] >= d1["uptime"]

    def test_prefixed_health_skips_auth_and_rate_limit(self, auth_rate_limited_client):
        resp1 = auth_rate_limited_client.get("/api/v1/health")
        resp2 = auth_rate_limited_client.get("/api/v1/health")

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ok"


# ── Configurable rate limit ───────────────────────────────────


class TestConfigurableRateLimit:
    """Rate limit values come from env vars or defaults.

    We hit /api/v1/rate-limit/status (a GET that doesn't match any
    specific EndpointRule) so the default_max / default_window are used.
    """

    def test_default_rate_limit_is_300(self, client):
        """Default rate limit (no env) should be 300."""
        resp = client.get("/api/v1/rate-limit/status")
        assert resp.headers.get("X-RateLimit-Limit") == "300"

    def test_default_window_is_60(self, client):
        """Default window should be 60.0 seconds."""
        resp = client.get("/api/v1/rate-limit/status")
        assert resp.headers.get("X-RateLimit-Window") == "60.0"

    def test_env_rate_limit(self, monkeypatch):
        """MEMOS_RATE_LIMIT env var overrides default."""
        monkeypatch.setenv("MEMOS_RATE_LIMIT", "500")
        memos = MemOS(backend="memory")
        app = create_fastapi_app(memos=memos)
        c = TestClient(app)
        resp = c.get("/api/v1/rate-limit/status")
        assert resp.headers.get("X-RateLimit-Limit") == "500"

    def test_env_rate_window(self, monkeypatch):
        """MEMOS_RATE_WINDOW env var overrides default."""
        monkeypatch.setenv("MEMOS_RATE_WINDOW", "120.0")
        memos = MemOS(backend="memory")
        app = create_fastapi_app(memos=memos)
        c = TestClient(app)
        resp = c.get("/api/v1/rate-limit/status")
        assert resp.headers.get("X-RateLimit-Window") == "120.0"

    def test_explicit_rate_limit_arg(self):
        """Explicit rate_limit kwarg takes precedence over env."""
        memos = MemOS(backend="memory")
        app = create_fastapi_app(memos=memos, rate_limit=42)
        c = TestClient(app)
        resp = c.get("/api/v1/rate-limit/status")
        assert resp.headers.get("X-RateLimit-Limit") == "42"

    def test_explicit_rate_window_arg(self):
        """Explicit rate_window kwarg takes precedence over env."""
        memos = MemOS(backend="memory")
        app = create_fastapi_app(memos=memos, rate_window=30.0)
        c = TestClient(app)
        resp = c.get("/api/v1/rate-limit/status")
        assert resp.headers.get("X-RateLimit-Window") == "30.0"
