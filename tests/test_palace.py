"""Tests for PalaceIndex diary append and retrieval (Task 4.2)."""

from __future__ import annotations

import json
import time

import pytest

from memos.palace import PalaceIndex


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def palace():
    """In-memory PalaceIndex for testing."""
    p = PalaceIndex(":memory:")
    yield p
    p.close()


# ---------------------------------------------------------------------------
# append_diary
# ---------------------------------------------------------------------------


class TestAppendDiary:
    def test_basic_append(self, palace: PalaceIndex):
        entry_id = palace.append_diary("hermes", "Completed task 4.2")
        assert entry_id
        assert entry_id.startswith("diary-hermes-")

    def test_returns_string_id(self, palace: PalaceIndex):
        entry_id = palace.append_diary("hermes", "Some entry")
        assert isinstance(entry_id, str)

    def test_empty_agent_raises(self, palace: PalaceIndex):
        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            palace.append_diary("  ", "content")

    def test_empty_entry_raises(self, palace: PalaceIndex):
        with pytest.raises(ValueError, match="Entry content cannot be empty"):
            palace.append_diary("hermes", "   ")

    def test_default_agent_diary_tag(self, palace: PalaceIndex):
        palace.append_diary("hermes", "An entry")
        entries = palace.read_diary("hermes")
        assert len(entries) == 1
        assert "agent-diary" in entries[0]["tags"]

    def test_extra_tags(self, palace: PalaceIndex):
        palace.append_diary("hermes", "Tagged entry", tags=["milestone", "release"])
        entries = palace.read_diary("hermes")
        assert len(entries) == 1
        assert "agent-diary" in entries[0]["tags"]
        assert "milestone" in entries[0]["tags"]
        assert "release" in entries[0]["tags"]

    def test_no_tags_still_has_agent_diary(self, palace: PalaceIndex):
        palace.append_diary("hermes", "No extra tags")
        entries = palace.read_diary("hermes")
        assert entries[0]["tags"] == ["agent-diary"]

    def test_none_tags_still_has_agent_diary(self, palace: PalaceIndex):
        palace.append_diary("hermes", "None tags", tags=None)
        entries = palace.read_diary("hermes")
        assert entries[0]["tags"] == ["agent-diary"]

    def test_write_diary_delegates_to_append_diary(self, palace: PalaceIndex):
        """Legacy write_diary should still work and use append_diary under the hood."""
        entry_id = palace.write_diary("hermes", "Legacy call")
        assert entry_id
        entries = palace.read_diary("hermes")
        assert len(entries) == 1
        assert entries[0]["entry"] == "Legacy call"
        assert "agent-diary" in entries[0]["tags"]

    def test_write_diary_with_tags(self, palace: PalaceIndex):
        entry_id = palace.write_diary("hermes", "Tagged legacy", tags=["old-api"])
        entries = palace.read_diary("hermes")
        assert "old-api" in entries[0]["tags"]


# ---------------------------------------------------------------------------
# read_diary
# ---------------------------------------------------------------------------


class TestReadDiary:
    def test_read_returns_entry_dict(self, palace: PalaceIndex):
        palace.append_diary("hermes", "Hello diary")
        entries = palace.read_diary("hermes")
        assert len(entries) == 1
        e = entries[0]
        assert "id" in e
        assert e["agent_name"] == "hermes"
        assert e["entry"] == "Hello diary"
        assert isinstance(e["tags"], list)
        assert isinstance(e["created_at"], float)

    def test_limit_parameter(self, palace: PalaceIndex):
        for i in range(5):
            palace.append_diary("hermes", f"Entry {i}")
        entries = palace.read_diary("hermes", limit=3)
        assert len(entries) == 3

    def test_ordering_newest_first(self, palace: PalaceIndex):
        palace.append_diary("hermes", "First entry")
        time.sleep(0.01)
        palace.append_diary("hermes", "Second entry")
        time.sleep(0.01)
        palace.append_diary("hermes", "Third entry")
        entries = palace.read_diary("hermes")
        assert entries[0]["entry"] == "Third entry"
        assert entries[1]["entry"] == "Second entry"
        assert entries[2]["entry"] == "First entry"

    def test_empty_result_for_unknown_agent(self, palace: PalaceIndex):
        entries = palace.read_diary("nonexistent")
        assert entries == []

    def test_empty_agent_raises(self, palace: PalaceIndex):
        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            palace.read_diary("  ")

    def test_entries_have_agent_diary_tag(self, palace: PalaceIndex):
        palace.append_diary("hermes", "Entry 1", tags=["custom"])
        palace.append_diary("hermes", "Entry 2")
        entries = palace.read_diary("hermes")
        assert all("agent-diary" in e["tags"] for e in entries)

    def test_multiple_agents_isolated(self, palace: PalaceIndex):
        palace.append_diary("hermes", "Hermes entry")
        palace.append_diary("athena", "Athena entry")
        hermes_entries = palace.read_diary("hermes")
        athena_entries = palace.read_diary("athena")
        assert len(hermes_entries) == 1
        assert len(athena_entries) == 1
        assert hermes_entries[0]["agent_name"] == "hermes"
        assert athena_entries[0]["agent_name"] == "athena"


# ---------------------------------------------------------------------------
# ensure_agent_wing integration
# ---------------------------------------------------------------------------


