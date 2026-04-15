"""Tests for the Decay & Reinforce engine (P9).

Covers:
- DecayEngine: adjusted_score, reinforce, run_decay, find_prune_candidates
- DecayConfig and DecayReport dataclasses
- CLI commands: decay, reinforce
- REST endpoints: POST /api/v1/decay/run, POST /api/v1/memories/{id}/reinforce
- MCP tools: memory_decay, memory_reinforce
"""

from __future__ import annotations

import time

import pytest

from memos.core import MemOS
from memos.decay.engine import DecayConfig, DecayEngine
from memos.models import MemoryItem

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> DecayEngine:
    return DecayEngine(rate=0.01, reinforce_strength=0.05)


def _make_item(content: str, age_days: float = 0, importance: float = 0.5) -> MemoryItem:
    item = MemoryItem(
        id=f"test-{content[:8]}",
        content=content,
        importance=importance,
        created_at=time.time() - age_days * 86400,
    )
    return item


# ---------------------------------------------------------------------------
# 1. DecayEngine — adjusted_score
# ---------------------------------------------------------------------------


def test_adjusted_score_fresh(engine: DecayEngine):
    item = _make_item("fresh memory", age_days=0)
    score = engine.adjusted_score(0.8, item)
    assert score > 0.7  # Fresh memory barely decays


def test_adjusted_score_old(engine: DecayEngine):
    item = _make_item("old memory", age_days=365, importance=0.3)
    score = engine.adjusted_score(0.8, item)
    assert score < 0.5  # Old low-importance memory decays significantly


def test_adjusted_score_permanent(engine: DecayEngine):
    """Permanent memories (importance=1.0) resist decay."""
    item = _make_item("permanent", age_days=365, importance=1.0)
    score = engine.adjusted_score(0.5, item)
    assert score > 0.1  # Still has some score thanks to importance floor


def test_adjusted_score_accessed(engine: DecayEngine):
    """Frequently accessed memories get a boost."""
    item_fresh = _make_item("fresh", age_days=10)
    item_accessed = _make_item("accessed", age_days=10)
    item_accessed.access_count = 20
    score_fresh = engine.adjusted_score(0.5, item_fresh)
    score_accessed = engine.adjusted_score(0.5, item_accessed)
    assert score_accessed > score_fresh


def test_adjusted_score_clamped(engine: DecayEngine):
    item = _make_item("test", importance=2.0)  # over 1.0
    score = engine.adjusted_score(1.5, item)
    assert score <= 1.0


# ---------------------------------------------------------------------------
# 2. DecayEngine — reinforce
# ---------------------------------------------------------------------------


def test_reinforce_default(engine: DecayEngine):
    item = _make_item("test", importance=0.5)
    new_imp = engine.reinforce(item)
    assert new_imp == pytest.approx(0.55, abs=0.01)


def test_reinforce_custom_strength(engine: DecayEngine):
    item = _make_item("test", importance=0.5)
    new_imp = engine.reinforce(item, strength=0.2)
    assert new_imp == pytest.approx(0.7, abs=0.01)


def test_reinforce_clamp_at_one(engine: DecayEngine):
    item = _make_item("test", importance=0.95)
    new_imp = engine.reinforce(item, strength=0.2)
    assert new_imp == 1.0


def test_reinforce_touches_item(engine: DecayEngine):
    item = _make_item("test")
    old_count = item.access_count
    engine.reinforce(item)
    assert item.access_count == old_count + 1


# ---------------------------------------------------------------------------
# 3. DecayEngine — run_decay
# ---------------------------------------------------------------------------


def test_run_decay_dry_run(engine: DecayEngine):
    items = [_make_item("young", age_days=1, importance=0.5)]
    report = engine.run_decay(items, min_age_days=0, dry_run=True)
    assert report.total == 1
    assert report.decayed >= 0
    # dry_run should not modify
    assert items[0].importance == 0.5


def test_run_decay_applies(engine: DecayEngine):
    items = [_make_item("old", age_days=30, importance=0.5)]
    report = engine.run_decay(items, min_age_days=0, dry_run=False)
    assert report.decayed == 1
    assert items[0].importance < 0.5


