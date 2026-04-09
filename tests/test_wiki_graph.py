"""Tests for graph community wiki mode (P21)."""

from __future__ import annotations

from pathlib import Path

from memos.knowledge_graph import KnowledgeGraph
from memos.wiki_graph import GraphWikiEngine


def build_sample_graph(kg: KnowledgeGraph) -> None:
    # Community A
    kg.add_fact("Alice", "works_on", "Project Phoenix")
    kg.add_fact("Project Phoenix", "uses", "Vector DB")
    kg.add_fact("Vector DB", "supports", "Alice")

    # Community B
    kg.add_fact("Orion", "maintains", "MemOS")
    kg.add_fact("MemOS", "powers", "Recall Engine")
    kg.add_fact("Recall Engine", "serves", "Orion")

    # Community C
    kg.add_fact("Paris", "located_in", "France")
    kg.add_fact("France", "part_of", "Europe")
    kg.add_fact("Europe", "contains", "Paris")

    # Bridge entity touching all three communities
    kg.add_fact("Bridge", "links", "Project Phoenix")
    kg.add_fact("Bridge", "links", "MemOS")
    kg.add_fact("Bridge", "links", "France")


def test_build_creates_graph_wiki(tmp_path):
    kg = KnowledgeGraph(db_path=":memory:")
    build_sample_graph(kg)
    engine = GraphWikiEngine(kg, output_dir=str(tmp_path / "wiki-graph"))

    result = engine.build()

    assert result.community_count >= 2
    assert result.facts_indexed == 12
    assert result.god_nodes >= 1

    out = Path(result.output_dir)
    assert (out / "index.md").exists()
    assert (out / "log.md").exists()
    assert (out / "god-nodes.md").exists()
    assert list((out / "communities").glob("*.md"))
    assert "Bridge" in (out / "god-nodes.md").read_text(encoding="utf-8")

    kg.close()


def test_read_community_returns_markdown(tmp_path):
    kg = KnowledgeGraph(db_path=":memory:")
    build_sample_graph(kg)
    engine = GraphWikiEngine(kg, output_dir=str(tmp_path / "wiki-graph"))
    engine.build()

    page = next((tmp_path / "wiki-graph" / "communities").glob("*.md"))
    content = engine.read_community(page.stem)

    assert content is not None
    assert "# Community" in content

    kg.close()


def test_incremental_update_skips_unchanged_pages(tmp_path):
    kg = KnowledgeGraph(db_path=":memory:")
    build_sample_graph(kg)
    engine = GraphWikiEngine(kg, output_dir=str(tmp_path / "wiki-graph"))

    first = engine.build()
    second = engine.build(update=True)

    assert first.pages_written >= 3
    assert second.pages_skipped >= second.community_count + 2
    assert second.pages_written == 1  # append-only log

    kg.close()


def test_incremental_update_rewrites_touched_pages(tmp_path):
    kg = KnowledgeGraph(db_path=":memory:")
    build_sample_graph(kg)
    engine = GraphWikiEngine(kg, output_dir=str(tmp_path / "wiki-graph"))

    engine.build()
    kg.add_fact("Project Phoenix", "connects_to", "Community Notes")
    result = engine.build(update=True)

    assert result.pages_written >= 2  # touched community + index/log or god nodes
    assert result.pages_skipped >= 1

    kg.close()
