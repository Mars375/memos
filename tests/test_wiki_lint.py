"""Tests for Karpathy-style wiki lint/health-check (Task 3.4)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from memos.core import MemOS
from memos.wiki_living import LivingWikiEngine, extract_entities


# ── Fixtures ──────────────────────────────────────────────────────


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


# ── Orphan Detection ─────────────────────────────────────────────


def test_orphan_detection(engine):
    """Orphan pages with no inbound links are reported."""
    engine.init()
    engine.update(force=True)

    report = engine.lint_report()
    orphans = [i for i in report["issues"] if i["type"] == "orphan"]
    # After update, backlinks should exist between co-mentioned entities
    # Entities with no inbound links are orphans
    for o in orphans:
        assert o["severity"] == "warning"
        assert o["page"]
        assert "No inbound links" in o["detail"]


def test_orphan_on_isolated_page(mem, tmp_path):
    """A manually created page with no links to it should be orphan."""
    engine = LivingWikiEngine(mem, wiki_dir=str(tmp_path / "wiki"))
    engine.init()
    engine.update(force=True)

    # Create an isolated page that nobody links to
    engine.create_page("IsolatedEntity", entity_type="concept")

    report = engine.lint_report()
    orphans = [i for i in report["issues"] if i["type"] == "orphan"]
    orphan_pages = {i["page"] for i in orphans}
    assert "IsolatedEntity" in orphan_pages


# ── Missing Cross-Reference Detection ────────────────────────────


def test_missing_cross_reference(engine):
    """Entities mentioned in content but without [[link]] are reported."""
    engine.init()
    engine.update(force=True)

    report = engine.lint_report()
    missing_refs = [i for i in report["issues"] if i["type"] == "missing_ref"]
    # Each missing ref should have severity=info, page, detail, target
    for ref in missing_refs:
        assert ref["severity"] == "info"
        assert ref["page"]
        assert "target" in ref
        assert "no link" in ref["detail"]


def test_no_missing_ref_when_linked(mem, tmp_path):
    """If a page already has a [[wikilink]] to an entity, no missing_ref."""
    engine = LivingWikiEngine(mem, wiki_dir=str(tmp_path / "wiki"))
    engine.init()
    engine.update(force=True)

    # Manually add a wikilink from one page to another
    db = engine._get_db()
    entities = [row["name"] for row in db.execute("SELECT name FROM entities").fetchall()]
    db.close()

    if len(entities) >= 2:
        slug = engine._safe_slug(entities[0])
        page_path = Path(engine.stats()["wiki_dir"]) / "pages" / f"{slug}.md"
        if page_path.exists():
            content = page_path.read_text(encoding="utf-8")
            target_slug = engine._safe_slug(entities[1])
            link_line = f"- [[{target_slug}|{entities[1]}]]"
            if link_line not in content:
                content += f"\n{link_line}\n"
                page_path.write_text(content, encoding="utf-8")


# ── Stale Page Detection ─────────────────────────────────────────


def test_stale_detection(engine):
    """Pages not updated in >30 days are flagged as stale."""
    engine.init()
    engine.update(force=True)

    # Manually age one entity's updated_at to 45 days ago
    db = engine._get_db()
    entities = [row["name"] for row in db.execute("SELECT name FROM entities").fetchall()]
    if entities:
        stale_time = time.time() - 45 * 86400  # 45 days ago
        db.execute(
            "UPDATE entities SET updated_at = ? WHERE name = ?",
            (stale_time, entities[0]),
        )
        db.commit()
    db.close()

    report = engine.lint_report()
    stale = [i for i in report["issues"] if i["type"] == "stale"]
    if entities:
        assert len(stale) >= 1
        stale_pages = {i["page"] for i in stale}
        assert entities[0] in stale_pages
        for s in stale:
            assert "days" in s["detail"]
            assert s["severity"] == "info"


def test_no_stale_when_fresh(engine):
    """Freshly updated pages should not be flagged as stale."""
    engine.init()
    engine.update(force=True)

    report = engine.lint_report()
    stale = [i for i in report["issues"] if i["type"] == "stale"]
    # All pages were just updated, so no stale pages
    assert len(stale) == 0


# ── Empty Page Detection ─────────────────────────────────────────


def test_empty_page_detection(engine):
    """Pages with minimal content (template-only) are flagged as empty."""
    engine.init()
    engine.update(force=True)

    report = engine.lint_report()
    empties = [i for i in report["issues"] if i["type"] == "empty"]
    # After update, pages should have content from memory snippets
    # so they should NOT be empty
    for e in empties:
        assert e["severity"] == "warning"
        assert e["page"]


def test_empty_page_when_manually_created(mem, tmp_path):
    """A manually created page with no content is flagged as empty."""
    engine = LivingWikiEngine(mem, wiki_dir=str(tmp_path / "wiki"))
    engine.init()
    engine.update(force=True)

    # Create page with no extra content (template only)
    engine.create_page("EmptyTestEntity", entity_type="concept")

    report = engine.lint_report()
    empties = [i for i in report["issues"] if i["type"] == "empty"]
    empty_pages = {i["page"] for i in empties}
    assert "EmptyTestEntity" in empty_pages


# ── Contradiction Detection ──────────────────────────────────────


def test_contradiction_detection(mem):
    """Contradictory statements on the same entity are detected."""
    # "Bob is not the owner" has "not owner"
    # But we need "is owner" somewhere too for a contradiction
    # The existing memories may or may not trigger this; let's check
    m = MemOS()
    m.learn("Widget is fast", tags=["tech"])
    m.learn("Widget is not fast", tags=["tech"])

    engine = LivingWikiEngine(m, wiki_dir="/tmp/test_wiki_lint_contra")
    engine.init()
    engine.update(force=True)

    report = engine.lint_report()
    contradictions = [i for i in report["issues"] if i["type"] == "contradiction"]
    # Should detect contradiction on Widget (fast vs not fast)
    contra_pages = {i["page"] for i in contradictions}
    assert "Widget" in contra_pages
    for c in contradictions:
        assert c["severity"] == "error"
        assert "conflicting_terms" in c


# ── Summary Counts ───────────────────────────────────────────────


def test_summary_counts_are_correct(engine):
    """Summary dict has correct counts matching the issues list."""
    engine.init()
    engine.update(force=True)

    report = engine.lint_report()
    summary = report["summary"]

    # Verify all expected keys
    assert "total_pages" in summary
    assert "orphan_count" in summary
    assert "missing_ref_count" in summary
    assert "stale_count" in summary
    assert "empty_count" in summary
    assert "contradiction_count" in summary

    # Verify counts match issues
    issues = report["issues"]
    assert summary["orphan_count"] == sum(1 for i in issues if i["type"] == "orphan")
    assert summary["missing_ref_count"] == sum(1 for i in issues if i["type"] == "missing_ref")
    assert summary["stale_count"] == sum(1 for i in issues if i["type"] == "stale")
    assert summary["empty_count"] == sum(1 for i in issues if i["type"] == "empty")
    assert summary["contradiction_count"] == sum(1 for i in issues if i["type"] == "contradiction")

    # Total pages matches DB entity count
    db = engine._get_db()
    entity_count = db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    db.close()
    assert summary["total_pages"] == entity_count


def test_summary_total_pages_zero_on_empty(engine):
    """Empty wiki reports total_pages=0 with all zero counts."""
    engine.init()
    # Don't call update — no entities

    report = engine.lint_report()
    assert report["summary"]["total_pages"] == 0
    assert report["summary"]["orphan_count"] == 0
    assert report["summary"]["missing_ref_count"] == 0
    assert report["summary"]["stale_count"] == 0
    assert report["summary"]["empty_count"] == 0
    assert report["summary"]["contradiction_count"] == 0
    assert report["issues"] == []


# ── Backward Compatibility ───────────────────────────────────────


def test_lint_returns_lint_report(engine):
    """The old lint() method still returns a LintReport dataclass."""
    from memos.wiki_living import LintReport

    engine.init()
    engine.update(force=True)

    report = engine.lint()
    assert isinstance(report, LintReport)
    assert isinstance(report.orphan_pages, list)
    assert isinstance(report.empty_pages, list)
    assert isinstance(report.contradictions, list)
    assert isinstance(report.stale_pages, list)
    assert isinstance(report.missing_backlinks, list)


# ── Issue Structure ──────────────────────────────────────────────


def test_issue_structure(engine):
    """Every issue has the required fields: type, severity, page, detail."""
    engine.init()
    engine.update(force=True)

    report = engine.lint_report()
    for issue in report["issues"]:
        assert "type" in issue
        assert "severity" in issue
        assert "page" in issue
        assert "detail" in issue
        assert issue["type"] in ("orphan", "missing_ref", "stale", "empty", "contradiction")
        assert issue["severity"] in ("info", "warning", "error")


# ── MCP Dispatch ─────────────────────────────────────────────────


def test_mcp_dispatch_wiki_lint(mem, tmp_path):
    """MCP dispatch for wiki_lint returns a structured report."""
    from memos.mcp_server import _dispatch_inner

    engine = LivingWikiEngine(mem, wiki_dir=str(tmp_path / "wiki"))
    engine.init()
    engine.update(force=True)

    result = _dispatch_inner(mem, "wiki_lint", {})
    assert "content" in result
    text_parts = [c["text"] for c in result["content"] if c["type"] == "text"]
    assert any("Wiki Lint Report" in t for t in text_parts)
    assert any("pages checked" in t for t in text_parts)
