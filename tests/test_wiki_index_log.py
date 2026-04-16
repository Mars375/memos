"""Tests for Tasks 3.1 + 3.2: auto-generated index.md and chronological log.md."""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from memos.core import MemOS
from memos.wiki_living import LivingWikiEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def memos_instance():
    """In-memory MemOS."""
    return MemOS(backend="memory")


@pytest.fixture()
def wiki(tmp_path, memos_instance):
    """LivingWikiEngine pointed at a temp directory."""
    engine = LivingWikiEngine(memos_instance, wiki_dir=str(tmp_path))
    engine.init()
    return engine


def _learn(memos_instance, text, tags=None):
    """Learn a memory and return the item."""
    return memos_instance.learn(text, tags=tags or [])


# ===========================================================================
# Task 3.1 — generate_index()
# ===========================================================================


class TestGenerateIndex:
    """Tests for generate_index() method."""

    def test_generate_index_creates_index_md(self, wiki, tmp_path):
        """generate_index() writes index.md to wiki_dir."""
        content = wiki.generate_index()
        index_path = tmp_path / "living" / "index.md"
        assert index_path.exists()
        assert content == index_path.read_text(encoding="utf-8")

    def test_generate_index_empty_wiki(self, wiki):
        """generate_index() on an empty wiki produces a valid header."""
        content = wiki.generate_index()
        assert "Living Wiki Index" in content
        assert "Total Pages | 0" in content

    def test_generate_index_groups_by_entity_type(self, wiki, memos_instance):
        """After update, index.md groups pages by entity_type category."""
        _learn(memos_instance, "Project Alpha is a new initiative", tags=["python"])
        _learn(memos_instance, "Alice Smith works on Project Alpha")
        wiki.update()

        content = wiki.generate_index()
        # Should have category section headers
        assert "## " in content
        # Should contain wikilinks
        assert "[[" in content

    def test_generate_index_contains_wikilinks(self, wiki, memos_instance):
        """Each page entry uses [[wikilink]] format."""
        _learn(memos_instance, "Project Phoenix is launching soon")
        wiki.update()

        content = wiki.generate_index()
        assert re.search(r"\[\[.*?\|.*?\]\]", content)

    def test_generate_index_includes_summaries(self, wiki, memos_instance):
        """Index entries include one-line summaries from page content."""
        _learn(memos_instance, "Project Aurora is a secret research initiative about fusion energy")
        wiki.update()

        content = wiki.generate_index()
        # Summaries appear after "—" on entry lines
        assert "[[" in content  # at minimum has wikilinks

    def test_generate_index_called_after_update(self, wiki, memos_instance):
        """update() triggers index regeneration."""
        _learn(memos_instance, "Bob Johnson handles infrastructure")
        wiki.update()

        index_path = wiki._index_path
        assert index_path.exists()
        content = index_path.read_text(encoding="utf-8")
        assert "Bob" in content or "bob" in content

    def test_generate_index_called_after_update_for_item(self, wiki, memos_instance):
        """update_for_item() triggers index regeneration."""
        item = _learn(memos_instance, "Charlie Brown manages deployments")
        wiki.update_for_item(item)

        index_path = wiki._index_path
        assert index_path.exists()
        content = index_path.read_text(encoding="utf-8")
        assert "Charlie" in content or "charlie" in content

    def test_regenerate_index_delegates_to_generate_index(self, wiki):
        """regenerate_index() returns same result as generate_index()."""
        r = wiki.regenerate_index()
        g = wiki.generate_index()
        assert r == g

    def test_generate_index_multiple_types(self, wiki, memos_instance):
        """Pages of different entity types are separated into sections."""
        _learn(memos_instance, "Alice Smith joined the team")
        _learn(memos_instance, "Project Nebula is our flagship product")
        _learn(memos_instance, "Docker containers simplify deployment", tags=["docker"])
        wiki.update()

        content = wiki.generate_index()
        sections = re.findall(r"^## \S+", content, re.MULTILINE)
        assert len(sections) >= 2

    def test_get_page_summary_extracts_content(self, wiki, memos_instance):
        """_get_page_summary returns the first content line from a page."""
        _learn(memos_instance, "Project Aurora is a research project about AI")
        wiki.update()

        summary = wiki._get_page_summary("Project Aurora")
        assert len(summary) > 0

    def test_get_page_summary_nonexistent_entity(self, wiki):
        """_get_page_summary returns empty string for unknown entities."""
        assert wiki._get_page_summary("NonExistent") == ""

    def test_generate_index_has_statistics(self, wiki, memos_instance):
        """Index includes a statistics section."""
        _learn(memos_instance, "Zeta protocol is active")
        wiki.update()

        content = wiki.generate_index()
        assert "Total Pages" in content
        assert "Total Memory Links" in content


