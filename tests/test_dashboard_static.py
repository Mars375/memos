"""Tests for dashboard static file serving (JS modules + CSS)."""

from __future__ import annotations

import pytest

from memos.api import create_fastapi_app


@pytest.fixture
def app():
    return create_fastapi_app(backend="memory")


@pytest.mark.asyncio
async def test_dashboard_html_served(app):
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "MemOS" in r.text
        assert "text/html" in r.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_dashboard_css_served(app):
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/static/dashboard.css")
        assert r.status_code == 200
        assert len(r.text) > 100
        assert "--bg:" in r.text or "background" in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [
    "state", "utils", "api", "graph", "filters",
    "sidebar", "panels", "wiki", "palace", "controls",
])
async def test_dashboard_js_modules_served(app, module):
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/static/js/{module}.js")
        assert r.status_code == 200
        assert len(r.text) > 10
        # state.js has only let/const, other modules have functions
        assert len(r.text) > 10 and ("function" in r.text or "let " in r.text or "const " in r.text)


@pytest.mark.asyncio
async def test_dashboard_html_references_static_assets(app):
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        html = r.text
        # CSS link
        assert '/static/dashboard.css' in html
        # All JS modules
        for module in ["state", "utils", "api", "graph", "filters",
                        "sidebar", "panels", "wiki", "palace", "controls"]:
            assert f'/static/js/{module}.js' in html, f"Missing script reference: {module}"
        # No inline <style> block
        assert "<style>" not in html
        # CDN deps
        assert "force-graph" in html
        assert "chart.js" in html
