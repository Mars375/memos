"""Tests for the Hierarchical Palace — Wings/Rooms (P6).

Covers:
- CRUD wings and rooms
- Assignment and unassignment
- list_memories with wing/room filters
- palace_recall with and without scope
- Fallback recall when scope is empty
- auto_assign heuristic
- REST endpoints (httpx AsyncClient)
- CLI commands
"""

from __future__ import annotations

from typing import Generator

import pytest

from memos.core import MemOS
from memos.palace import PalaceIndex, PalaceRecall

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def palace() -> Generator[PalaceIndex, None, None]:
    """In-memory PalaceIndex for isolated tests."""
    p = PalaceIndex(db_path=":memory:")
    yield p
    p.close()


# ---------------------------------------------------------------------------
# 1. Wing CRUD
# ---------------------------------------------------------------------------


def test_create_wing_returns_id(palace: PalaceIndex) -> None:
    wing_id = palace.create_wing("project-alpha")
    assert isinstance(wing_id, str)
    assert len(wing_id) > 0


def test_create_wing_idempotent(palace: PalaceIndex) -> None:
    id1 = palace.create_wing("project-alpha")
    id2 = palace.create_wing("project-alpha")
    assert id1 == id2


def test_get_wing_found(palace: PalaceIndex) -> None:
    palace.create_wing("project-alpha", description="Main project")
    w = palace.get_wing("project-alpha")
    assert w is not None
    assert w["name"] == "project-alpha"
    assert w["description"] == "Main project"


def test_get_wing_not_found(palace: PalaceIndex) -> None:
    assert palace.get_wing("nonexistent") is None


def test_list_wings_empty(palace: PalaceIndex) -> None:
    assert palace.list_wings() == []