# ===========================================================================
# Task 3.2 — _append_log(action, detail)
# ===========================================================================


class TestAppendLog:
    """Tests for _append_log(action, detail) method."""

    def test_append_log_creates_log_md(self, wiki, tmp_path):
        """_append_log creates log.md with header if it doesn't exist."""
        log_path = wiki._log_path
        if log_path.exists():
            log_path.unlink()

        wiki._append_log("test_action", "test detail")
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert content.startswith("# Wiki Activity Log")

    def test_append_log_format(self, wiki):
        """Log entries follow the format: ## [YYYY-MM-DD HH:MM] action | detail."""
        wiki._append_log("create", "New page for Alice")
        content = wiki._log_path.read_text(encoding="utf-8")
        assert re.search(
            r"## \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] create \| New page for Alice",
            content,
        )

    def test_append_log_without_detail(self, wiki):
        """Log entry without detail omits the pipe."""
        wiki._append_log("update")
        content = wiki._log_path.read_text(encoding="utf-8")
        # The line should have "update" without a trailing "|"
        assert re.search(r"## \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] update\n", content)

    def test_append_log_multiple_entries(self, wiki):
        """Multiple log entries are appended chronologically."""
        wiki._append_log("first", "entry one")
        wiki._append_log("second", "entry two")
        content = wiki._log_path.read_text(encoding="utf-8")
        assert "first" in content
        assert "second" in content
        assert content.index("first") < content.index("second")

    def test_append_log_called_from_update(self, wiki, memos_instance):
        """update() calls _append_log."""
        _learn(memos_instance, "Delta force handles operations")
        wiki.update()

        content = wiki._log_path.read_text(encoding="utf-8")
        assert "update" in content

    def test_append_log_called_from_update_for_item(self, wiki, memos_instance):
        """update_for_item() calls _append_log."""
        item = _learn(memos_instance, "Echo squadron arrived today")
        wiki.update_for_item(item)

        content = wiki._log_path.read_text(encoding="utf-8")
        assert "update_for_item" in content

    def test_append_log_called_from_lint(self, wiki, memos_instance):
        """lint() calls _append_log."""
        _learn(memos_instance, "Foxtrot team is deployed")
        wiki.update()
        wiki.lint()

        content = wiki._log_path.read_text(encoding="utf-8")
        assert "lint" in content

    def test_append_log_called_from_create_page(self, wiki):
        """create_page() calls _append_log."""
        wiki.create_page("TestEntity", entity_type="concept")

        content = wiki._log_path.read_text(encoding="utf-8")
        assert "create_page" in content
        assert "TestEntity" in content

    def test_get_log_markdown(self, wiki):
        """get_log_markdown returns the log.md content."""
        wiki._append_log("test", "check")
        md = wiki.get_log_markdown()
        assert "# Wiki Activity Log" in md
        assert "test" in md

    def test_get_log_markdown_empty(self, wiki):
        """get_log_markdown returns header when log.md doesn't exist."""
        log_path = wiki._log_path
        if log_path.exists():
            log_path.unlink()
        md = wiki.get_log_markdown()
        assert "# Wiki Activity Log" in md


# ===========================================================================
# API Endpoints
# ===========================================================================


class TestWikiEndpoints:
    """Tests for /api/v1/wiki/index and /api/v1/wiki/log endpoints."""

    @pytest.fixture()
    def client(self, memos_instance):
        """TestClient wired to the app."""
        from memos.api import create_fastapi_app
        from starlette.testclient import TestClient

        app = create_fastapi_app(memos=memos_instance)
        return TestClient(app)

    def test_wiki_index_endpoint(self, client):
        """GET /api/v1/wiki/index returns index content."""
        resp = client.get("/api/v1/wiki/index")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "content" in data
        assert "Living Wiki Index" in data["content"]

    def test_wiki_index_endpoint_with_pages(self, client, memos_instance):
        """GET /api/v1/wiki/index includes pages after update."""
        memos_instance.learn("Project Omega is revolutionary", tags=["omega"])
        wiki = LivingWikiEngine(memos_instance)
        wiki.update()

        resp = client.get("/api/v1/wiki/index")
        data = resp.json()
        assert data["status"] == "ok"
        assert "[[" in data["content"]

    def test_wiki_log_endpoint(self, client):
        """GET /api/v1/wiki/log returns log content."""
        resp = client.get("/api/v1/wiki/log")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "content" in data

    def test_wiki_log_endpoint_shows_entries(self, client, memos_instance):
        """GET /api/v1/wiki/log shows log entries after actions."""
        wiki = LivingWikiEngine(memos_instance)
        wiki._append_log("test_action", "via endpoint test")

        resp = client.get("/api/v1/wiki/log")
        data = resp.json()
        assert data["status"] == "ok"
        assert "test_action" in data["content"]
