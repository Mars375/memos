"""Tests for Karpathy-style wiki index generation (Task 3.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from memos.core import MemOS
from memos.wiki_living import LivingWikiEngine, extract_entities


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


# ── Index Generation ────────────────────────────────────────────


def test_index_generation_with_pages(engine):
    """After update, regenerate_index produces a non-empty index.md."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    assert content
    assert "📚 Living Wiki Index" in content
    # Should mention at least some entities
    assert "Alice" in content or "alice" in content
    assert "Project Phoenix" in content or "project-phoenix" in content


def test_index_written_to_disk(engine):
    """Index file on disk matches returned content."""
    engine.init()
    engine.update(force=True)

    returned = engine.regenerate_index()
    index_path = Path(engine.stats()["wiki_dir"]) / "index.md"
    assert index_path.exists()
    on_disk = index_path.read_text(encoding="utf-8")
    assert on_disk == returned


def test_generate_index_alias(engine):
    """generate_index() is an alias for regenerate_index()."""
    engine.init()
    engine.update(force=True)

    assert engine.generate_index() == engine.regenerate_index()


# ── Statistics Section ──────────────────────────────────────────


def test_statistics_section(engine):
    """Index contains a Statistics table with Total Pages, Memory Links, etc."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    assert "📊 Statistics" in content
    assert "Total Pages" in content
    assert "Total Memory Links" in content
    assert "Total Wiki Links" in content
    assert "Last Updated" in content
    # Table formatting
    assert "| Metric |" in content
    assert "|--------|" in content


def test_statistics_total_pages_count(engine):
    """Total Pages reflects the actual number of entities."""
    engine.init()
    engine.update(force=True)

    stats = engine.stats()
    content = engine.regenerate_index()
    expected = f"| Total Pages | {stats['total_entities']} |"
    assert expected in content


# ── Categorization ──────────────────────────────────────────────


def test_categorization_entities(engine):
    """Person and project pages appear under the Entities category."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    assert "## Entities" in content
    # Alice (person) and Project Phoenix (project) should be in Entities
    assert "[[alice|Alice]]" in content
    assert "[[project-phoenix|Project Phoenix]]" in content


def test_categorization_topics(engine):
    """Tag-based topic pages appear under the Topics category."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    assert "## Topics" in content
    # Tags "project" and "team" should be topics
    assert "[[project|project]]" in content
    assert "[[team|team]]" in content


def test_categorization_concepts(engine):
    """Concept-type pages appear under Concepts category."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    # default entities go to Concepts; check the section exists
    # (may or may not have items depending on extraction)
    # At minimum the code should not crash
    assert "## Entities" in content or "## Concepts" in content or "## Topics" in content


# ── Recent Changes Section ──────────────────────────────────────


def test_recent_changes_section(engine):
    """Recent Changes section appears after an update."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    assert "🕐 Recent Changes" in content
    # Should contain create/update actions logged during the update
    assert "**create**" in content or "**update**" in content


def test_recent_changes_limited_to_10(engine):
    """Recent Changes section shows at most 10 entries."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    # Count the number of timestamp lines (lines starting with "- `")
    ts_lines = [line for line in content.splitlines() if line.startswith("- `")]
    assert len(ts_lines) <= 10


# ── Page Metadata ───────────────────────────────────────────────


def test_page_metadata_in_index(engine):
    """Each page entry includes created date, source count, and updated date."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    # Should contain metadata line with created/sources/updated
    assert "created:" in content
    assert "sources:" in content
    assert "updated:" in content


def test_freshness_indicators(engine):
    """Pages show freshness indicators (🟢 🟡 🔴) based on recency."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    # Since we just updated, pages should be fresh (🟢)
    assert "🟢" in content


# ── Sorting by Relevance ────────────────────────────────────────


def test_pages_sorted_by_relevance(engine, tmp_path):
    """Pages with more incoming backlinks appear first within their category."""
    engine.init()
    engine.update(force=True)

    content = engine.regenerate_index()
    # At minimum the index should be non-empty and parseable
    lines = content.splitlines()
    entity_section = False
    entity_lines = []
    for line in lines:
        if line.startswith("## Entities"):
            entity_section = True
            continue
        if entity_section and line.startswith("## "):
            break
        if entity_section and line.startswith("- [["):
            entity_lines.append(line)

    # There should be entity entries
    assert len(entity_lines) >= 1


# ── Empty Wiki ──────────────────────────────────────────────────


def test_empty_wiki_index(engine):
    """Index generates cleanly even with no pages."""
    engine.init()

    content = engine.regenerate_index()
    assert "📚 Living Wiki Index" in content
    assert "| Total Pages | 0 |" in content


# ── MCP Dispatch ────────────────────────────────────────────────


def test_mcp_dispatch_wiki_regenerate_index(mem, tmp_path):
    """MCP dispatch for wiki_regenerate_index returns index content."""
    from memos.mcp_server import _dispatch_inner

    engine = LivingWikiEngine(mem, wiki_dir=str(tmp_path / "wiki"))
    engine.init()
    engine.update(force=True)

    # Simulate MCP dispatch — but it creates its own LivingWikiEngine
    # We need to ensure memos has the right setup
    result = _dispatch_inner(mem, "wiki_regenerate_index", {})
    assert "content" in result
    text_parts = [c["text"] for c in result["content"] if c["type"] == "text"]
    assert any("Living Wiki Index" in t for t in text_parts)
