"""Tests for the web dashboard."""

from __future__ import annotations

import pytest
from pathlib import Path

from memos.core import MemOS
from memos.api import create_fastapi_app
from memos.web import DASHBOARD_HTML


def test_dashboard_html_contains_title():
    assert "MemOS" in DASHBOARD_HTML
    assert "search" in DASHBOARD_HTML.lower()
    assert "learn" in DASHBOARD_HTML.lower()
    assert "graph" in DASHBOARD_HTML.lower()
    assert "d3" in DASHBOARD_HTML.lower()
    assert "analytics" in DASHBOARD_HTML.lower()
    assert "chart.js" in DASHBOARD_HTML.lower()
    assert "entity-panel" in DASHBOARD_HTML
    assert "openEntityDetail" in DASHBOARD_HTML
    assert "marked" in DASHBOARD_HTML.lower()


@pytest.mark.asyncio
async def test_dashboard_route():
    app = create_fastapi_app(backend="memory")
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "MemOS" in resp.text
        assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_dashboard_learn_and_recall():
    app = create_fastapi_app(backend="memory")
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Learn
        r = await client.post("/api/v1/learn", json={"content": "test memory", "tags": ["test"]})
        assert r.json()["status"] == "ok"
        # Recall
        r = await client.post("/api/v1/recall", json={"query": "test", "top": 5})
        assert len(r.json()["results"]) >= 1
        # Analytics
        r = await client.get("/api/v1/analytics/summary")
        assert r.json()["status"] == "ok"
        # Dashboard still works
        r = await client.get("/")
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_entity_routes_and_entity_graph(tmp_path: Path):
    kg_path = tmp_path / "kg.db"
    memos = MemOS(data_dir=str(tmp_path / "data"), backend="json", kg_db_path=str(kg_path))
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))
    memos.learn("Alice works at Acme and mentors Bob", tags=["team"], auto_kg=False)
    memos.learn("Bob ships Project Phoenix with Alice", tags=["project"], auto_kg=False)
    memos._kg.add_fact(subject="Alice", predicate="works_at", object="Acme", confidence_label="EXTRACTED")
    memos._kg.add_fact(subject="Alice", predicate="mentors", object="Bob", confidence_label="EXTRACTED")
    memos._kg.add_fact(subject="Bob", predicate="works_on", object="Project Phoenix", confidence_label="EXTRACTED")

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await client.get("/api/v1/graph", params={"kind": "entity"})
        assert graph.status_code == 200
        graph_data = graph.json()
        assert graph_data["meta"]["graph_kind"] == "entity"
        assert any(node["id"] == "Alice" for node in graph_data["nodes"])

        detail = await client.get("/api/v1/brain/entity/Alice")
        assert detail.status_code == 200
        detail_data = detail.json()
        assert detail_data["status"] == "ok"
        assert detail_data["entity"] == "Alice"
        assert "wiki_page" in detail_data

        subgraph = await client.get("/api/v1/brain/entity/Alice/subgraph")
        assert subgraph.status_code == 200
        subgraph_data = subgraph.json()
        assert subgraph_data["status"] == "ok"
        assert subgraph_data["center"] == "Alice"
        assert subgraph_data["total_edges"] >= 2
