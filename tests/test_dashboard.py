"""Tests for the web dashboard."""

from __future__ import annotations

import pytest
from memos.core import MemOS
from memos.api import create_fastapi_app
from memos.web import DASHBOARD_HTML


def test_dashboard_html_contains_title():
    assert "MemOS" in DASHBOARD_HTML
    assert "search" in DASHBOARD_HTML.lower()
    assert "learn" in DASHBOARD_HTML.lower()
    assert "graph" in DASHBOARD_HTML.lower()
    assert "d3" in DASHBOARD_HTML.lower()


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
        # Dashboard still works
        r = await client.get("/")
        assert r.status_code == 200