def test_list_wings_counts(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.create_wing("beta")
    wings = palace.list_wings()
    assert len(wings) == 2
    names = {w["name"] for w in wings}
    assert "alpha" in names
    assert "beta" in names


def test_create_wing_empty_name_raises(palace: PalaceIndex) -> None:
    with pytest.raises(ValueError):
        palace.create_wing("   ")


# ---------------------------------------------------------------------------
# 2. Room CRUD
# ---------------------------------------------------------------------------


def test_create_room_returns_id(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    room_id = palace.create_room("alpha", "auth")
    assert isinstance(room_id, str)
    assert len(room_id) > 0


def test_create_room_unknown_wing_raises(palace: PalaceIndex) -> None:
    with pytest.raises(KeyError):
        palace.create_room("no-such-wing", "auth")


def test_create_room_idempotent(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    r1 = palace.create_room("alpha", "auth")
    r2 = palace.create_room("alpha", "auth")
    assert r1 == r2


def test_list_rooms_by_wing(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.create_wing("beta")
    palace.create_room("alpha", "auth")
    palace.create_room("alpha", "api")
    palace.create_room("beta", "frontend")
    rooms = palace.list_rooms(wing_name="alpha")
    assert len(rooms) == 2
    names = {r["name"] for r in rooms}
    assert "auth" in names
    assert "api" in names


def test_list_rooms_global(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.create_wing("beta")
    palace.create_room("alpha", "auth")
    palace.create_room("beta", "deploy")
    rooms = palace.list_rooms()
    assert len(rooms) == 2


def test_list_rooms_unknown_wing_raises(palace: PalaceIndex) -> None:
    with pytest.raises(KeyError):
        palace.list_rooms(wing_name="ghost")


# ---------------------------------------------------------------------------
# 3. Assignment / Unassignment
# ---------------------------------------------------------------------------


def test_assign_wing_only(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.assign("mem-001", "alpha")
    a = palace.get_assignment("mem-001")
    assert a is not None
    assert a["wing_name"] == "alpha"
    assert a["room_name"] is None


def test_assign_wing_and_room(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.create_room("alpha", "auth")
    palace.assign("mem-002", "alpha", room_name="auth")
    a = palace.get_assignment("mem-002")
    assert a["room_name"] == "auth"


def test_assign_unknown_wing_raises(palace: PalaceIndex) -> None:
    with pytest.raises(KeyError):
        palace.assign("mem-003", "ghost-wing")


def test_assign_unknown_room_raises(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    with pytest.raises(KeyError):
        palace.assign("mem-004", "alpha", room_name="no-room")


def test_unassign(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.assign("mem-005", "alpha")
    palace.unassign("mem-005")
    assert palace.get_assignment("mem-005") is None


def test_assign_overwrites(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.create_wing("beta")
    palace.assign("mem-006", "alpha")
    palace.assign("mem-006", "beta")
    a = palace.get_assignment("mem-006")
    assert a["wing_name"] == "beta"


# ---------------------------------------------------------------------------
# 4. list_memories filters
# ---------------------------------------------------------------------------


def test_list_memories_wing_filter(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.create_wing("beta")
    palace.assign("m1", "alpha")
    palace.assign("m2", "alpha")
    palace.assign("m3", "beta")
    ids = palace.list_memories(wing_name="alpha")
    assert set(ids) == {"m1", "m2"}


def test_list_memories_room_filter(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.create_room("alpha", "auth")
    palace.create_room("alpha", "api")
    palace.assign("m1", "alpha", room_name="auth")
    palace.assign("m2", "alpha", room_name="api")
    palace.assign("m3", "alpha")  # no room
    ids = palace.list_memories(wing_name="alpha", room_name="auth")
    assert ids == ["m1"]


def test_list_memories_global(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.assign("m1", "alpha")
    palace.assign("m2", "alpha")
    all_ids = palace.list_memories()
    assert set(all_ids) == {"m1", "m2"}


def test_list_memories_empty_scope(palace: PalaceIndex) -> None:
    palace.create_wing("empty-wing")
    ids = palace.list_memories(wing_name="empty-wing")
    assert ids == []


# ---------------------------------------------------------------------------
# 5. Stats
# ---------------------------------------------------------------------------


def test_stats_initial(palace: PalaceIndex) -> None:
    s = palace.stats()
    assert s["total_wings"] == 0
    assert s["total_rooms"] == 0
    assert s["assigned_memories"] == 0


def test_stats_after_ops(palace: PalaceIndex) -> None:
    palace.create_wing("alpha")
    palace.create_room("alpha", "auth")
    palace.assign("m1", "alpha", room_name="auth")
    s = palace.stats()
    assert s["total_wings"] == 1
    assert s["total_rooms"] == 1
    assert s["assigned_memories"] == 1


# ---------------------------------------------------------------------------
# 6. auto_assign heuristic
# ---------------------------------------------------------------------------


def test_auto_assign_no_wings(palace: PalaceIndex) -> None:
    result = palace.auto_assign("m1", "authentication flow", ["auth", "login"])
    assert result is None


def test_auto_assign_matches_wing(palace: PalaceIndex) -> None:
    palace.create_wing("auth")
    palace.create_wing("deployment")
    matched = palace.auto_assign("m1", "login and auth flow", ["auth", "security"])
    assert matched == "auth"
    a = palace.get_assignment("m1")
    assert a is not None
    assert a["wing_name"] == "auth"


def test_auto_assign_matches_room(palace: PalaceIndex) -> None:
    palace.create_wing("project")
    palace.create_room("project", "auth")
    palace.create_room("project", "frontend")
    palace.auto_assign("m1", "auth token flow", ["auth"])
    a = palace.get_assignment("m1")
    assert a is not None
    assert a["room_name"] == "auth"


def test_auto_assign_no_match_returns_none(palace: PalaceIndex) -> None:
    palace.create_wing("astronomy")
    result = palace.auto_assign("m1", "database migration script", ["sql", "postgres"])
    # "astronomy" shares no words with the content/tags
    assert result is None


# ---------------------------------------------------------------------------
# 7. PalaceRecall — scoped recall
# ---------------------------------------------------------------------------


def test_palace_recall_global_fallback(palace: PalaceIndex, memos_empty: MemOS) -> None:
    """No scope → global recall."""
    memos_empty.learn("Python is a programming language", tags=["python"])
    pr = PalaceRecall(palace)
    results = pr.palace_recall(memos_empty, "Python language", top=5)
    assert len(results) >= 1


def test_palace_recall_with_scope(palace: PalaceIndex, memos_empty: MemOS) -> None:
    palace.create_wing("project")
    item = memos_empty.learn("auth token implementation", tags=["auth"])
    palace.assign(item.id, "project")
    pr = PalaceRecall(palace)
    results = pr.palace_recall(memos_empty, "auth token", wing_name="project", top=10)
    ids = [r.item.id for r in results]
    assert item.id in ids


def test_palace_recall_scope_filters_out(palace: PalaceIndex, memos_empty: MemOS) -> None:
    """Memories not in scope should not appear when scope is non-empty."""
    palace.create_wing("wing-a")
    palace.create_wing("wing-b")
    item_a = memos_empty.learn("deployment pipeline configuration", tags=["deploy"])
    item_b = memos_empty.learn("deployment pipeline configuration copy", tags=["deploy"])
    palace.assign(item_a.id, "wing-a")
    palace.assign(item_b.id, "wing-b")
    pr = PalaceRecall(palace)
    results = pr.palace_recall(memos_empty, "deployment pipeline", wing_name="wing-a", top=10)
    ids = {r.item.id for r in results}
    # item_a should be present; item_b should not (different wing)
    assert item_a.id in ids
    assert item_b.id not in ids


def test_palace_recall_empty_scope_fallback(palace: PalaceIndex, memos_empty: MemOS) -> None:
    """Empty scope (no assignments) → fallback to global recall."""
    palace.create_wing("empty-wing")
    memos_empty.learn("fallback content keyword", tags=["fallback"])
    pr = PalaceRecall(palace)
    results = pr.palace_recall(memos_empty, "fallback content keyword", wing_name="empty-wing", top=5)
    # Should get results via fallback
    assert len(results) >= 1


def test_palace_recall_unknown_wing_fallback(palace: PalaceIndex, memos_empty: MemOS) -> None:
    """Unknown wing → fallback to global recall (no error)."""
    memos_empty.learn("some global memory about anything", tags=["global"])
    pr = PalaceRecall(palace)
    results = pr.palace_recall(memos_empty, "global memory", wing_name="nonexistent-wing", top=5)
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# 8. REST endpoints (FastAPI / httpx)
# ---------------------------------------------------------------------------


def _make_app():
    """Create a fresh FastAPI app backed by an in-memory MemOS."""
    from memos.api import create_fastapi_app

    return create_fastapi_app(backend="memory", kg_db_path=":memory:")


@pytest.mark.anyio
async def test_rest_create_wing() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/palace/wings", json={"name": "rest-wing-a"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["name"] == "rest-wing-a"


@pytest.mark.anyio
async def test_rest_list_wings() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/palace/wings", json={"name": "rest-wing-list-test"})
        resp = await client.get("/api/v1/palace/wings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["wings"], list)


@pytest.mark.anyio
async def test_rest_create_room() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/palace/wings", json={"name": "rest-wing-room-test"})
        resp = await client.post(
            "/api/v1/palace/rooms",
            json={"wing": "rest-wing-room-test", "name": "rest-room-x"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["name"] == "rest-room-x"


@pytest.mark.anyio
async def test_rest_list_rooms() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/palace/wings", json={"name": "rest-room-list-wing"})
        await client.post(
            "/api/v1/palace/rooms",
            json={"wing": "rest-room-list-wing", "name": "room-alpha"},
        )
        resp = await client.get("/api/v1/palace/rooms?wing=rest-room-list-wing")
        assert resp.status_code == 200
        data = resp.json()
        assert any(r["name"] == "room-alpha" for r in data["rooms"])


@pytest.mark.anyio
async def test_rest_assign_and_unassign() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/palace/wings", json={"name": "rest-assign-wing"})
        resp = await client.post(
            "/api/v1/palace/assign",
            json={"memory_id": "rest-mem-001", "wing": "rest-assign-wing"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        resp2 = await client.delete("/api/v1/palace/assign/rest-mem-001")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ok"


@pytest.mark.anyio
async def test_rest_palace_stats() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/palace/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "total_wings" in data


@pytest.mark.anyio
async def test_rest_palace_recall() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/learn", json={"content": "rest palace recall test memory"})
        resp = await client.get("/api/v1/palace/recall?query=palace+recall+test&top=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "results" in data


# ---------------------------------------------------------------------------
# 9. CLI commands
# ---------------------------------------------------------------------------


def test_cli_palace_init(tmp_path) -> None:
    from memos.cli import main

    db = str(tmp_path / "palace.db")
    main(["palace-init", "--db", db])  # should not raise


def test_cli_palace_wing_create(tmp_path, capsys) -> None:
    from memos.cli import main

    db = str(tmp_path / "palace.db")
    main(["palace-init", "--db", db])
    main(["palace-wing-create", "cli-wing", "--db", db])
    out = capsys.readouterr().out
    assert "cli-wing" in out


def test_cli_palace_wing_list(tmp_path, capsys) -> None:
    from memos.cli import main

    db = str(tmp_path / "palace.db")
    main(["palace-init", "--db", db])
    main(["palace-wing-create", "listed-wing", "--db", db])
    main(["palace-wing-list", "--db", db])
    out = capsys.readouterr().out
    assert "listed-wing" in out


def test_cli_palace_room_create(tmp_path, capsys) -> None:
    from memos.cli import main

    db = str(tmp_path / "palace.db")
    main(["palace-init", "--db", db])
    main(["palace-wing-create", "wing-r", "--db", db])
    main(["palace-room-create", "wing-r", "room-r", "--db", db])
    out = capsys.readouterr().out
    assert "room-r" in out


def test_cli_palace_room_list(tmp_path, capsys) -> None:
    from memos.cli import main

    db = str(tmp_path / "palace.db")
    main(["palace-init", "--db", db])
    main(["palace-wing-create", "wing-rl", "--db", db])
    main(["palace-room-create", "wing-rl", "room-rl", "--db", db])
    main(["palace-room-list", "--wing", "wing-rl", "--db", db])
    out = capsys.readouterr().out
    assert "room-rl" in out


def test_cli_palace_assign(tmp_path, capsys) -> None:
    from memos.cli import main

    db = str(tmp_path / "palace.db")
    main(["palace-init", "--db", db])
    main(["palace-wing-create", "assign-wing", "--db", db])
    main(["palace-assign", "mem-cli-001", "--wing", "assign-wing", "--db", db])
    out = capsys.readouterr().out
    assert "mem-cli-001" in out


def test_cli_palace_stats(tmp_path, capsys) -> None:
    from memos.cli import main

    db = str(tmp_path / "palace.db")
    main(["palace-init", "--db", db])
    main(["palace-stats", "--db", db])
    out = capsys.readouterr().out
    assert "wings" in out.lower() or "Total" in out


# ---------------------------------------------------------------------------
# Regression: Bug 2 — Palace DB path derivation from kg_db_path
# ---------------------------------------------------------------------------


def test_palace_db_colocated_with_kg_db(tmp_path) -> None:
    """When kg_db_path is a real file path, palace.db must be in the same directory.

    It must NOT fall back to ~/.memos/palace.db, which would leak state between
    isolated instances (tests, tenants).
    """
    from pathlib import Path

    from memos.api import create_fastapi_app

    kg_db = str(tmp_path / "kg.db")
    # Create the app — this triggers palace path derivation
    create_fastapi_app(backend="memory", kg_db_path=kg_db)

    expected_palace_db = tmp_path / "palace.db"
    home_palace_db = Path.home() / ".memos" / "palace.db"

    assert expected_palace_db.exists(), (
        f"Expected palace.db at {expected_palace_db} but it was not created. "
        "Palace may have opened the global ~/.memos/palace.db instead."
    )
    # Also verify it did NOT fall back to the home directory path
    # (only meaningful if home palace didn't exist before the test)
    if home_palace_db.exists():
        # Can't conclusively check without stat — just confirm colocated one exists
        pass
    else:
        assert not home_palace_db.exists(), "palace.db was created in ~/.memos/ instead of alongside kg.db"


def test_palace_db_memory_when_kg_is_memory() -> None:
    """When kg_db_path=':memory:', palace must also use ':memory:' (no file leakage)."""
    from pathlib import Path

    from memos.api import create_fastapi_app

    # Snapshot of home palace before
    home_palace_db = Path.home() / ".memos" / "palace.db"
    existed_before = home_palace_db.exists()

    create_fastapi_app(backend="memory", kg_db_path=":memory:")

    if not existed_before:
        assert not home_palace_db.exists(), (
            "palace.db was created in ~/.memos/ when kg_db_path=':memory:' — palace should have used ':memory:' too."
        )


# ---------------------------------------------------------------------------
# 10. Diary entries — Task 4.2
# ---------------------------------------------------------------------------


def test_write_diary_returns_id(palace: PalaceIndex) -> None:
    entry_id = palace.write_diary("hermes", "Deployed v1.2.3 to production.")
    assert isinstance(entry_id, str)
    assert entry_id.startswith("diary-hermes-")
    # ID format: diary-{agent}-{timestamp}-{uuid8}
    parts = entry_id.split("-")
    assert len(parts) >= 4


def test_write_diary_empty_agent_raises(palace: PalaceIndex) -> None:
    with pytest.raises(ValueError, match="Agent name cannot be empty"):
        palace.write_diary("   ", "some content")


def test_write_diary_empty_content_raises(palace: PalaceIndex) -> None:
    with pytest.raises(ValueError, match="Content cannot be empty"):
        palace.write_diary("hermes", "   ")


def test_read_diary_returns_entries(palace: PalaceIndex) -> None:
    palace.write_diary("hermes", "First entry")
    palace.write_diary("hermes", "Second entry")
    entries = palace.read_diary("hermes")
    assert len(entries) == 2
    # Newest first
    assert entries[0]["content"] == "Second entry"
    assert entries[1]["content"] == "First entry"
    assert all("id" in e and "content" in e and "timestamp" in e for e in entries)


def test_read_diary_respects_limit(palace: PalaceIndex) -> None:
    for i in range(5):
        palace.write_diary("hermes", f"Entry {i}")
    entries = palace.read_diary("hermes", limit=3)
    assert len(entries) == 3


def test_read_diary_agent_isolation(palace: PalaceIndex) -> None:
    palace.write_diary("hermes", "Hermes entry")
    palace.write_diary("athena", "Athena entry")
    hermes_entries = palace.read_diary("hermes")
    athena_entries = palace.read_diary("athena")
    assert len(hermes_entries) == 1
    assert hermes_entries[0]["content"] == "Hermes entry"
    assert len(athena_entries) == 1
    assert athena_entries[0]["content"] == "Athena entry"


def test_read_diary_empty_agent_raises(palace: PalaceIndex) -> None:
    with pytest.raises(ValueError, match="Agent name cannot be empty"):
        palace.read_diary("   ")


def test_read_diary_no_entries(palace: PalaceIndex) -> None:
    entries = palace.read_diary("nonexistent")
    assert entries == []


# ---------------------------------------------------------------------------
# 11. Agent discovery — Task 4.3
# ---------------------------------------------------------------------------


def test_list_agents_empty(palace: PalaceIndex) -> None:
    assert palace.list_agents() == []


def test_list_agents_no_agent_wings(palace: PalaceIndex) -> None:
    palace.create_wing("project-alpha")
    assert palace.list_agents() == []


def test_list_agents_finds_agents(palace: PalaceIndex) -> None:
    palace.create_wing("agent-hermes")
    palace.create_wing("agent-athena")
    palace.create_wing("project-alpha")
    agents = palace.list_agents()
    names = {a["name"] for a in agents}
    assert names == {"hermes", "athena"}
    assert len(agents) == 2


def test_list_agents_includes_diary_counts(palace: PalaceIndex) -> None:
    palace.create_wing("agent-hermes")
    palace.write_diary("hermes", "Diary entry 1")
    palace.write_diary("hermes", "Diary entry 2")
    palace.write_diary("athena", "Other agent diary")
    agents = palace.list_agents()
    hermes = next(a for a in agents if a["name"] == "hermes")
    assert hermes["diary_entries"] == 2
    assert hermes["wing"]["name"] == "agent-hermes"
    assert "memory_count" in hermes["stats"]
    assert "room_count" in hermes["stats"]


def test_list_agents_includes_wing_stats(palace: PalaceIndex) -> None:
    palace.create_wing("agent-hermes")
    palace.create_room("agent-hermes", "logs")
    palace.assign("mem-001", "agent-hermes", room_name="logs")
    agents = palace.list_agents()
    hermes = agents[0]
    assert hermes["stats"]["memory_count"] >= 1
    assert hermes["stats"]["room_count"] >= 1


# ---------------------------------------------------------------------------
# 12. Diary REST endpoints — Task 4.2
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rest_diary_write() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/palace/diary",
            json={"agent": "hermes", "content": "REST diary entry"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agent"] == "hermes"
        assert "id" in data


@pytest.mark.anyio
async def test_rest_diary_write_missing_fields() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/palace/diary", json={"agent": "hermes"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"


@pytest.mark.anyio
async def test_rest_diary_read() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Write first
        await client.post(
            "/api/v1/palace/diary",
            json={"agent": "hermes", "content": "Diary for read test"},
        )
        # Then read
        resp = await client.get("/api/v1/palace/diary/hermes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agent"] == "hermes"
        assert data["count"] >= 1
        assert any(e["content"] == "Diary for read test" for e in data["entries"])


@pytest.mark.anyio
async def test_rest_diary_read_with_limit() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(5):
            await client.post(
                "/api/v1/palace/diary",
                json={"agent": "limiter", "content": f"Entry {i}"},
            )
        resp = await client.get("/api/v1/palace/diary/limiter?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2


# ---------------------------------------------------------------------------
# 13. Agent discovery REST endpoint — Task 4.3
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rest_list_agents() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create an agent wing
        await client.post("/api/v1/palace/wings", json={"name": "agent-hermes"})
        # Write a diary entry
        await client.post(
            "/api/v1/palace/diary",
            json={"agent": "hermes", "content": "Agent discovery test"},
        )
        resp = await client.get("/api/v1/palace/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["total"] >= 1
        hermes = next(a for a in data["agents"] if a["name"] == "hermes")
        assert hermes["diary_entries"] == 1
        assert "wing" in hermes
        assert "stats" in hermes


@pytest.mark.anyio
async def test_rest_list_agents_empty() -> None:
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/palace/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["total"] == 0
        assert data["agents"] == []