class TestAgentWingIntegration:
    def test_ensure_agent_wing(self, palace: PalaceIndex):
        wing = palace.ensure_agent_wing("hermes")
        assert wing is not None
        assert wing["name"] == "agent:hermes"

    def test_diary_and_wing_coexist(self, palace: PalaceIndex):
        palace.ensure_agent_wing("hermes")
        entry_id = palace.append_diary("hermes", "Diary with wing")
        entries = palace.read_diary("hermes")
        assert len(entries) == 1
        assert entries[0]["entry"] == "Diary with wing"


# ---------------------------------------------------------------------------
# API endpoint tests (using TestClient)
# ---------------------------------------------------------------------------


class TestDiaryAPIEndpoints:
    @pytest.fixture
    def client(self):
        """Create a FastAPI TestClient with palace diary routes."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from memos.api.routes.knowledge import create_knowledge_router
        from memos.core import MemOS
        from memos.palace import PalaceIndex

        app = FastAPI()
        memos = MemOS(backend="memory")
        palace = PalaceIndex(":memory:")
        memos._palace = palace

        from memos.context import ContextStack
        from memos.knowledge_graph import KnowledgeGraph

        context_stack = ContextStack(memos)
        kg = KnowledgeGraph()

        router = create_knowledge_router(memos, kg, palace, context_stack)
        app.include_router(router)

        client = TestClient(app)
        yield client
        palace.close()

    def test_post_diary_append(self, client):
        resp = client.post(
            "/api/v1/palace/diary",
            json={"agent_name": "hermes", "entry": "API diary entry"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agent_name"] == "hermes"
        assert data["id"]

    def test_post_diary_with_tags(self, client):
        resp = client.post(
            "/api/v1/palace/diary",
            json={"agent_name": "hermes", "entry": "Tagged entry", "tags": ["milestone"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        # Read back and verify tags
        read_resp = client.get("/api/v1/palace/diary/hermes")
        entries = read_resp.json()["entries"]
        assert len(entries) == 1
        assert "agent-diary" in entries[0]["tags"]
        assert "milestone" in entries[0]["tags"]

    def test_get_diary_read(self, client):
        client.post(
            "/api/v1/palace/diary",
            json={"agent_name": "athena", "entry": "First entry"},
        )
        client.post(
            "/api/v1/palace/diary",
            json={"agent_name": "athena", "entry": "Second entry"},
        )
        resp = client.get("/api/v1/palace/diary/athena")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agent_name"] == "athena"
        assert data["count"] == 2
        # Newest first
        assert data["entries"][0]["entry"] == "Second entry"

    def test_get_diary_with_limit(self, client):
        for i in range(5):
            client.post(
                "/api/v1/palace/diary",
                json={"agent_name": "hermes", "entry": f"Entry {i}"},
            )
        resp = client.get("/api/v1/palace/diary/hermes?limit=2")
        data = resp.json()
        assert data["count"] == 2

    def test_post_diary_missing_fields(self, client):
        resp = client.post("/api/v1/palace/diary", json={"agent_name": "hermes"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"

    def test_get_diary_empty_agent(self, client):
        resp = client.get("/api/v1/palace/diary/nonexistent")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["count"] == 0

    def test_backward_compat_agent_content_fields(self, client):
        """Old field names (agent, content) should still work."""
        resp = client.post(
            "/api/v1/palace/diary",
            json={"agent": "legacy-agent", "content": "Legacy content"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agent_name"] == "legacy-agent"


# ---------------------------------------------------------------------------
# MCP dispatch: palace_list_agents (Task 4.3)
# ---------------------------------------------------------------------------


class TestMCPListAgents:
    def test_dispatch_palace_list_agents_no_agents(self):
        """MCP dispatch returns 'no agents' when palace is empty."""
        from unittest.mock import MagicMock

        from memos.mcp_server import _dispatch

        memos = MagicMock(spec=[])
        palace = PalaceIndex(":memory:")
        memos._palace = palace

        r = _dispatch(memos, "palace_list_agents", {})
        assert not r.get("isError")
        assert "No agents found" in r["content"][0]["text"]
        palace.close()

    def test_dispatch_palace_list_agents_with_agents(self):
        """MCP dispatch returns formatted agent list."""
        from unittest.mock import MagicMock

        from memos.mcp_server import _dispatch

        memos = MagicMock(spec=[])
        palace = PalaceIndex(":memory:")
        memos._palace = palace

        # Provision two agent wings
        palace.ensure_agent_wing("hermes")
        palace.ensure_agent_wing("athena")

        r = _dispatch(memos, "palace_list_agents", {})
        assert not r.get("isError")
        text = r["content"][0]["text"]
        assert "Found 2 agent(s)" in text
        assert "hermes" in text
        assert "athena" in text
        assert "wing_id=" in text
        assert "diary_count=0" in text
        palace.close()

    def test_dispatch_palace_list_agents_no_palace(self):
        """MCP dispatch returns error when no palace is attached."""
        from unittest.mock import MagicMock

        from memos.mcp_server import _dispatch

        memos = MagicMock(spec=[])  # no _palace attribute
        r = _dispatch(memos, "palace_list_agents", {})
        assert r.get("isError")
        assert "Palace index not available" in r["content"][0]["text"]
