"""Tests for admin API routes — analytics, events, subscriptions, rate-limit,
namespace ACL, multi-agent sharing, mine/conversation, and dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from memos.api import create_fastapi_app
from memos.core import MemOS

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def memos():
    mem = MemOS(backend="memory")
    mem.learn("Python async patterns", tags=["python"], importance=0.8)
    mem.learn("Docker deployment", tags=["devops"], importance=0.6)
    mem.learn("FastAPI routing", tags=["python", "web"], importance=0.7)
    return mem


@pytest.fixture()
def app(memos):
    return create_fastapi_app(memos=memos)


@pytest.fixture()
def client(app):
    return TestClient(app)


# ── Analytics (6 endpoints) ──────────────────────────────────


class TestAnalytics:
    """GET /api/v1/analytics/* endpoints."""

    def test_analytics_top(self, client, memos):
        memos.recall("python", top=5)
        resp = client.get("/api/v1/analytics/top", params={"n": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "results" in data

    def test_analytics_patterns(self, client, memos):
        memos.recall("docker", top=5)
        resp = client.get("/api/v1/analytics/patterns", params={"n": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "results" in data

    def test_analytics_latency(self, client):
        resp = client.get("/api/v1/analytics/latency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "results" in data

    def test_analytics_success_rate(self, client):
        resp = client.get("/api/v1/analytics/success-rate", params={"days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_analytics_daily(self, client):
        resp = client.get("/api/v1/analytics/daily", params={"days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "results" in data

    def test_analytics_zero_result(self, client):
        resp = client.get("/api/v1/analytics/zero-result", params={"n": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "results" in data


# ── Events & Subscriptions (4 endpoints) ─────────────────────


class TestEventsAndSubscriptions:
    """SSE stream, subscriptions CRUD, event stats."""

    def test_event_stream_sse_content_type(self, app):
        import threading

        import httpx
        import uvicorn

        server = threading.Thread(
            target=uvicorn.run,
            args=(app,),
            kwargs={"host": "127.0.0.1", "port": 18765, "log_level": "error"},
            daemon=True,
        )
        server.start()
        import time

        time.sleep(0.5)

        with httpx.stream("GET", "http://127.0.0.1:18765/api/v1/events/stream", timeout=3) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_list_subscriptions(self, client):
        resp = client.get("/api/v1/subscriptions")
        assert resp.status_code == 200
        data = resp.json()
        assert "subscriptions" in data
        assert "total" in data

    def test_delete_subscription_not_found(self, client):
        resp = client.delete("/api/v1/subscriptions/nonexistent-id")
        assert resp.status_code == 404
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND"

    def test_event_stats(self, client):
        resp = client.get("/api/v1/events/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_events" in data
        assert "ws_clients" in data


# ── Rate Limiting (1 endpoint) ───────────────────────────────


class TestRateLimitStatus:
    def test_rate_limit_status_returns_response(self, client):
        resp = client.get("/api/v1/rate-limit/status")
        assert resp.status_code == 422


# ── Namespace ACL (5 endpoints) ──────────────────────────────


class TestNamespaceACL:
    """Grant → list policies → revoke lifecycle."""

    def test_grant_access(self, client):
        resp = client.post(
            "/api/v1/namespaces/project-x/grant",
            json={"agent_id": "agent-alice", "role": "reader"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "policy" in data

    def test_grant_access_missing_fields(self, client):
        resp = client.post(
            "/api/v1/namespaces/project-x/grant",
            json={"agent_id": "agent-alice"},
        )
        assert resp.status_code == 422

    def test_list_namespace_policies(self, client):
        client.post(
            "/api/v1/namespaces/project-y/grant",
            json={"agent_id": "agent-bob", "role": "writer"},
        )
        resp = client.get("/api/v1/namespaces/project-y/policies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["namespace"] == "project-y"
        assert "policies" in data
        assert data["total"] >= 1

    def test_list_all_namespace_policies(self, client):
        client.post(
            "/api/v1/namespaces/ns-a/grant",
            json={"agent_id": "agent-1", "role": "reader"},
        )
        client.post(
            "/api/v1/namespaces/ns-b/grant",
            json={"agent_id": "agent-2", "role": "owner"},
        )
        resp = client.get("/api/v1/namespaces")
        assert resp.status_code == 200
        data = resp.json()
        assert "policies" in data
        assert data["total"] >= 2

    def test_acl_stats(self, client):
        resp = client.get("/api/v1/namespaces/acl/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_revoke_access(self, client):
        client.post(
            "/api/v1/namespaces/project-z/grant",
            json={"agent_id": "agent-carol", "role": "reader"},
        )
        resp = client.post(
            "/api/v1/namespaces/project-z/revoke",
            json={"agent_id": "agent-carol"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_revoke_not_found(self, client):
        resp = client.post(
            "/api/v1/namespaces/nonexistent/revoke",
            json={"agent_id": "ghost-agent"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND"

    def test_revoke_missing_agent_id(self, client):
        resp = client.post(
            "/api/v1/namespaces/project-x/revoke",
            json={},
        )
        assert resp.status_code == 422


# ── Multi-agent Sharing (8 endpoints) ────────────────────────


class TestSharing:
    """Share lifecycle: offer → accept/reject/revoke + export/import.

    MemOS.accept_share uses _agent_id or "default" as acceptor identity,
    so offers must target "default" for accept/reject to succeed.
    """

    def _create_offer(self, client, target="default"):
        return client.post(
            "/api/v1/share/offer",
            json={"target_agent": target},
        ).json()

    def test_share_offer(self, client):
        resp = client.post(
            "/api/v1/share/offer",
            json={"target_agent": "agent-bob"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "share" in data
        share = data["share"]
        assert share["target_agent"] == "agent-bob"
        assert share["status"] == "pending"

    def test_share_offer_invalid_scope(self, client):
        resp = client.post(
            "/api/v1/share/offer",
            json={"target_agent": "agent-bob", "scope": "invalid_scope"},
        )
        assert resp.status_code == 422

    def test_share_accept(self, client):
        offer = self._create_offer(client)
        share_id = offer["share"]["id"]
        resp = client.post(f"/api/v1/share/{share_id}/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["share"]["status"] == "accepted"

    def test_share_accept_wrong_target_is_forbidden(self, client):
        resp = client.post(
            "/api/v1/share/offer",
            json={"target_agent": "other-agent"},
        )
        share_id = resp.json()["share"]["id"]
        resp = client.post(f"/api/v1/share/{share_id}/accept")
        assert resp.status_code == 403
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == "ERROR"

    def test_share_reject(self, client):
        offer = self._create_offer(client)
        share_id = offer["share"]["id"]
        resp = client.post(f"/api/v1/share/{share_id}/reject")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["share"]["status"] == "rejected"

    def test_share_revoke(self, client):
        offer = self._create_offer(client, target="agent-revoke-target")
        share_id = offer["share"]["id"]
        resp = client.post(f"/api/v1/share/{share_id}/revoke")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["share"]["status"] == "revoked"

    def test_share_export_after_accept(self, client, memos):
        memos.learn("exportable memory", tags=["export-test"], importance=0.6)
        offer_resp = client.post(
            "/api/v1/share/offer",
            json={"target_agent": "default", "scope": "tag", "scope_key": "export-test"},
        )
        share_id = offer_resp.json()["share"]["id"]
        client.post(f"/api/v1/share/{share_id}/accept")
        resp = client.get(f"/api/v1/share/{share_id}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "envelope" in data
        assert len(data["envelope"]["memories"]) >= 1

    def test_share_export_not_accepted(self, client):
        offer = self._create_offer(client, target="agent-no-accept")
        share_id = offer["share"]["id"]
        resp = client.get(f"/api/v1/share/{share_id}/export")
        assert resp.status_code == 409
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == "ERROR"

    def test_share_import(self, client, memos):
        item = memos.learn("shared knowledge", tags=["share-test"], importance=0.7)  # noqa: F841
        offer_resp = client.post(
            "/api/v1/share/offer",
            json={"target_agent": "default", "scope": "tag", "scope_key": "share-test"},
        )
        share_id = offer_resp.json()["share"]["id"]
        client.post(f"/api/v1/share/{share_id}/accept")
        export_resp = client.get(f"/api/v1/share/{share_id}/export")
        envelope = export_resp.json()["envelope"]

        resp = client.post("/api/v1/share/import", json={"envelope": envelope})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["imported"] >= 1
        assert len(data["ids"]) >= 1

    def test_share_import_invalid_envelope(self, client):
        resp = client.post("/api/v1/share/import", json={"envelope": {"bad": "data"}})
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == "error"

    def test_shares_list(self, client):
        self._create_offer(client, target="agent-list-target")
        resp = client.get("/api/v1/shares")
        assert resp.status_code == 200
        data = resp.json()
        assert "shares" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_shares_list_filtered_by_status(self, client):
        self._create_offer(client, target="agent-filter-target")
        resp = client.get("/api/v1/shares", params={"status": "pending"})
        assert resp.status_code == 200
        data = resp.json()
        for share in data["shares"]:
            assert share["status"] == "pending"

    def test_sharing_stats(self, client):
        self._create_offer(client, target="agent-stats-target")
        resp = client.get("/api/v1/sharing/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_share_accept_not_found(self, client):
        resp = client.post("/api/v1/share/nonexistent-id/accept")
        assert resp.status_code == 404
        data = resp.json()
        assert data["code"] == "NOT_FOUND"

    def test_share_reject_not_found(self, client):
        resp = client.post("/api/v1/share/nonexistent-id/reject")
        assert resp.status_code == 404
        data = resp.json()
        assert data["code"] == "NOT_FOUND"


# ── Mine Conversation (1 endpoint) ───────────────────────────


class TestMineConversation:
    def test_mine_conversation_with_text(self, client):
        resp = client.post(
            "/api/v1/mine/conversation",
            json={
                "text": "Alice: Let's use FastAPI.\nBob: Good idea.",
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "partial")
        assert "imported" in data
        assert "speakers" in data

    def test_mine_conversation_missing_text_and_path(self, client):
        resp = client.post("/api/v1/mine/conversation", json={})
        assert resp.status_code == 422


# ── Dashboard (1 endpoint) ───────────────────────────────────


class TestShareLifecycleErrors:
    def test_invalid_share_accept_returns_404(self, client):
        resp = client.post("/api/v1/share/not-a-share/accept")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    def test_invalid_share_reject_returns_404(self, client):
        resp = client.post("/api/v1/share/not-a-share/reject")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    def test_invalid_share_revoke_returns_404(self, client):
        resp = client.post("/api/v1/share/not-a-share/revoke")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    def test_invalid_share_export_returns_404(self, client):
        resp = client.get("/api/v1/share/not-a-share/export")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"


class TestDashboard:
    def test_dashboard_returns_html(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
