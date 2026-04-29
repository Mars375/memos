"""Tests for MCP server (JSON-RPC 2.0)."""

from __future__ import annotations

import pytest

from memos.core import MemOS
from memos.mcp_server import TOOLS, _dispatch, create_mcp_app


@pytest.fixture
def mem():
    m = MemOS()
    m.learn("Python is great for scripting", tags=["python", "dev"])
    m.learn("Use async/await for concurrency", tags=["python", "async"])
    m.learn("Docker simplifies deployment", tags=["devops"])
    return m


def test_tools_list(mem):
    assert len(TOOLS) == 26  # + diary, palace_diary_append/read, palace_list_agents, wiki_lint
    names = {t["name"] for t in TOOLS}
    assert {"memory_search", "memory_save", "memory_forget", "memory_stats"}.issubset(names)
    assert {"kg_add_fact", "kg_query_entity", "kg_timeline"}.issubset(names)
    assert {"memory_decay", "memory_reinforce"}.issubset(names)
    assert {"memory_wake_up", "memory_context_for", "brain_search"}.issubset(names)


def test_dispatch_search(mem):
    r = _dispatch(mem, "memory_search", {"query": "python", "top_k": 3})
    assert not r.get("isError")
    assert "python" in r["content"][0]["text"].lower()


def test_dispatch_search_with_advanced_filters(mem):
    r = _dispatch(
        mem,
        "memory_search",
        {
            "query": "deployment",
            "top_k": 5,
            "tags": ["devops"],
            "require_tags": ["devops"],
            "min_importance": 0.4,
            "retrieval_mode": "keyword",
        },
    )
    assert not r.get("isError")
    text = r["content"][0]["text"]
    assert "Docker simplifies deployment" in text
    assert "importance=" in text


def test_dispatch_save(mem):
    r = _dispatch(mem, "memory_save", {"content": "test mcp save", "tags": ["test"]})
    assert not r.get("isError")
    assert "Saved" in r["content"][0]["text"]


def test_dispatch_stats(mem):
    r = _dispatch(mem, "memory_stats", {})
    text = r["content"][0]["text"]
    assert "Total memories" in text
    assert "3" in text


def test_dispatch_forget_by_tag(mem):
    r = _dispatch(mem, "memory_forget", {"tag": "devops"})
    assert not r.get("isError")
    assert "1" in r["content"][0]["text"]


def test_dispatch_forget_by_tag_deletes_memories():
    """Regression: memory_forget(tag=...) must delete matching memories, not just remove the tag."""
    m = MemOS()
    m.learn("Docker rocks", tags=["devops", "infra"])
    m.learn("Kubernetes rocks", tags=["devops", "k8s"])
    m.learn("Python tip", tags=["python"])
    assert m.stats().total_memories == 3

    r = _dispatch(m, "memory_forget", {"tag": "devops"})
    assert not r.get("isError")
    assert "2" in r["content"][0]["text"]
    assert m.stats().total_memories == 1  # only "Python tip" remains


def test_dispatch_forget_by_id():
    """memory_forget(id=...) deletes a single memory."""
    m = MemOS()
    item = m.learn("temporary", tags=["tmp"])
    assert m.stats().total_memories == 1

    r = _dispatch(m, "memory_forget", {"id": item.id})
    assert not r.get("isError")
    assert "Forgotten" in r["content"][0]["text"]
    assert m.stats().total_memories == 0


def test_dispatch_decay_dry_run(mem):
    """Decay dry-run should not modify any memories."""
    r = _dispatch(mem, "memory_decay", {"apply": False})
    assert not r.get("isError")
    text = r["content"][0]["text"]
    assert "DRY RUN" in text
    assert mem.stats().total_memories == 3


def test_dispatch_decay_apply():
    """Decay with apply=True should persist via public facade."""
    import time

    m = MemOS()
    # Create an old memory eligible for decay
    item = m.learn("old memory", tags=["old"], importance=0.5)
    # Backdate created_at to make it eligible
    item.created_at = time.time() - 100 * 86400  # 100 days ago
    item.updated_at = item.created_at
    m._store.upsert(item, namespace=m._namespace)

    r = _dispatch(m, "memory_decay", {"apply": True, "min_age_days": 30, "floor": 0.0})
    assert not r.get("isError")
    text = r["content"][0]["text"]
    assert "APPLIED" in text


def test_dispatch_reinforce_found():
    """Reinforce via public facade should boost importance."""
    m = MemOS()
    item = m.learn("boost me", tags=["test"], importance=0.3)

    r = _dispatch(m, "memory_reinforce", {"memory_id": item.id, "strength": 0.2})
    assert not r.get("isError")
    assert "Reinforced" in r["content"][0]["text"]


def test_dispatch_reinforce_not_found():
    """Reinforce with invalid ID should return error."""
    m = MemOS()
    r = _dispatch(m, "memory_reinforce", {"memory_id": "nonexistent"})
    assert r.get("isError")
    assert "not found" in r["content"][0]["text"].lower()


def test_dispatch_unknown_tool(mem):
    r = _dispatch(mem, "unknown_tool", {})
    assert r.get("isError")


def test_dispatch_save_empty(mem):
    r = _dispatch(mem, "memory_save", {"content": ""})
    assert r.get("isError")


@pytest.mark.asyncio
async def test_http_initialize(mem):
    from httpx import ASGITransport, AsyncClient

    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        data = r.json()
        assert data["result"]["serverInfo"]["name"] == "memos-mcp"
        assert "tools" in data["result"]["capabilities"]


@pytest.mark.asyncio
async def test_http_parse_error_returns_jsonrpc_error(mem):
    from httpx import ASGITransport, AsyncClient

    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/mcp", content="not-json")
        assert r.status_code == 400
        data = r.json()
        assert data["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_http_mcp_rejects_oversized_body(mem, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("MEMOS_MCP_MAX_REQUEST_BYTES", "16")
    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/mcp", content=b'{"jsonrpc":"2.0","id":1,"method":"ping"}')
        assert r.status_code == 413
        assert r.json()["error"]["message"] == "Request body too large"


@pytest.mark.asyncio
async def test_legacy_root_rejects_oversized_body(mem, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("MEMOS_MCP_MAX_REQUEST_BYTES", "16")
    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/", content=b'{"jsonrpc":"2.0","id":1,"method":"ping"}')
        assert r.status_code == 413
        assert r.json()["error"]["message"] == "Request body too large"


@pytest.mark.asyncio
async def test_http_tools_list(mem):
    from httpx import ASGITransport, AsyncClient

    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert len(r.json()["result"]["tools"]) == 26


@pytest.mark.asyncio
async def test_http_tool_call(mem):
    from httpx import ASGITransport, AsyncClient

    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "memory_stats", "arguments": {}},
            },
        )
        text = r.json()["result"]["content"][0]["text"]
        assert "Total memories" in text


@pytest.mark.asyncio
async def test_standalone_mcp_requires_api_key_when_configured(mem):
    from httpx import ASGITransport, AsyncClient

    app = create_mcp_app(mem, api_keys=["sk-mcp"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_standalone_mcp_allows_valid_api_key(mem):
    from httpx import ASGITransport, AsyncClient

    app = create_mcp_app(mem, api_keys=["sk-mcp"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"X-API-Key": "sk-mcp"},
        )
        assert r.status_code == 200
        assert len(r.json()["result"]["tools"]) == 26


@pytest.mark.asyncio
async def test_http_health(mem):
    from httpx import ASGITransport, AsyncClient

    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/health")
        assert r.json()["status"] == "ok"