def test_run_decay_respects_floor(engine: DecayEngine):
    items = [_make_item("very-old", age_days=365, importance=0.3)]
    engine.run_decay(items, min_age_days=0, floor=0.2, dry_run=False)
    assert items[0].importance >= 0.2


def test_run_decay_skips_young(engine: DecayEngine):
    items = [_make_item("young", age_days=0, importance=0.5)]
    report = engine.run_decay(items, min_age_days=7, dry_run=False)
    assert report.decayed == 0
    assert items[0].importance == 0.5


def test_run_decay_skips_permanent(engine: DecayEngine):
    items = [_make_item("permanent", age_days=30, importance=0.95)]
    report = engine.run_decay(items, min_age_days=0, dry_run=False)
    assert report.decayed == 0
    assert items[0].importance == 0.95


def test_run_decay_report_details(engine: DecayEngine):
    items = [
        _make_item("a", age_days=30, importance=0.5),
        _make_item("b", age_days=1, importance=0.5),
    ]
    report = engine.run_decay(items, min_age_days=0, dry_run=False)
    assert report.decayed >= 1
    assert len(report.details) >= 1
    assert "id" in report.details[0]
    assert "importance_before" in report.details[0]


def test_run_decay_avg_importance(engine: DecayEngine):
    items = [
        _make_item("a", age_days=30, importance=0.8),
        _make_item("b", age_days=30, importance=0.2),
    ]
    report = engine.run_decay(items, min_age_days=0, dry_run=False)
    assert report.avg_importance_before > 0
    assert report.avg_importance_after > 0


def test_run_decay_empty(engine: DecayEngine):
    report = engine.run_decay([], dry_run=False)
    assert report.total == 0
    assert report.decayed == 0
    assert report.avg_importance_before == 0.0


# ---------------------------------------------------------------------------
# 4. DecayEngine — find_prune_candidates (existing, verify still works)
# ---------------------------------------------------------------------------


def test_find_prune_candidates(engine: DecayEngine):
    items = [
        _make_item("old-low", age_days=200, importance=0.1),
        _make_item("new-low", age_days=0, importance=0.1),
        _make_item("old-high", age_days=200, importance=0.95),
    ]
    candidates = engine.find_prune_candidates(items, threshold=0.3, max_age_days=365)
    # old-low should be a candidate, new-low too recent, old-high too important
    ids = {c.id for c in candidates}
    assert "test-old-low" in ids


# ---------------------------------------------------------------------------
# 5. DecayConfig dataclass
# ---------------------------------------------------------------------------


def test_decay_config_defaults():
    cfg = DecayConfig()
    assert cfg.rate == 0.01
    assert cfg.reinforce_strength == 0.05
    assert cfg.auto_reinforce is True
    assert cfg.importance_floor == 0.1
    assert cfg.decay_min_age_days == 7.0


# ---------------------------------------------------------------------------
# 6. CLI tests
# ---------------------------------------------------------------------------


def test_cli_decay_dry_run(memos_empty: MemOS, capsys):
    import argparse

    from memos.cli import cmd_decay

    memos_empty.learn("test memory for decay", importance=0.5)
    ns = argparse.Namespace(
        apply=False,
        min_age_days=0,
        floor=None,
        backend="memory",
    )
    # Inject the memos instance
    import memos.cli.commands_memory as cm_mod

    original = cm_mod._get_memos
    cm_mod._get_memos = lambda ns: memos_empty
    try:
        cmd_decay(ns)
    finally:
        cm_mod._get_memos = original

    captured = capsys.readouterr()
    assert "DRY RUN" in captured.out
    assert "Total memories" in captured.out


def test_cli_decay_apply(memos_empty: MemOS, capsys):
    import argparse

    from memos.cli import cmd_decay

    memos_empty.learn("old decay test", importance=0.8)
    ns = argparse.Namespace(
        apply=True,
        min_age_days=0,
        floor=None,
        backend="memory",
    )

    import memos.cli.commands_memory as cm_mod

    original = cm_mod._get_memos
    cm_mod._get_memos = lambda ns: memos_empty
    try:
        cmd_decay(ns)
    finally:
        cm_mod._get_memos = original

    captured = capsys.readouterr()
    assert "APPLIED" in captured.out


