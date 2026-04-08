"""Tests for living wiki mode (P13)."""
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


def test_extract_entities_captures_people_and_projects():
    entities = extract_entities("Alice works on Project Phoenix with Bob")
    names = {name for name, _ in entities}
    assert "Alice" in names
    assert "Bob" in names
    assert "Project Phoenix" in names


def test_init_creates_structure(engine):
    result = engine.init()
    wiki_dir = Path(result["wiki_dir"])
    assert wiki_dir.exists()
    assert (wiki_dir / "pages").exists()
    assert (wiki_dir / "index.md").exists()
    assert (wiki_dir / "log.md").exists()
    assert (wiki_dir / ".living.db").exists()


def test_update_creates_pages_and_index(engine):
    engine.init()
    result = engine.update(force=True)
    assert result.pages_created >= 3
    assert result.memories_indexed == 3

    assert engine.read_page("Alice") is not None
    assert engine.read_page("Project Phoenix") is not None

    stats = engine.stats()
    assert stats["total_entities"] >= 3
    assert stats["total_memory_links"] >= 3

    index = Path(stats["wiki_dir"]) / "index.md"
    assert index.exists()
    assert "Living Wiki Index" in index.read_text(encoding="utf-8")


def test_search_and_list(engine):
    engine.update(force=True)
    results = engine.search("Phoenix")
    assert results
    assert any("Phoenix" in r["entity"] or r["snippet"] for r in results)

    pages = engine.list_pages()
    assert pages
    assert any(p.entity == "Alice" for p in pages)


def test_lint_reports_clean_state(engine):
    engine.update(force=True)
    report = engine.lint()
    assert report.orphan_pages == []
    assert report.empty_pages == []
    assert report.contradictions == []
    assert report.missing_backlinks == []


def test_log_records_updates(engine):
    engine.update(force=True)
    entries = engine.get_log(limit=5)
    assert entries
    assert entries[0]["action"] in {"update", "create"}
