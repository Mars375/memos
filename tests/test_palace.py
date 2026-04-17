"""Tests for Palace — agent wing creation and discovery."""

import pytest

from memos.palace import PalaceIndex


@pytest.fixture
def palace():
    """In-memory PalaceIndex for testing."""
    with PalaceIndex(":memory:") as p:
        yield p


# ── Wing CRUD ──────────────────────────────────────────────


class TestWingCRUD:
    def test_create_wing(self, palace):
        wing_id = palace.create_wing("project-x")
        assert wing_id
        wing = palace.get_wing("project-x")
        assert wing is not None
        assert wing["name"] == "project-x"

    def test_create_wing_idempotent(self, palace):
        id1 = palace.create_wing("project-x")
        id2 = palace.create_wing("project-x")
        assert id1 == id2

    def test_list_wings(self, palace):
        palace.create_wing("alpha")
        palace.create_wing("beta")
        wings = palace.list_wings()
        names = [w["name"] for w in wings]
        assert "alpha" in names
        assert "beta" in names


# ── Agent wing provisioning ───────────────────────────────


class TestAgentWings:
    def test_ensure_agent_wing_creates_wing_with_colon_prefix(self, palace):
        wing = palace.ensure_agent_wing("mnesia")
        assert wing is not None
        assert wing["name"] == "agent:mnesia"

    def test_ensure_agent_wing_creates_default_rooms(self, palace):
        palace.ensure_agent_wing("mnesia")
        rooms = palace.list_rooms(wing_name="agent:mnesia")
        room_names = [r["name"] for r in rooms]
        assert "diary" in room_names
        assert "context" in room_names
        assert "learnings" in room_names

    def test_ensure_agent_wing_idempotent(self, palace):
        w1 = palace.ensure_agent_wing("mnesia")
        w2 = palace.ensure_agent_wing("mnesia")
        assert w1["id"] == w2["id"]

    def test_list_agent_wings_returns_created_agent(self, palace):
        palace.ensure_agent_wing("mnesia")
        agents = palace.list_agent_wings()
        assert len(agents) == 1
        assert agents[0]["name"] == "mnesia"
        assert agents[0]["wing_id"]

    def test_list_agent_wings_empty_when_no_agents(self, palace):
        palace.create_wing("project-x")
        agents = palace.list_agent_wings()
        assert agents == []

    def test_list_agents_returns_created_agent(self, palace):
        """The core bug: list_agents() must match wings with 'agent:' prefix."""
        palace.ensure_agent_wing("mnesia")
        agents = palace.list_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "mnesia"
        assert agents[0]["wing"]["name"] == "agent:mnesia"

    def test_list_agents_multiple_agents(self, palace):
        palace.ensure_agent_wing("mnesia")
        palace.ensure_agent_wing("hermes")
        palace.ensure_agent_wing("athena")
        agents = palace.list_agents()
        names = [a["name"] for a in agents]
        assert sorted(names) == ["athena", "hermes", "mnesia"]

    def test_list_agents_excludes_non_agent_wings(self, palace):
        palace.create_wing("project-x")
        palace.create_wing("agent")  # no colon — not an agent wing
        palace.ensure_agent_wing("mnesia")
        agents = palace.list_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "mnesia"

    def test_list_agents_with_diary_entries(self, palace):
        palace.ensure_agent_wing("hermes")
        palace.append_diary("hermes", "Refactored the recall engine")
        palace.append_diary("hermes", "Fixed a bug in palace")
        agents = palace.list_agents()
        assert len(agents) == 1
        assert agents[0]["diary_entries"] == 2


# ── Diary ─────────────────────────────────────────────────


class TestDiary:
    def test_write_and_read_diary(self, palace):
        palace.ensure_agent_wing("hermes")
        eid = palace.write_diary("hermes", "Hello world")
        assert eid
        entries = palace.read_diary("hermes")
        assert len(entries) == 1
        assert entries[0]["entry"] == "Hello world"
        assert "agent-diary" in entries[0]["tags"]

    def test_read_diary_newest_first(self, palace):
        palace.write_diary("hermes", "First entry")
        palace.write_diary("hermes", "Second entry")
        entries = palace.read_diary("hermes")
        assert entries[0]["entry"] == "Second entry"
        assert entries[1]["entry"] == "First entry"
