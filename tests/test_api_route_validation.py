"""Validation and error-shape tests for admin and knowledge API routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from memos.api import create_fastapi_app
from memos.core import MemOS


@pytest.fixture()
def memos():
    mem = MemOS(backend="memory")
    mem.learn("Alice works on MemOS", tags=["people", "memos"], importance=0.8)
    return mem


@pytest.fixture()
def client(memos):
    app = create_fastapi_app(memos=memos, kg_db_path=":memory:")
    return TestClient(app)


class TestKnowledgeRouteValidation:
    def test_kg_add_fact_missing_object_returns_422(self, client):
        resp = client.post(
            "/api/v1/kg/facts",
            json={"subject": "Alice", "predicate": "works_at"},
        )

        assert resp.status_code == 422

    def test_brain_search_missing_query_returns_422(self, client):
        resp = client.post("/api/v1/brain/search", json={"top_k": 5})

        assert resp.status_code == 422

    def test_palace_create_wing_missing_name_returns_422(self, client):
        resp = client.post("/api/v1/palace/wings", json={"description": "ops"})

        assert resp.status_code == 422

    def test_context_set_identity_missing_content_returns_422(self, client):
        resp = client.post("/api/v1/context/identity", json={})

        assert resp.status_code == 422

    def test_palace_create_room_missing_wing_returns_422(self, client):
        resp = client.post("/api/v1/palace/rooms", json={"name": "ops"})

        assert resp.status_code == 422

    def test_palace_assign_missing_memory_id_returns_422(self, client):
        resp = client.post("/api/v1/palace/assign", json={"wing": "agent:alice"})

        assert resp.status_code == 422

    def test_palace_write_diary_missing_entry_returns_422(self, client):
        resp = client.post("/api/v1/palace/diary", json={"agent_name": "alice"})

        assert resp.status_code == 422

    def test_palace_provision_agent_missing_name_returns_422(self, client):
        resp = client.post("/api/v1/palace/agents", json={"description": "ops"})

        assert resp.status_code == 422

    def test_wiki_create_page_missing_entity_returns_422(self, client):
        resp = client.post("/api/v1/wiki/pages", json={"content": "hello"})

        assert resp.status_code == 422

    def test_wiki_read_page_unknown_slug_returns_404(self, client):
        resp = client.get("/api/v1/wiki/page/unknown-page")

        assert resp.status_code == 404
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND"


class TestAdminRouteValidation:
    def test_ingest_url_missing_url_returns_422(self, client):
        resp = client.post("/api/v1/ingest/url", json={"dry_run": True})

        assert resp.status_code == 422

    def test_acl_grant_missing_role_returns_422(self, client):
        resp = client.post(
            "/api/v1/namespaces/project-x/grant",
            json={"agent_id": "agent-alice"},
        )

        assert resp.status_code == 422

    def test_acl_revoke_missing_agent_id_returns_422(self, client):
        resp = client.post("/api/v1/namespaces/project-x/revoke", json={})

        assert resp.status_code == 422

    def test_delete_subscription_not_found_returns_404(self, client):
        resp = client.delete("/api/v1/subscriptions/nonexistent-id")

        assert resp.status_code == 404
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == "NOT_FOUND"

    def test_share_offer_missing_target_agent_returns_422(self, client):
        resp = client.post("/api/v1/share/offer", json={})

        assert resp.status_code == 422

    def test_share_import_missing_envelope_returns_422(self, client):
        resp = client.post("/api/v1/share/import", json={})

        assert resp.status_code == 422

    def test_mine_conversation_missing_text_and_path_returns_422(self, client):
        resp = client.post("/api/v1/mine/conversation", json={})

        assert resp.status_code == 422
