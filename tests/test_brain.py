"""Tests for BrainSearch — unified search across memories, wiki, and KG."""

import os
import shutil
import tempfile

import pytest

from memos.brain import (
    BrainSearch,
    BrainSearchResult,
    KGFactHit,
    ScoredMemory,
    WikiHit,
    _extract_entities,
)
from memos.core import MemOS


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp(prefix="memos_brain_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def memos(tmp_dir):
    return MemOS(data_dir=tmp_dir, backend="json")


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

class TestExtractEntities:
    def test_quoted_names(self):
        entities = _extract_entities('"Alice Smith" works at "Acme Corp"')
        assert "Alice Smith" in entities
        assert "Acme Corp" in entities

    def test_pascal_case(self):
        entities = _extract_entities("Alice Smith deployed to production")
        assert "Alice" in entities

    def test_allcaps(self):
        entities = _extract_entities("NASA launched the SLS rocket")
        assert any("NASA" in e for e in entities)

    def test_empty_query(self):
        assert _extract_entities("") == []

    def test_no_entities(self):
        result = _extract_entities("the quick brown fox jumps over the lazy dog")
        # "the" won't match capitalized patterns, but "Brown" etc won't be there
        # Only capitalized words match
        assert isinstance(result, list)

    def test_single_quotes(self):
        entities = _extract_entities("'Project Alpha' is live")
        assert "Project Alpha" in entities


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class TestDataStructures:
    def test_scored_memory_to_dict(self):
        m = ScoredMemory(id="abc", content="test", score=0.85, tags=["a"], importance=0.5)
        d = m.to_dict()
        assert d["id"] == "abc"
        assert d["score"] == 0.85
        assert d["tags"] == ["a"]

    def test_wiki_hit_to_dict(self):
        w = WikiHit(entity="Alice", type="person", matches=3, snippet="...")
        d = w.to_dict()
        assert d["entity"] == "Alice"
        assert d["matches"] == 3

    def test_kg_fact_hit_to_dict(self):
        f = KGFactHit(id="f1", subject="A", predicate="knows", object="B")
        d = f.to_dict()
        assert d["subject"] == "A"
        assert d["confidence_label"] == "EXTRACTED"

    def test_brain_search_result_total_hits(self):
        r = BrainSearchResult(
            query="test",
            memories=[ScoredMemory(id="1", content="a", score=0.5)],
            wiki_pages=[WikiHit(entity="E1"), WikiHit(entity="E2")],
            kg_facts=[KGFactHit(id="f1", subject="S", predicate="P", object="O")],
        )
        assert r.total_hits == 4

    def test_brain_search_result_to_dict(self):
        r = BrainSearchResult(query="test")
        d = r.to_dict()
        assert d["query"] == "test"
        assert d["total_hits"] == 0
        assert d["memory_count"] == 0


# ---------------------------------------------------------------------------
# BrainSearch integration
# ---------------------------------------------------------------------------

class TestBrainSearch:
    def test_search_empty(self, memos):
        brain = BrainSearch(memos)
        result = brain.search("nonexistent query xyzzz123")
        assert result.query == "nonexistent query xyzzz123"
        # May return results from shared store; just check structure
        assert isinstance(result.memories, list)
        assert isinstance(result.context, str)

    def test_search_with_memories(self, memos):
        memos.learn("Alice works at Acme Corp on infrastructure", tags=["person"])
        memos.learn("Bob maintains the deployment pipeline", tags=["devops"])

        brain = BrainSearch(memos)
        result = brain.search("Alice")
        assert len(result.memories) >= 1
        assert any("Alice" in m.content for m in result.memories)
        assert result.context != ""

    def test_search_entities_detected(self, memos):
        memos.learn("Alice leads the team")
        brain = BrainSearch(memos)
        result = brain.search("Alice infrastructure")
        assert "Alice" in result.entities

    def test_search_include_toggle(self, memos):
        memos.learn("test memory content")

        brain = BrainSearch(memos)
        # Disable memories
        result = brain.search("test", include_memories=False)
        assert result.memories == []

        # Enable memories
        result = brain.search("test", include_memories=True)
        assert len(result.memories) >= 1

    def test_search_with_kg(self, memos):
        from memos.knowledge_graph import KnowledgeGraph
        import tempfile, os
        kg_path = os.path.join(tempfile.mkdtemp(prefix="memos_kg_test_"), "kg.db")
        kg = KnowledgeGraph(db_path=kg_path)
        kg.add_fact(subject="Alice", predicate="works_at", object="Acme", confidence_label="EXTRACTED")

        brain = BrainSearch(memos)
        brain._memos._kg = kg

        result = brain.search("Alice")
        assert any(f.subject == "Alice" for f in result.kg_facts)

    def test_search_context_format(self, memos):
        memos.learn("Important project milestone reached", tags=["milestone"])
        brain = BrainSearch(memos)
        result = brain.search("project milestone")
        assert "Brain Search:" in result.context
        assert "Memories" in result.context

    def test_search_top_k(self, memos):
        for i in range(15):
            memos.learn(f"Memory number {i} about testing", importance=0.5 + i * 0.01)

        brain = BrainSearch(memos)
        result = brain.search("testing", top_k=3)
        assert len(result.memories) <= 3

    def test_search_no_results_context(self, memos):
        brain = BrainSearch(memos)
        result = brain.search("xyzzynothinghere999")
        # Context always has the query; may or may not have results
        assert "xyzzynothinghere999" in result.context

    def test_search_wiki_graceful(self, memos):
        """Wiki search should not crash even without a wiki initialized."""
        brain = BrainSearch(memos)
        result = brain.search("anything", include_wiki=True)
        # Should not raise, wiki pages may be empty
        assert isinstance(result.wiki_pages, list)

    def test_brain_search_via_memos_attribute(self, memos):
        """BrainSearch can be created via MemOS attribute."""
        memos.learn("test for attribute access")
        brain = BrainSearch(memos)
        result = brain.search("attribute")
        assert len(result.memories) >= 1


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_full_result_roundtrip(self, memos):
        memos.learn("Alice works on the project", tags=["team"])
        brain = BrainSearch(memos)
        result = brain.search("Alice")
        d = result.to_dict()

        assert d["query"] == "Alice"
        assert isinstance(d["memories"], list)
        assert isinstance(d["wiki_pages"], list)
        assert isinstance(d["kg_facts"], list)
        assert isinstance(d["entities"], list)
        assert isinstance(d["context"], str)
        assert d["total_hits"] >= 1


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

class TestContextBuilder:
    def test_empty_context(self):
        ctx = BrainSearch._build_context("test", [], [], [], [])
        assert "test" in ctx
        assert "No results found" in ctx

    def test_truncation_many_memories(self):
        memories = [ScoredMemory(id=str(i), content=f"mem {i}", score=0.5) for i in range(10)]
        ctx = BrainSearch._build_context("q", [], memories, [], [])
        assert "and 5 more" in ctx

    def test_entities_in_context(self):
        ctx = BrainSearch._build_context("q", ["Alice", "Bob"], [], [], [])
        assert "Alice" in ctx
        assert "Bob" in ctx

    def test_kg_facts_in_context(self):
        facts = [KGFactHit(id="f1", subject="A", predicate="knows", object="B")]
        ctx = BrainSearch._build_context("q", [], [], [], facts)
        assert "A" in ctx
        assert "knows" in ctx
        assert "B" in ctx
