"""Direct tests for wiki_models module — data classes and _safe_slug."""

from __future__ import annotations

from pathlib import Path

# Direct import from the split module
from memos.wiki_models import LintReport, LivingPage, UpdateResult, _safe_slug

# ---------------------------------------------------------------------------
# _safe_slug
# ---------------------------------------------------------------------------


class TestSafeSlug:
    """Tests for the _safe_slug helper."""

    def test_lowercase_conversion(self) -> None:
        assert _safe_slug("HelloWorld") == "helloworld"

    def test_spaces_to_hyphens(self) -> None:
        assert _safe_slug("hello world") == "hello-world"

    def test_underscores_to_hyphens(self) -> None:
        assert _safe_slug("hello_world") == "hello-world"

    def test_special_chars_stripped(self) -> None:
        assert _safe_slug("hello!@#world") == "helloworld"

    def test_leading_trailing_hyphens_stripped(self) -> None:
        assert _safe_slug("--hello--") == "hello"

    def test_empty_string_returns_unnamed(self) -> None:
        assert _safe_slug("") == "unnamed"

    def test_only_special_chars_returns_unnamed(self) -> None:
        assert _safe_slug("!@#$%") == "unnamed"

    def test_preserves_hyphens_in_middle(self) -> None:
        assert _safe_slug("Project Phoenix") == "project-phoenix"


# ---------------------------------------------------------------------------
# LivingPage
# ---------------------------------------------------------------------------


class TestLivingPage:
    """Tests for the LivingPage data class."""

    def test_defaults(self) -> None:
        page = LivingPage(entity="Alice", entity_type="person", path=Path("/tmp/alice.md"))
        assert page.memory_ids == []
        assert page.backlinks == []
        assert page.created_at == 0.0
        assert page.updated_at == 0.0
        assert page.size_bytes == 0
        assert page.is_orphan is False
        assert page.has_contradictions is False

    def test_slug_property(self) -> None:
        page = LivingPage(entity="Project Phoenix", entity_type="project", path=Path("/tmp/pp.md"))
        assert page.slug == "project-phoenix"

    def test_slug_cached(self) -> None:
        page = LivingPage(entity="TestEntity", entity_type="concept", path=Path("/tmp/te.md"))
        s1 = page.slug
        s2 = page.slug
        assert s1 == s2 == "testentity"
        assert page._slug_cache is not None

    def test_memory_count_property(self) -> None:
        page = LivingPage(
            entity="X", entity_type="default", path=Path("/tmp/x.md"), memory_ids=["m1", "m2", "m3"]
        )
        assert page.memory_count == 3

    def test_memory_count_empty(self) -> None:
        page = LivingPage(entity="X", entity_type="default", path=Path("/tmp/x.md"))
        assert page.memory_count == 0

    def test_custom_fields(self) -> None:
        page = LivingPage(
            entity="Bob",
            entity_type="person",
            path=Path("/tmp/bob.md"),
            memory_ids=["m1"],
            backlinks=["Alice"],
            created_at=1000.0,
            updated_at=2000.0,
            size_bytes=512,
            is_orphan=True,
            has_contradictions=True,
        )
        assert page.entity == "Bob"
        assert page.backlinks == ["Alice"]
        assert page.size_bytes == 512
        assert page.is_orphan is True
        assert page.has_contradictions is True


# ---------------------------------------------------------------------------
# LintReport
# ---------------------------------------------------------------------------


class TestLintReport:
    """Tests for the LintReport data class."""

    def test_defaults_empty(self) -> None:
        report = LintReport()
        assert report.orphan_pages == []
        assert report.empty_pages == []
        assert report.contradictions == []
        assert report.stale_pages == []
        assert report.missing_backlinks == []

    def test_populated_report(self) -> None:
        report = LintReport(
            orphan_pages=["Alpha", "Beta"],
            empty_pages=["Gamma"],
            contradictions=[{"entity": "Delta", "conflicting_terms": ["a", "b"]}],
            stale_pages=["Epsilon"],
            missing_backlinks=[("Zeta", "Eta")],
        )
        assert len(report.orphan_pages) == 2
        assert len(report.empty_pages) == 1
        assert len(report.contradictions) == 1
        assert len(report.stale_pages) == 1
        assert len(report.missing_backlinks) == 1


# ---------------------------------------------------------------------------
# UpdateResult
# ---------------------------------------------------------------------------


class TestUpdateResult:
    """Tests for the UpdateResult data class."""

    def test_defaults_zero(self) -> None:
        result = UpdateResult()
        assert result.pages_created == 0
        assert result.pages_updated == 0
        assert result.entities_found == 0
        assert result.memories_indexed == 0
        assert result.backlinks_added == 0

    def test_populated_result(self) -> None:
        result = UpdateResult(
            pages_created=3,
            pages_updated=5,
            entities_found=10,
            memories_indexed=20,
            backlinks_added=8,
        )
        assert result.pages_created == 3
        assert result.backlinks_added == 8


# ---------------------------------------------------------------------------
# Backward compatibility — import from wiki_living shim still works
# ---------------------------------------------------------------------------


class TestBackwardCompatImports:
    """Verify that the legacy import path still resolves the same classes."""

    def test_living_page_same_class(self) -> None:
        from memos.wiki_living import LivingPage as ShimLivingPage

        assert ShimLivingPage is LivingPage

    def test_lint_report_same_class(self) -> None:
        from memos.wiki_living import LintReport as ShimLintReport

        assert ShimLintReport is LintReport

    def test_update_result_same_class(self) -> None:
        from memos.wiki_living import UpdateResult as ShimUpdateResult

        assert ShimUpdateResult is UpdateResult
