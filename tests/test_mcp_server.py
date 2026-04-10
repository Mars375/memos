"""Tests for MCP server (JSON-RPC 2.0)."""
from __future__ import annotations
import pytest
from memos.core import MemOS
from memos.mcp_server import create_mcp_app, TOOLS, _dispatch


@pytest.fixture
def mem():
    m = MemOS()
    m.learn("Python is great for scripting", tags=["python", "dev"])
    m.learn("Use async/await for concurrency", tags=["python", "async"])
    m.learn("Docker simplifies deployment", tags=["devops"])
    m.create_namespace("orion", description="SRE agent")
    m.namespace = "orion"
    m.learn("Rotate nginx logs weekly", tags=["ops"])
    m.namespace = ""
    return m


def test_tools_list(mem):
    assert len(TOOLS) == 17  # prior tools + 2 namespace tools (P30)
    names = {t["name"] for t in TOOLS}
    assert {"memory_search", "memory_save", "memory_forget", "memory_stats"}.issubset(names)
    assert {"kg_add_fact", "kg_query_entity", "kg_timeline"}.issubset(names)
    assert {"memory_decay", "memory_reinforce"}.issubset(names)
    assert {"memory_wake_up", "memory_context_for"}.issubset(names)
    assert {"namespace_list", "namespace_stats"}.issubset(names)


def test_dispatch_search(mem):
    r = _dispatch(mem, "memory_search", {"query": "python", "top_k": 3})
    assert not r.get("isError")
    assert "python" in r["content"][0]["text"].lower()


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


def test_dispatch_unknown_tool(mem):
    r = _dispatch(mem, "unknown_tool", {})
    assert r.get("isError")


def test_dispatch_namespace_list(mem):
    r = _dispatch(mem, "namespace_list", {})
    assert not r.get("isError")
    assert "orion" in r["content"][0]["text"]


def test_dispatch_namespace_stats(mem):
    r = _dispatch(mem, "namespace_stats", {"name": "orion"})
    assert not r.get("isError")
    text = r["content"][0]["text"]
    assert "Namespace: orion" in text
    assert "Memories: 1" in text


def test_dispatch_save_empty(mem):
    r = _dispatch(mem, "memory_save", {"content": ""})
    assert r.get("isError")


@pytest.mark.asyncio
async def test_http_initialize(mem):
    from httpx import AsyncClient, ASGITransport
    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        data = r.json()
        assert data["result"]["serverInfo"]["name"] == "memos-mcp"
        assert "tools" in data["result"]["capabilities"]


@pytest.mark.asyncio
async def test_http_tools_list(mem):
    from httpx import AsyncClient, ASGITransport
    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert len(r.json()["result"]["tools"]) == 17


@pytest.mark.asyncio
async def test_http_tool_call(mem):
    from httpx import AsyncClient, ASGITransport
    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/mcp", json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "memory_stats", "arguments": {}}
        })
        text = r.json()["result"]["content"][0]["text"]
        assert "Total memories" in text


@pytest.mark.asyncio
async def test_http_health(mem):
    from httpx import AsyncClient, ASGITransport
    app = create_mcp_app(mem)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/health")
        assert r.json()["status"] == "ok"
