"""Tests for the temporal knowledge graph (P5).

Covers:
- CRUD operations
- Temporal queries (valid_from / valid_to)
- Invalidation
- Timeline ordering
- Predicate query
- Stats
- CLI command dispatch
- REST endpoints (httpx AsyncClient)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Generator

import pytest

from memos.knowledge_graph import KnowledgeGraph, _parse_date


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def kg() -> Generator[KnowledgeGraph, None, None]:
    """In-memory KnowledgeGraph for tests."""
    graph = KnowledgeGraph(db_path=":memory:")
    yield graph
    graph.close()


# ---------------------------------------------------------------------------
# 1. add_fact — basic
# ---------------------------------------------------------------------------


def test_add_fact_returns_id(kg: KnowledgeGraph) -> None:
    fact_id = kg.add_fact("Alice", "knows", "Bob")
    assert isinstance(fact_id, str)
    assert len(fact_id) == 8


def test_add_fact_stored(kg: KnowledgeGraph) -> None:
    kg.add_fact("Alice", "knows", "Bob")
    facts = kg.query("Alice", direction="subject")
    assert len(facts) == 1
    assert facts[0]["subject"] == "Alice"
    assert facts[0]["predicate"] == "knows"
    assert facts[0]["object"] == "Bob"


def test_add_fact_confidence_default(kg: KnowledgeGraph) -> None:
    kg.add_fact("X", "rel", "Y")
    facts = kg.query("X")
    assert facts[0]["confidence"] == 1.0


def test_add_fact_custom_confidence(kg: KnowledgeGraph) -> None:
    kg.add_fact("X", "rel", "Y", confidence=0.7)
    facts = kg.query("X")
    assert abs(facts[0]["confidence"] - 0.7) < 0.001


def test_add_fact_with_source(kg: KnowledgeGraph) -> None:
    kg.add_fact("Alice", "born_in", "Paris", source="wikipedia")
    facts = kg.query("Alice")
    assert facts[0]["source"] == "wikipedia"


# ---------------------------------------------------------------------------
# 2. Temporal queries
# ---------------------------------------------------------------------------


def test_add_fact_valid_from(kg: KnowledgeGraph) -> None:
    future = time.time() + 3600  # 1h from now
    kg.add_fact("A", "rel", "B", valid_from=future)
    # querying now — fact is NOT yet valid
    facts = kg.query("A", time=time.time())
    assert len(facts) == 0


def test_add_fact_valid_to_expired(kg: KnowledgeGraph) -> None:
    past = time.time() - 3600  # 1h ago
    kg.add_fact("A", "rel", "B", valid_to=past)
    # querying now — fact has expired
    facts = kg.query("A", time=time.time())
    assert len(facts) == 0


def test_add_fact_temporal_active(kg: KnowledgeGraph) -> None:
    yesterday = time.time() - 86400
    tomorrow = time.time() + 86400
    kg.add_fact("A", "rel", "B", valid_from=yesterday, valid_to=tomorrow)
    facts = kg.query("A", time=time.time())
    assert len(facts) == 1


def test_query_at_historical_time(kg: KnowledgeGraph) -> None:
    past = time.time() - 86400  # yesterday
    present = time.time()
    kg.add_fact("A", "rel", "B", valid_from=past, valid_to=present + 3600)
    # Query at a point in the past (1 hour ago) — should be active
    facts = kg.query("A", time=present - 3600)
    assert len(facts) == 1


# ---------------------------------------------------------------------------
# 3. Direction filtering
# ---------------------------------------------------------------------------


def test_query_direction_subject(kg: KnowledgeGraph) -> None:
    kg.add_fact("Alice", "knows", "Bob")
    facts = kg.query("Alice", direction="subject")
    assert len(facts) == 1
    facts_obj = kg.query("Alice", direction="object")
    assert len(facts_obj) == 0


def test_query_direction_object(kg: KnowledgeGraph) -> None:
    kg.add_fact("Alice", "knows", "Bob")
    facts = kg.query("Bob", direction="object")
    assert len(facts) == 1
    facts_subj = kg.query("Bob", direction="subject")
    assert len(facts_subj) == 0


def test_query_direction_both(kg: KnowledgeGraph) -> None:
    kg.add_fact("Alice", "knows", "Bob")
    kg.add_fact("Carol", "knows", "Alice")
    # Alice appears as subject in first and object in second
    facts = kg.query("Alice", direction="both")
    assert len(facts) == 2


# ---------------------------------------------------------------------------
# 4. query_predicate
# ---------------------------------------------------------------------------


def test_query_predicate(kg: KnowledgeGraph) -> None:
    kg.add_fact("Alice", "knows", "Bob")
    kg.add_fact("Carol", "knows", "Dave")
    kg.add_fact("Alice", "likes", "Coffee")
    facts = kg.query_predicate("knows")
    assert len(facts) == 2
    predicates = {f["predicate"] for f in facts}
    assert predicates == {"knows"}


def test_query_predicate_temporal(kg: KnowledgeGraph) -> None:
    past = time.time() - 3600
    kg.add_fact("Alice", "worked_at", "Acme", valid_to=past)
    kg.add_fact("Bob", "worked_at", "Beta")
    # At current time, only Bob's fact is active
    facts = kg.query_predicate("worked_at", time=time.time())
    assert len(facts) == 1
    assert facts[0]["subject"] == "Bob"


# ---------------------------------------------------------------------------
# 5. timeline
# ---------------------------------------------------------------------------


def test_timeline_returns_all(kg: KnowledgeGraph) -> None:
    kg.add_fact("Alice", "knows", "Bob")
    kg.add_fact("Alice", "likes", "Coffee")
    tl = kg.timeline("Alice")
    assert len(tl) == 2


def test_timeline_includes_invalidated(kg: KnowledgeGraph) -> None:
    fid = kg.add_fact("Alice", "knows", "Bob")
    kg.invalidate(fid)
    tl = kg.timeline("Alice")
    assert len(tl) == 1
    assert tl[0]["invalidated_at"] is not None


def test_timeline_chronological_order(kg: KnowledgeGraph) -> None:
    past = time.time() - 100
    present = time.time()
    kg.add_fact("Alice", "event_b", "B", valid_from=present)
    kg.add_fact("Alice", "event_a", "A", valid_from=past)
    tl = kg.timeline("Alice")
    # event_a has earlier valid_from, should come first
    first_event = tl[0]["predicate"]
    assert first_event == "event_a"


# ---------------------------------------------------------------------------
# 6. invalidate
# ---------------------------------------------------------------------------


def test_invalidate_returns_true(kg: KnowledgeGraph) -> None:
    fid = kg.add_fact("Alice", "knows", "Bob")
    assert kg.invalidate(fid) is True


def test_invalidate_not_found(kg: KnowledgeGraph) -> None:
    assert kg.invalidate("nonexist") is False


def test_invalidate_hides_from_query(kg: KnowledgeGraph) -> None:
    fid = kg.add_fact("Alice", "knows", "Bob")
    kg.invalidate(fid)
    facts = kg.query("Alice")
    assert len(facts) == 0


def test_invalidate_twice_returns_false(kg: KnowledgeGraph) -> None:
    fid = kg.add_fact("Alice", "knows", "Bob")
    kg.invalidate(fid)
    assert kg.invalidate(fid) is False


# ---------------------------------------------------------------------------
# 7. stats
# ---------------------------------------------------------------------------


def test_stats_empty(kg: KnowledgeGraph) -> None:
    s = kg.stats()
    assert s["total_facts"] == 0
    assert s["active_facts"] == 0
    assert s["invalidated_facts"] == 0
    assert s["total_entities"] == 0


def test_stats_after_add(kg: KnowledgeGraph) -> None:
    kg.add_fact("A", "rel", "B")
    kg.add_fact("C", "rel", "D")
    s = kg.stats()
    assert s["total_facts"] == 2
    assert s["active_facts"] == 2
    assert s["invalidated_facts"] == 0


def test_stats_after_invalidate(kg: KnowledgeGraph) -> None:
    fid = kg.add_fact("A", "rel", "B")
    kg.add_fact("C", "rel", "D")
    kg.invalidate(fid)
    s = kg.stats()
    assert s["total_facts"] == 2
    assert s["active_facts"] == 1
    assert s["invalidated_facts"] == 1


# ---------------------------------------------------------------------------
# 8. _parse_date helper
# ---------------------------------------------------------------------------


def test_parse_date_none() -> None:
    assert _parse_date(None) is None


def test_parse_date_float() -> None:
    ts = 1700000000.0
    assert _parse_date(ts) == ts


def test_parse_date_iso() -> None:
    result = _parse_date("2024-01-15T00:00:00Z")
    assert isinstance(result, float)
    assert result > 0


def test_parse_date_relative_hours() -> None:
    before = time.time()
    result = _parse_date("2h")
    after = time.time()
    # Should be roughly 2 hours in the past
    assert before - 7205 <= result <= after - 7195


def test_parse_date_relative_days() -> None:
    before = time.time()
    result = _parse_date("1d")
    assert before - 86405 <= result <= before - 86395


# ---------------------------------------------------------------------------
# 9. Context manager
# ---------------------------------------------------------------------------


def test_context_manager() -> None:
    with KnowledgeGraph(db_path=":memory:") as kg:
        fid = kg.add_fact("A", "rel", "B")
        assert len(fid) == 8


# ---------------------------------------------------------------------------
# 10. search_entities
# ---------------------------------------------------------------------------


def test_search_entities_no_match(kg: KnowledgeGraph) -> None:
    # entities table is empty by default; search should return empty list
    results = kg.search_entities("Alice")
    assert results == []


# ---------------------------------------------------------------------------
# Regression: Bug 1 — add_fact must populate entities table
# ---------------------------------------------------------------------------


def test_add_fact_populates_entities_stats(kg: KnowledgeGraph) -> None:
    """After add_fact, stats()['total_entities'] must be >= 2 (subject + object)."""
    kg.add_fact("Alice", "knows", "Bob")
    s = kg.stats()
    assert s["total_entities"] >= 2, (
        f"Expected >= 2 entities after add_fact, got {s['total_entities']}"
    )


def test_add_fact_search_entities_finds_subject(kg: KnowledgeGraph) -> None:
    """After add_fact, search_entities should return the subject entity."""
    kg.add_fact("Alice", "knows", "Bob")
    results = kg.search_entities("Alice")
    assert len(results) >= 1
    names = [r["name"] for r in results]
    assert "Alice" in names


def test_add_fact_search_entities_finds_object(kg: KnowledgeGraph) -> None:
    """After add_fact, search_entities should return the object entity."""
    kg.add_fact("Alice", "knows", "Bob")
    results = kg.search_entities("Bob")
    assert len(results) >= 1
    names = [r["name"] for r in results]
    assert "Bob" in names


def test_add_fact_entities_deduped(kg: KnowledgeGraph) -> None:
    """Adding multiple facts with the same entity name should not duplicate it."""
    kg.add_fact("Alice", "knows", "Bob")
    kg.add_fact("Alice", "likes", "Coffee")
    results = kg.search_entities("Alice")
    alice_rows = [r for r in results if r["name"] == "Alice"]
    assert len(alice_rows) == 1, "Entity 'Alice' should appear exactly once in entities table"


def test_add_fact_populates_entities_table(kg: KnowledgeGraph) -> None:
    """Regression: add_fact() must upsert subject and object into entities."""
    kg.add_fact("Alice", "works_on", "ProjectX")
    s = kg.stats()
    assert s["total_entities"] >= 2, (
        f"Expected at least 2 entities after add_fact, got {s['total_entities']}"
    )
    results = kg.search_entities("Alice")
    assert len(results) >= 1, "search_entities('Alice') should return at least 1 result"
    names = {r["name"] for r in results}
    assert "Alice" in names


def test_query_both_direction_no_duplicates(kg: KnowledgeGraph) -> None:
    """Regression: query(direction='both') must not return duplicates when subject == object."""
    # Alice is both subject and object of the same fact
    kg.add_fact("Alice", "knows", "Alice")
    facts = kg.query("Alice", direction="both")
    ids = [f["id"] for f in facts]
    assert len(ids) == len(set(ids)), (
        f"Duplicate fact IDs returned by query(direction='both'): {ids}"
    )


# ---------------------------------------------------------------------------
# 11. CLI command tests (argparse-level)
# ---------------------------------------------------------------------------


def test_cli_kg_add_basic(tmp_path) -> None:
    import argparse
    from memos.cli import cmd_kg_add, cmd_kg_stats

    db = str(tmp_path / "test.db")

    ns_add = argparse.Namespace(
        subject="Alice",
        predicate="knows",
        object="Bob",
        valid_from=None,
        valid_to=None,
        confidence=1.0,
        source=None,
        kg_db=db,
    )
    # Should not raise
    cmd_kg_add(ns_add)

    ns_stats = argparse.Namespace(kg_db=db)
    # Should not raise
    cmd_kg_stats(ns_stats)


def test_cli_kg_query(tmp_path, capsys) -> None:
    import argparse
    from memos.cli import cmd_kg_add, cmd_kg_query

    db = str(tmp_path / "test.db")

    ns_add = argparse.Namespace(
        subject="Alice", predicate="knows", object="Bob",
        valid_from=None, valid_to=None, confidence=1.0,
        source=None, kg_db=db,
    )
    cmd_kg_add(ns_add)

    ns_query = argparse.Namespace(entity="Alice", at_time=None, direction="both", kg_db=db)
    cmd_kg_query(ns_query)
    captured = capsys.readouterr()
    assert "Alice" in captured.out
    assert "Bob" in captured.out


def test_cli_kg_timeline(tmp_path, capsys) -> None:
    import argparse
    from memos.cli import cmd_kg_add, cmd_kg_timeline

    db = str(tmp_path / "test.db")
    ns_add = argparse.Namespace(
        subject="Alice", predicate="born_in", object="Paris",
        valid_from=None, valid_to=None, confidence=1.0,
        source=None, kg_db=db,
    )
    cmd_kg_add(ns_add)

    ns_tl = argparse.Namespace(entity="Alice", kg_db=db)
    cmd_kg_timeline(ns_tl)
    captured = capsys.readouterr()
    assert "Alice" in captured.out


def test_cli_kg_invalidate(tmp_path, capsys) -> None:
    import argparse
    from memos.cli import cmd_kg_add, cmd_kg_query, cmd_kg_invalidate

    db = str(tmp_path / "test.db")

    # Add fact
    ns_add = argparse.Namespace(
        subject="Alice", predicate="knows", object="Bob",
        valid_from=None, valid_to=None, confidence=1.0,
        source=None, kg_db=db,
    )
    cmd_kg_add(ns_add)

    # Get fact ID from query
    with KnowledgeGraph(db_path=db) as g:
        facts = g.query("Alice")
    assert len(facts) == 1
    fid = facts[0]["id"]

    ns_inv = argparse.Namespace(fact_id=fid, kg_db=db)
    cmd_kg_invalidate(ns_inv)
    captured = capsys.readouterr()
    assert "invalidated" in captured.out.lower()


def test_cli_kg_stats_empty(tmp_path, capsys) -> None:
    import argparse
    from memos.cli import cmd_kg_stats

    db = str(tmp_path / "test.db")
    ns = argparse.Namespace(kg_db=db)
    cmd_kg_stats(ns)
    captured = capsys.readouterr()
    assert "Total facts" in captured.out


# ---------------------------------------------------------------------------
# 12. REST endpoint tests (httpx AsyncClient)
# ---------------------------------------------------------------------------


@pytest.fixture()
def kg_db_path(tmp_path):
    return str(tmp_path / "api_test.db")


@pytest.fixture()
def app(kg_db_path):
    """Create a FastAPI test app backed by a temp KG db."""
    from memos.core import MemOS
    from memos.api import create_fastapi_app

    memos_instance = MemOS(backend="memory")
    return create_fastapi_app(memos=memos_instance, kg_db_path=kg_db_path)


@pytest.mark.anyio
async def test_rest_kg_add_fact(app) -> None:
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/kg/facts", json={
            "subject": "Alice",
            "predicate": "knows",
            "object": "Bob",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "id" in data


@pytest.mark.anyio
async def test_rest_kg_query(app) -> None:
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/kg/facts", json={
            "subject": "Alice", "predicate": "knows", "object": "Bob",
        })
        resp = await client.get("/api/v1/kg/query", params={"entity": "Alice"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["facts"]) == 1
    assert data["facts"][0]["object"] == "Bob"


@pytest.mark.anyio
async def test_rest_kg_timeline(app) -> None:
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/kg/facts", json={
            "subject": "Alice", "predicate": "born_in", "object": "Paris",
        })
        resp = await client.get("/api/v1/kg/timeline", params={"entity": "Alice"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["timeline"]) == 1


@pytest.mark.anyio
async def test_rest_kg_invalidate(app) -> None:
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        add_resp = await client.post("/api/v1/kg/facts", json={
            "subject": "Alice", "predicate": "works_at", "object": "Acme",
        })
        fact_id = add_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/kg/facts/{fact_id}")
        assert del_resp.json()["status"] == "ok"

        # Fact should no longer appear
        query_resp = await client.get("/api/v1/kg/query", params={"entity": "Alice"})
    assert len(query_resp.json()["facts"]) == 0


@pytest.mark.anyio
async def test_rest_kg_stats(app) -> None:
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/kg/facts", json={
            "subject": "A", "predicate": "rel", "object": "B",
        })
        resp = await client.get("/api/v1/kg/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_facts"] == 1
    assert data["active_facts"] == 1


@pytest.mark.anyio
async def test_rest_kg_add_missing_fields(app) -> None:
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/kg/facts", json={"subject": "Alice"})

    assert resp.json()["status"] == "error"
