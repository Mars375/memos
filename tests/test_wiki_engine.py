"""Direct tests for wiki_engine module — LivingWikiEngine imported from the split path."""

from __future__ import annotations

from pathlib import Path

import pytest

from memos.core import MemOS

# Direct import from the split module — NOT via wiki_living shim
from memos.wiki_engine import LivingWikiEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem():
    m = MemOS()
    m.learn("Alice works on Project Phoenix with Bob", tags=["project", "team"])
    m.learn("Project Phoenix is a search tool for MemOS", tags=["project"])
    m.learn("Bob is not the owner of Project Phoenix", tags=["project", "team"])
    return m


@pytest.fixture
def engine(mem, tmp_path):
    return LivingWikiEngine(mem, wiki_dir=str(tmp_path / "wiki"))


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestEngineInit:
    """Tests for LivingWikiEngine.init() via direct import."""

    def test_init_creates_structure(self, engine: LivingWikiEngine) -> None:
        result = engine.init()
        wiki_dir = Path(result["wiki_dir"])
        assert wiki_dir.exists()
        assert (wiki_dir / "pages").exists()
        assert (wiki_dir / "index.md").exists()
        assert (wiki_dir / "log.md").exists()
        assert (wiki_dir / ".living.db").exists()

    def test_init_idempotent(self, engine: LivingWikiEngine) -> None:
        engine.init()
        result2 = engine.init()
        assert result2["initialized"] is True


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestEngineUpdate:
    """Tests for LivingWikiEngine.update() via direct import."""

    def test_update_creates_pages(self, engine: LivingWikiEngine) -> None:
        engine.init()
        result = engine.update(force=True)
        assert result.pages_created >= 3
        assert result.memories_indexed == 3

    def test_update_creates_readable_pages(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        assert engine.read_page("Alice") is not None
        assert engine.read_page("Project Phoenix") is not None

    def test_update_builds_index(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        index = engine._wiki_dir / "index.md"
        assert index.exists()
        content = index.read_text(encoding="utf-8")
        assert "Living Wiki Index" in content

    def test_update_returns_update_result(self, engine: LivingWikiEngine) -> None:
        from memos.wiki_models import UpdateResult

        result = engine.update(force=True)
        assert isinstance(result, UpdateResult)

    def test_update_for_item_incremental(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)

        mem = engine._memos
        item = mem.learn("Charlie joined Project Phoenix recently")
        result = engine.update_for_item(item)
        assert result.memories_indexed == 1
        assert engine.read_page("Charlie") is not None


# ---------------------------------------------------------------------------
# Search and read
# ---------------------------------------------------------------------------


class TestEngineSearchRead:
    """Tests for search/read via direct import."""

    def test_search_finds_content(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        results = engine.search("Phoenix")
        assert results
        assert any("Phoenix" in r["entity"] or "Phoenix" in r.get("snippet", "") for r in results)

    def test_read_page_existing(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        page = engine.read_page("Alice")
        assert page is not None
        assert "Alice" in page

    def test_read_page_nonexistent(self, engine: LivingWikiEngine) -> None:
        assert engine.read_page("NonExistentEntity12345") is None


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------


class TestEngineLint:
    """Tests for LivingWikiEngine.lint() via direct import."""

    def test_lint_returns_lint_report(self, engine: LivingWikiEngine) -> None:
        from memos.wiki_models import LintReport

        engine.update(force=True)
        report = engine.lint()
        assert isinstance(report, LintReport)

    def test_lint_clean_state(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        report = engine.lint()
        assert report.contradictions == []
        assert report.missing_backlinks == []

    def test_lint_report_detailed(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        report = engine.lint_report()
        assert "issues" in report
        assert "summary" in report
        assert "total_pages" in report["summary"]


# ---------------------------------------------------------------------------
# Stats and list
# ---------------------------------------------------------------------------


class TestEngineStatsList:
    """Tests for stats/list_pages via direct import."""

    def test_stats(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        s = engine.stats()
        assert s["total_entities"] >= 3
        assert s["total_memory_links"] >= 3
        assert "wiki_dir" in s

    def test_list_pages(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        pages = engine.list_pages()
        assert pages
        assert any(p.entity == "Alice" for p in pages)


# ---------------------------------------------------------------------------
# Index generation
# ---------------------------------------------------------------------------


class TestEngineGenerateIndex:
    """Tests for generate_index / regenerate_index via direct import."""

    def test_generate_index(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        content = engine.generate_index()
        assert "Living Wiki Index" in content

    def test_regenerate_index_alias(self, engine: LivingWikiEngine) -> None:
        """regenerate_index is an alias for generate_index."""
        engine.update(force=True)
        c1 = engine.generate_index()
        c2 = engine.regenerate_index()
        assert c1 == c2


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------


class TestEngineLog:
    """Tests for get_log / get_log_markdown via direct import."""

    def test_get_log(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        entries = engine.get_log(limit=5)
        assert entries
        assert entries[0]["action"] in {"update", "create"}

    def test_get_log_markdown(self, engine: LivingWikiEngine) -> None:
        engine.update(force=True)
        md = engine.get_log_markdown()
        assert "Wiki Activity Log" in md


# ---------------------------------------------------------------------------
# Safe slug delegation
# ---------------------------------------------------------------------------


class TestEngineSlug:
    """Tests that the engine's _safe_slug delegates to wiki_models._safe_slug."""

    def test_slug_delegation(self, engine: LivingWikiEngine) -> None:
        assert engine._safe_slug("Project Phoenix") == "project-phoenix"
        assert engine._safe_slug("") == "unnamed"


# ---------------------------------------------------------------------------
# Create page
# ---------------------------------------------------------------------------


class TestEngineCreatePage:
    """Tests for create_page via direct import."""

    def test_create_page(self, engine: LivingWikiEngine) -> None:
        engine.init()
        result = engine.create_page("TestEntity", entity_type="concept", content="Some notes")
        assert result["status"] == "created"

        page = engine.read_page("TestEntity")
        assert page is not None
        assert 'title: "TestEntity"' in page

    def test_create_page_duplicate(self, engine: LivingWikiEngine) -> None:
        engine.init()
        engine.create_page("DupEntity", entity_type="default")
        result = engine.create_page("DupEntity", entity_type="default")
        assert result["status"] == "already_exists"

    def test_create_page_slug_collision_duplicate(self, engine: LivingWikiEngine) -> None:
        engine.init()
        first = engine.create_page("Foo Bar", entity_type="default")
        second = engine.create_page("Foo-Bar", entity_type="default")

        assert first["status"] == "created"
        assert second["status"] == "already_exists"

        page = engine.read_page("Foo Bar")
        assert page is not None
        assert 'title: "Foo Bar"' in page


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Legacy import path from wiki_living resolves to the same class."""

    def test_engine_same_class(self) -> None:
        from memos.wiki_living import LivingWikiEngine as ShimEngine

        assert ShimEngine is LivingWikiEngine
