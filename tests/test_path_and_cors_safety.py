"""Path traversal and CORS safety tests.

Assumptions:
- validate_safe_path rejects any resolved path containing ``..`` segments
- validate_safe_path rejects paths that escape a given base_dir
- Export/markdown and brain endpoints return 400 for traversal paths
- CORS defaults to reflecting request origin (no wildcard)
- MEMOS_CORS_ORIGINS=* restores the old permissive behaviour
- Explicit allowlist via MEMOS_CORS_ORIGINS only allows listed origins
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from memos.api import create_fastapi_app
from memos.core import MemOS
from memos.utils import validate_safe_path

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def memos():
    return MemOS(backend="memory")


@pytest.fixture()
def app(memos):
    return create_fastapi_app(memos=memos)


@pytest.fixture()
def client(app):
    return TestClient(app)


def _learn(client: TestClient, content: str = "test memory", **kwargs: object) -> str:
    payload: dict = {"content": content}
    payload.update(kwargs)
    resp = client.post("/api/v1/learn", json=payload)
    assert resp.status_code == 200, f"learn failed: {resp.text}"
    return resp.json()["id"]


# ── 1. validate_safe_path unit tests ────────────────────────────────────────


class TestValidateSafePath:
    def test_absolute_path_without_traversal(self):
        result = validate_safe_path("/tmp/safe/export")
        assert result.endswith("/tmp/safe/export") or result == "/tmp/safe/export"

    def test_relative_path_without_traversal(self):
        result = validate_safe_path("safe/subdir")
        assert "safe/subdir" in result

    def test_rejects_dotdot_traversal(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_safe_path("/tmp/../etc/passwd")

    def test_rejects_dotdot_in_middle(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_safe_path("/tmp/valid/../../etc/shadow")

    def test_rejects_dotdot_relative(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_safe_path("../../etc/passwd")

    def test_base_dir_allows_subpath(self, tmp_path):
        base = str(tmp_path)
        result = validate_safe_path(str(tmp_path / "sub" / "file.md"), base_dir=base)
        assert str(tmp_path) in result

    def test_base_dir_rejects_escape(self, tmp_path):
        base = str(tmp_path / "safe")
        with pytest.raises(ValueError, match="traversal"):
            validate_safe_path(str(tmp_path / ".." / "etc" / "passwd"), base_dir=base)

    def test_dotdot_resolved_and_rejected(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_safe_path("/tmp/good/../../../etc/shadow")


# ── 2. Export markdown endpoint path safety ─────────────────────────────────


class TestExportMarkdownPathSafety:
    def test_traversal_output_dir_rejected(self, client):
        resp = client.get("/api/v1/export/markdown", params={"output_dir": "/tmp/../etc"})
        assert resp.status_code == 400
        assert "traversal" in resp.json()["message"].lower() or "invalid" in resp.json()["message"].lower()

    def test_traversal_wiki_dir_rejected(self, client):
        resp = client.get("/api/v1/export/markdown", params={"wiki_dir": "../../etc/secrets"})
        assert resp.status_code == 400

    def test_safe_output_dir_works(self, client, tmp_path):
        _learn(client, "path safety test")
        safe_dir = str(tmp_path / "export")
        resp = client.get("/api/v1/export/markdown", params={"output_dir": safe_dir})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    def test_no_path_params_unchanged(self, client):
        _learn(client, "default export")
        resp = client.get("/api/v1/export/markdown")
        assert resp.status_code == 200


# ── 3. Brain endpoint wiki_dir path safety ──────────────────────────────────


class TestBrainPathSafety:
    def test_brain_search_traversal_wiki_dir_rejected(self, client):
        resp = client.post(
            "/api/v1/brain/search",
            json={"query": "test", "wiki_dir": "/tmp/../etc"},
        )
        assert resp.status_code == 400

    def test_brain_entity_detail_traversal_rejected(self, client):
        resp = client.get(
            "/api/v1/brain/entity/test",
            params={"wiki_dir": "../../etc"},
        )
        assert resp.status_code == 400

    def test_brain_suggest_traversal_rejected(self, client):
        resp = client.get(
            "/api/v1/brain/suggest",
            params={"wiki_dir": "/tmp/../etc"},
        )
        assert resp.status_code == 400

    def test_brain_suggestions_traversal_rejected(self, client):
        resp = client.get(
            "/api/v1/brain/suggestions",
            params={"wiki_dir": "/var/../../../etc"},
        )
        assert resp.status_code == 400

    def test_brain_connections_traversal_rejected(self, client):
        resp = client.get(
            "/api/v1/brain/connections",
            params={"wiki_dir": "../etc"},
        )
        assert resp.status_code == 400

    def test_brain_subgraph_traversal_rejected(self, client):
        resp = client.get(
            "/api/v1/brain/entity/test/subgraph",
            params={"wiki_dir": "/tmp/../../../etc"},
        )
        assert resp.status_code == 400

    def test_brain_search_without_wiki_dir_succeeds(self, client):
        _learn(client, "brain path safety test")
        resp = client.post("/api/v1/brain/search", json={"query": "brain"})
        assert resp.status_code == 200


# ── 4. CORS defaults (no env var → origin-reflection) ──────────────────────


class TestCORSDefaults:
    def test_no_origin_no_allow_origin_header(self, client):
        resp = client.options("/mcp")
        assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}

    def test_origin_reflected_when_no_env_set(self, client):
        resp = client.options("/mcp", headers={"Origin": "http://localhost:3000"})
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_post_reflects_origin(self, client):
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_discovery_reflects_origin(self, client):
        resp = client.get(
            "/.well-known/mcp.json",
            headers={"Origin": "http://example.com"},
        )
        assert resp.headers.get("access-control-allow-origin") == "http://example.com"


class TestCORSWildcard:
    """When MEMOS_CORS_ORIGINS=* the old permissive behaviour is restored."""

    def test_wildcard_allows_all(self, memos):
        with patch.dict(os.environ, {"MEMOS_CORS_ORIGINS": "*"}):
            from memos import mcp_server

            original = mcp_server._CORS_ALLOWED_ORIGINS
            mcp_server._CORS_ALLOWED_ORIGINS = "*"
            try:
                headers = mcp_server._cors_headers("http://evil.com")
                assert headers["Access-Control-Allow-Origin"] == "*"
            finally:
                mcp_server._CORS_ALLOWED_ORIGINS = original


class TestCORSAllowlist:
    """When MEMOS_CORS_ORIGINS is a comma-separated list, only listed origins pass."""

    def test_allowed_origin_passes(self):
        from memos import mcp_server

        original = mcp_server._CORS_ALLOWED_ORIGINS
        mcp_server._CORS_ALLOWED_ORIGINS = "http://localhost:3000, http://trusted.example.com"
        try:
            headers = mcp_server._cors_headers("http://localhost:3000")
            assert headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
        finally:
            mcp_server._CORS_ALLOWED_ORIGINS = original

    def test_disallowed_origin_no_header(self):
        from memos import mcp_server

        original = mcp_server._CORS_ALLOWED_ORIGINS
        mcp_server._CORS_ALLOWED_ORIGINS = "http://localhost:3000, http://trusted.example.com"
        try:
            headers = mcp_server._cors_headers("http://evil.com")
            assert "Access-Control-Allow-Origin" not in headers
        finally:
            mcp_server._CORS_ALLOWED_ORIGINS = original
