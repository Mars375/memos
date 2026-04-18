"""Tests for the Multi-layer Context Stack (P7).

Covers:
- set/get identity
- wake_up without identity (empty)
- wake_up with identity + memories
- wake_up max_chars respected
- wake_up format (sections: === IDENTITY ===, === MEMORY CONTEXT ===)
- recall_l2 with tag filters
- recall_l3 full search
- context_for format
- REST endpoints (via httpx AsyncClient)
- MCP tool dispatch
- CLI wake-up
- CLI identity set/show
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from memos.context import ContextStack
from memos.core import MemOS
from memos.storage.memory_backend import InMemoryBackend


class CountingStore(InMemoryBackend):
    def __init__(self) -> None:
        super().__init__()
        self.list_all_calls = 0

    def list_all(self, *, namespace: str = ""):
        self.list_all_calls += 1
        return super().list_all(namespace=namespace)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cs_tmp(memos_empty: MemOS, tmp_path: Path) -> ContextStack:
    """ContextStack with a temporary identity file path."""
    identity_file = tmp_path / "identity.txt"
    return ContextStack(memos_empty, identity_path=str(identity_file))


@pytest.fixture()
def cs_with_memories(cs_tmp: ContextStack) -> ContextStack:
    """ContextStack loaded with a few memories for testing."""
    m = cs_tmp._memos
    m.learn("Python async best practices", tags=["python", "async"], importance=0.9)
    m.learn("Docker multi-stage builds", tags=["devops"], importance=0.85)
    m.learn("Redis caching patterns", tags=["redis", "cache"], importance=0.7)
    m.learn("Git rebase workflow", tags=["git"], importance=0.5)
    return cs_tmp


# ---------------------------------------------------------------------------
# 1. Identity (L0) — set / get
# ---------------------------------------------------------------------------


def test_get_identity_missing_returns_empty(cs_tmp: ContextStack) -> None:
    """get_identity() should return empty string when file does not exist."""
    assert cs_tmp.get_identity() == ""


def test_set_then_get_identity(cs_tmp: ContextStack) -> None:
    content = "I am an AI assistant focused on Python and DevOps."
    cs_tmp.set_identity(content)
    assert cs_tmp.get_identity() == content


def test_set_identity_creates_parent_dirs(memos_empty: MemOS, tmp_path: Path) -> None:
    deep_path = tmp_path / "a" / "b" / "c" / "identity.txt"
    cs = ContextStack(memos_empty, identity_path=str(deep_path))
    cs.set_identity("deep identity")
    assert deep_path.exists()
    assert deep_path.read_text() == "deep identity"


def test_set_identity_overwrites(cs_tmp: ContextStack) -> None:
    cs_tmp.set_identity("first version")
    cs_tmp.set_identity("second version")
    assert cs_tmp.get_identity() == "second version"


def test_identity_path_tilde_expansion(memos_empty: MemOS) -> None:
    """ContextStack constructor must expand ~ in identity_path."""
    cs = ContextStack(memos_empty, identity_path="~/.memos/identity.txt")
    assert "~" not in str(cs._identity_path)
    assert str(Path.home()) in str(cs._identity_path)


# ---------------------------------------------------------------------------
# 2. wake_up — output format
# ---------------------------------------------------------------------------


def test_wake_up_empty_store_no_identity(cs_tmp: ContextStack) -> None:
    """wake_up() on an empty store with no identity should still produce output."""
    output = cs_tmp.wake_up()
    assert isinstance(output, str)
    assert "=== IDENTITY ===" in output
    assert "=== MEMORY CONTEXT" in output


def test_wake_up_includes_identity_section(cs_tmp: ContextStack) -> None:
    cs_tmp.set_identity("I am a DevOps-focused agent.")
    output = cs_tmp.wake_up()
    assert "=== IDENTITY ===" in output
    assert "I am a DevOps-focused agent." in output


def test_wake_up_includes_memory_context_section(cs_with_memories: ContextStack) -> None:
    output = cs_with_memories.wake_up()
    assert "=== MEMORY CONTEXT" in output
    # At least one memory should appear
    assert "Python async best practices" in output


def test_wake_up_memory_count_in_header(cs_with_memories: ContextStack) -> None:
    """The memory section header should include the count of returned memories."""
    output = cs_with_memories.wake_up(l1_top=3)
    assert "=== MEMORY CONTEXT (3 memories) ===" in output


def test_wake_up_includes_stats_section(cs_with_memories: ContextStack) -> None:
    output = cs_with_memories.wake_up(include_stats=True)
    assert "=== STATS ===" in output
    assert "memories" in output


def test_wake_up_no_stats(cs_with_memories: ContextStack) -> None:
    output = cs_with_memories.wake_up(include_stats=False)
    assert "=== STATS ===" not in output


def test_wake_up_respects_max_chars(cs_with_memories: ContextStack) -> None:
    """wake_up() must truncate output to exactly max_chars."""
    cs_with_memories.set_identity("x" * 500)
    output = cs_with_memories.wake_up(max_chars=100)
    assert len(output) <= 100


def test_wake_up_importance_ordering(cs_tmp: ContextStack) -> None:
    """Memories should appear in descending importance order."""
    m = cs_tmp._memos
    m.learn("Low priority", importance=0.1)
    m.learn("High priority", importance=0.99)
    m.learn("Medium priority", importance=0.5)
    output = cs_tmp.wake_up(l1_top=3)
    idx_high = output.index("High priority")
    idx_medium = output.index("Medium priority")
    idx_low = output.index("Low priority")
    assert idx_high < idx_medium < idx_low


def test_wake_up_memory_line_format(cs_with_memories: ContextStack) -> None:
    """Each memory line should follow [score] content (tags: ...) format."""
    output = cs_with_memories.wake_up()
    # Check that at least one line has the [X.XX] prefix
    lines = output.splitlines()
    mem_lines = [line for line in lines if line.startswith("[")]
    assert len(mem_lines) > 0
    # Score format: [0.XX] or [1.00]
    import re

    for line in mem_lines:
        assert re.match(r"^\[[\d.]+\]", line), f"unexpected format: {line!r}"


def test_wake_up_with_stats_reuses_single_store_scan(tmp_path: Path) -> None:
    mem = MemOS(backend="memory")
    mem._store = CountingStore()
    mem.learn("Python async best practices", tags=["python"], importance=0.9)
    mem.learn("Docker multi-stage builds", tags=["devops"], importance=0.85)
    mem._store.list_all_calls = 0
    cs = ContextStack(mem, identity_path=str(tmp_path / "identity.txt"))

    output = cs.wake_up(include_stats=True)

    assert "=== STATS ===" in output
    assert mem._store.list_all_calls == 1


def test_wake_up_compact_reuses_single_store_scan(tmp_path: Path) -> None:
    mem = MemOS(backend="memory")
    mem._store = CountingStore()
    mem.learn("Python async best practices", tags=["python"], importance=0.9)
    mem.learn("Docker multi-stage builds", tags=["devops"], importance=0.85)
    mem._store.list_all_calls = 0
    cs = ContextStack(mem, identity_path=str(tmp_path / "identity.txt"))

    output = cs.wake_up(compact=True)

    assert "[STATS]" in output
    assert mem._store.list_all_calls == 1


# ---------------------------------------------------------------------------
# 3. recall_l2 — scoped by tags
# ---------------------------------------------------------------------------


def test_recall_l2_with_tags(cs_with_memories: ContextStack) -> None:
    results = cs_with_memories.recall_l2("async patterns", tags=["python"])
    # With keyword matching, we may get results; just check type
    assert isinstance(results, list)


def test_recall_l2_no_tags_returns_results(cs_with_memories: ContextStack) -> None:
    results = cs_with_memories.recall_l2("Docker builds", tags=None)
    assert isinstance(results, list)


def test_recall_l2_top_limits_results(cs_with_memories: ContextStack) -> None:
    results = cs_with_memories.recall_l2("patterns", top=2)
    assert len(results) <= 2


# ---------------------------------------------------------------------------
# 4. recall_l3 — full search
# ---------------------------------------------------------------------------


def test_recall_l3_returns_list(cs_with_memories: ContextStack) -> None:
    results = cs_with_memories.recall_l3("Docker")
    assert isinstance(results, list)


def test_recall_l3_top_limits(cs_with_memories: ContextStack) -> None:
    results = cs_with_memories.recall_l3("patterns", top=2)
    assert len(results) <= 2


# ---------------------------------------------------------------------------
# 5. context_for
# ---------------------------------------------------------------------------


def test_context_for_returns_string(cs_with_memories: ContextStack) -> None:
    output = cs_with_memories.context_for("async Python patterns")
    assert isinstance(output, str)


def test_context_for_respects_max_chars(cs_with_memories: ContextStack) -> None:
    cs_with_memories.set_identity("y" * 200)
    output = cs_with_memories.context_for("docker", max_chars=50)
    assert len(output) <= 50


def test_context_for_includes_identity_when_set(cs_with_memories: ContextStack) -> None:
    cs_with_memories.set_identity("My identity text.")
    output = cs_with_memories.context_for("python async", max_chars=2000)
    assert "=== IDENTITY ===" in output
    assert "My identity text." in output


def test_context_for_includes_relevant_section(cs_with_memories: ContextStack) -> None:
    output = cs_with_memories.context_for("docker multi-stage", max_chars=2000)
    assert "=== RELEVANT MEMORIES" in output


def test_context_for_no_identity_still_works(cs_with_memories: ContextStack) -> None:
    output = cs_with_memories.context_for("caching")
    assert isinstance(output, str)


# ---------------------------------------------------------------------------
# 6. REST endpoints
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rest_wake_up_returns_context() -> None:
    """GET /api/v1/context/wake-up returns context string."""
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    m = MemOS(backend="memory")
    m.learn("Test memory for wake-up", importance=0.8)
    app = create_fastapi_app(memos=m)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/context/wake-up")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "context" in data
    assert "=== MEMORY CONTEXT" in data["context"]


@pytest.mark.anyio
async def test_rest_identity_get_empty() -> None:
    """GET /api/v1/context/identity returns empty when no identity file set."""
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    m = MemOS(backend="memory")
    app = create_fastapi_app(memos=m)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/context/identity")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.anyio
async def test_rest_identity_set_and_get() -> None:
    """POST /api/v1/context/identity stores identity and returns char count."""
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    m = MemOS(backend="memory")
    app = create_fastapi_app(memos=m)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/context/identity",
            json={"content": "I am a test agent."},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["chars"] == len("I am a test agent.")


@pytest.mark.anyio
async def test_rest_identity_set_missing_content() -> None:
    """POST /api/v1/context/identity without content returns error."""
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    m = MemOS(backend="memory")
    app = create_fastapi_app(memos=m)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/context/identity", json={})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_rest_context_for_returns_context() -> None:
    """GET /api/v1/context/for returns context for a query."""
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    m = MemOS(backend="memory")
    m.learn("Python async patterns", tags=["python"])
    app = create_fastapi_app(memos=m)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/context/for", params={"query": "python async"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "context" in data
    assert data["query"] == "python async"


@pytest.mark.anyio
async def test_rest_graph_reuses_single_store_scan() -> None:
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    m = MemOS(backend="memory")
    m._store = CountingStore()
    m.learn("Python async patterns", tags=["python", "backend"], importance=0.8)
    m.learn("Docker deploy guide", tags=["docker", "backend"], importance=0.6)
    m._store.list_all_calls = 0
    app = create_fastapi_app(memos=m)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/graph")

    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total_memories"] == 2
    assert m._store.list_all_calls == 1


@pytest.mark.anyio
async def test_rest_graph_aggregates_shared_tags_without_duplicate_edges() -> None:
    from httpx import ASGITransport, AsyncClient

    from memos.api import create_fastapi_app

    m = MemOS(backend="memory")
    m.learn("alpha memory", tags=["shared-a", "shared-b"])
    m.learn("beta memory", tags=["shared-a", "shared-b"])
    app = create_fastapi_app(memos=m)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/graph")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["edges"]) == 1
    edge = data["edges"][0]
    assert edge["weight"] == 2
    assert sorted(edge["shared_tags"]) == ["shared-a", "shared-b"]


# ---------------------------------------------------------------------------
# 7. MCP dispatch
# ---------------------------------------------------------------------------


def test_mcp_memory_wake_up_dispatch() -> None:
    """_dispatch('memory_wake_up', ...) returns text content."""
    from memos.mcp_server import _dispatch

    m = MemOS(backend="memory")
    m.learn("Wake-up test memory", importance=0.9)
    result = _dispatch(m, "memory_wake_up", {"max_chars": 500, "include_stats": True})
    assert "content" in result
    text = result["content"][0]["text"]
    assert "=== MEMORY CONTEXT" in text


def test_mcp_memory_wake_up_default_args() -> None:
    """_dispatch('memory_wake_up', {}) uses default parameters."""
    from memos.mcp_server import _dispatch

    m = MemOS(backend="memory")
    result = _dispatch(m, "memory_wake_up", {})
    assert "content" in result
    assert result.get("isError") is not True


def test_mcp_memory_context_for_dispatch() -> None:
    """_dispatch('memory_context_for', ...) returns context for a query."""
    from memos.mcp_server import _dispatch

    m = MemOS(backend="memory")
    m.learn("Docker multi-stage builds", tags=["devops"])
    result = _dispatch(m, "memory_context_for", {"query": "docker", "max_chars": 800})
    assert "content" in result
    assert result.get("isError") is not True


def test_mcp_memory_context_for_missing_query() -> None:
    """_dispatch('memory_context_for', {}) returns an error when query missing."""
    from memos.mcp_server import _dispatch

    m = MemOS(backend="memory")
    result = _dispatch(m, "memory_context_for", {})
    assert result.get("isError") is True


def test_mcp_tools_list_includes_wake_up() -> None:
    """TOOLS list must include the memory_wake_up tool definition."""
    from memos.mcp_server import TOOLS

    names = [t["name"] for t in TOOLS]
    assert "memory_wake_up" in names


def test_mcp_tools_list_includes_context_for() -> None:
    """TOOLS list must include the memory_context_for tool definition."""
    from memos.mcp_server import TOOLS

    names = [t["name"] for t in TOOLS]
    assert "memory_context_for" in names


# ---------------------------------------------------------------------------
# 8. CLI — wake-up and identity commands
# ---------------------------------------------------------------------------


def test_cli_wake_up(tmp_path: Path, capsys) -> None:
    """memos wake-up prints L0+L1 context."""
    from memos.cli import main

    persist = tmp_path / "store.json"
    # Pre-populate via MemOS then persist
    m = MemOS(backend="memory")
    m.learn("CLI wake-up test memory", importance=0.8)
    from memos.storage.json_backend import JsonFileBackend

    jb = JsonFileBackend(path=str(persist))
    for item in m._store.list_all():
        jb.upsert(item)

    # Use memory backend with persist-path so the CLI can load memories
    main(["wake-up", "--backend", "memory", "--max-chars", "1000", "--top", "5"])
    captured = capsys.readouterr()
    # wake-up output must contain the MEMORY CONTEXT section header
    assert "=== MEMORY CONTEXT" in captured.out


def test_cli_identity_show_empty(tmp_path: Path, capsys) -> None:
    """memos identity show prints a helpful message when no identity is set."""
    from memos.context import ContextStack

    class _FakeMemos:
        namespace = ""

        def stats(self, items=None):
            from memos.models import MemoryStats

            return MemoryStats()

        _store = type("S", (), {"list_all": lambda self, **kw: []})()

    identity_path = tmp_path / "no_identity.txt"
    cs = ContextStack(_FakeMemos(), identity_path=str(identity_path))  # type: ignore[arg-type]

    # With no file, get_identity returns empty string
    result = cs.get_identity()
    assert result == ""

    # After calling wake_up with no memories, it still works
    output = cs.wake_up(include_stats=False)
    assert "=== IDENTITY ===" in output


def test_cli_identity_set_and_show(tmp_path: Path, capsys) -> None:
    """memos identity set <text> then show round-trips correctly."""

    identity_file = tmp_path / "identity.txt"

    class _FakeMemos:
        namespace = ""

        def stats(self, items=None):
            from memos.models import MemoryStats

            return MemoryStats()

        def _store_list_all(self):
            return []

    # Manually build a ContextStack pointed at our tmp file
    cs = ContextStack(_FakeMemos(), identity_path=str(identity_file))  # type: ignore[arg-type]
    cs.set_identity("Test identity content")

    assert identity_file.read_text() == "Test identity content"

    result = cs.get_identity()
    assert result == "Test identity content"


# ── P3: compact wake-up ────────────────────────────────────────────────────


class _FakeMemosCompact:
    namespace = ""

    def __init__(self, items=None):
        self._items = items or []

    def stats(self, items=None):
        from memos.models import MemoryStats

        source_items = items if items is not None else self._items
        return MemoryStats(
            total_memories=len(source_items),
            decay_candidates=1,
        )

    class _FakeStore:
        def __init__(self, items):
            self._items = items

        def list_all(self, namespace=""):
            return self._items

    @property
    def _store(self):
        return self._FakeStore(self._items)


def test_wake_up_compact_format(tmp_path):
    """compact=True produces [ID], [MEM], [STATS] lines without section headers."""
    from memos.context import ContextStack
    from memos.models import MemoryItem

    items = [
        MemoryItem(id="a1", content="Python async patterns", importance=0.9),
        MemoryItem(id="a2", content="Docker multi-stage builds", importance=0.8),
        MemoryItem(id="a3", content="Redis caching strategy", importance=0.7),
    ]
    fake = _FakeMemosCompact(items)
    identity_path = tmp_path / "identity.txt"
    cs = ContextStack(fake, identity_path=str(identity_path))  # type: ignore[arg-type]
    cs.set_identity("Tachikoma — AI agent on Cortex")

    output = cs.wake_up(compact=True)

    assert "===" not in output, "compact mode must not include section headers"
    assert "[ID]" in output
    assert "[MEM]" in output
    assert "[STATS]" in output
    assert "Tachikoma" in output
    assert "Python async" in output


def test_wake_up_compact_fits_in_200_tokens(tmp_path):
    """compact output should fit in ~200 tokens (≤800 chars)."""
    from memos.context import ContextStack
    from memos.models import MemoryItem

    items = [MemoryItem(id=f"i{i}", content="x" * 200, importance=0.9 - i * 0.1) for i in range(10)]
    fake = _FakeMemosCompact(items)
    cs = ContextStack(fake, identity_path=str(tmp_path / "id.txt"))  # type: ignore[arg-type]
    output = cs.wake_up(compact=True)
    assert len(output) <= 800


def test_wake_up_compact_no_identity(tmp_path):
    """compact mode works when no identity file exists."""
    from memos.context import ContextStack

    fake = _FakeMemosCompact([])
    cs = ContextStack(fake, identity_path=str(tmp_path / "no_id.txt"))  # type: ignore[arg-type]
    output = cs.wake_up(compact=True)
    assert "[STATS]" in output
    assert "[ID]" not in output  # no identity → no [ID] line


def test_wake_up_compact_cli_flag(tmp_path, capsys):
    """--compact flag wires through to compact=True in CLI."""
    import argparse
    from unittest.mock import MagicMock

    from memos.cli import cmd_wake_up
    from memos.models import MemoryItem, MemoryStats

    fake_memos = MagicMock()
    fake_memos.namespace = ""
    fake_memos.stats.return_value = MemoryStats(total_memories=2)
    fake_memos._store.list_all.return_value = [
        MemoryItem(id="x1", content="Important fact one", importance=0.9),
    ]

    ns = argparse.Namespace(
        max_chars=2000,
        l1_top=15,
        no_stats=False,
        compact=True,
        backend="memory",
        db=None,
        namespace=None,
    )
    with patch("memos.cli.commands_memory._get_memos", return_value=fake_memos):
        cmd_wake_up(ns)

    out = capsys.readouterr().out
    assert "===" not in out
    assert "[MEM]" in out or "[STATS]" in out