def test_cli_reinforce(memos_empty: MemOS, capsys):
    import argparse

    from memos.cli import cmd_reinforce

    item = memos_empty.learn("reinforce target", importance=0.5)
    ns = argparse.Namespace(
        memory_id=item.id,
        strength=None,
        backend="memory",
    )

    import memos.cli.commands_memory as cm_mod

    original = cm_mod._get_memos
    cm_mod._get_memos = lambda ns: memos_empty
    try:
        cmd_reinforce(ns)
    finally:
        cm_mod._get_memos = original

    captured = capsys.readouterr()
    assert "Reinforced" in captured.out
    assert item.id[:8] in captured.out


def test_cli_reinforce_not_found(memos_empty: MemOS):
    import argparse

    from memos.cli import cmd_reinforce

    ns = argparse.Namespace(
        memory_id="nonexistent",
        strength=None,
        backend="memory",
    )

    import memos.cli.commands_memory as cm_mod

    original = cm_mod._get_memos
    cm_mod._get_memos = lambda ns: memos_empty
    try:
        with pytest.raises(SystemExit):
            cmd_reinforce(ns)
    finally:
        cm_mod._get_memos = original


# ---------------------------------------------------------------------------
# 7. REST endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def app(memos_empty: MemOS):
    from memos.api import create_fastapi_app

    return create_fastapi_app(memos=memos_empty)


@pytest.mark.anyio
async def test_rest_decay_run(app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/decay/run", json={"dry_run": True, "min_age_days": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "total" in data
    assert "decayed" in data


@pytest.mark.anyio
async def test_rest_decay_apply(app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First add a memory
        await client.post("/api/v1/learn", json={"content": "decay test", "importance": 0.5})
        # Apply decay
        resp = await client.post("/api/v1/decay/run", json={"dry_run": False, "min_age_days": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.anyio
async def test_rest_reinforce(app):
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    # We need the actual MemOS instance to get the item ID
    m = MemOS(backend="memory")
    item = m.learn("reinforce rest test", importance=0.5)
    test_app = create_fastapi_app(memos=m)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(f"/api/v1/memories/{item.id}/reinforce", json={"strength": 0.1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["importance_after"] > data["importance_before"]


@pytest.mark.anyio
async def test_rest_reinforce_not_found(app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/memories/nonexistent/reinforce", json={})
    assert resp.status_code == 404
    data = resp.json()
    assert data["status"] == "error"


# ---------------------------------------------------------------------------
# 8. MCP tool tests
# ---------------------------------------------------------------------------


def test_mcp_decay_dry_run(memos_empty: MemOS):
    from memos.mcp_server import _dispatch

    memos_empty.learn("mcp decay test", importance=0.5)
    result = _dispatch(memos_empty, "memory_decay", {"min_age_days": 0})
    assert not result.get("isError")
    assert "DRY RUN" in result["content"][0]["text"]


def test_mcp_decay_apply(memos_empty: MemOS):
    from memos.mcp_server import _dispatch

    memos_empty.learn("mcp decay apply", importance=0.5)
    result = _dispatch(memos_empty, "memory_decay", {"apply": True, "min_age_days": 0})
    assert not result.get("isError")
    assert "APPLIED" in result["content"][0]["text"]


def test_mcp_reinforce(memos_empty: MemOS):
    from memos.mcp_server import _dispatch

    item = memos_empty.learn("mcp reinforce test", importance=0.5)
    result = _dispatch(memos_empty, "memory_reinforce", {"memory_id": item.id, "strength": 0.1})
    assert not result.get("isError")
    assert "Reinforced" in result["content"][0]["text"]


def test_mcp_reinforce_not_found(memos_empty: MemOS):
    from memos.mcp_server import _dispatch

    result = _dispatch(memos_empty, "memory_reinforce", {"memory_id": "nonexistent"})
    assert result.get("isError")


def test_mcp_tools_list_includes_decay():
    from memos.mcp_server import TOOLS

    names = {t["name"] for t in TOOLS}
    assert "memory_decay" in names
    assert "memory_reinforce" in names
    assert len(TOOLS) == 15  # + brain_search
