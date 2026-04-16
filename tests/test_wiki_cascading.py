"""Tests for Task 1.6: Wiki cascading updates on ingest."""

from __future__ import annotations

from pathlib import Path

import pytest

from memos.core import MemOS
from memos.knowledge_graph import KnowledgeGraph
from memos.wiki_living import LivingWikiEngine


@pytest.fixture
def env(tmp_path: Path):
    """Set up MemOS + LivingWikiEngine + optional KG."""
    m = MemOS(backend="json", persist_path=str(tmp_path / "store.json"))
    engine = LivingWikiEngine(m, wiki_dir=str(tmp_path / "wiki"))
    engine.init()
    yield m, engine


class TestCascadingRefresh:
    def test_refresh_entity_page_adds_trigger_note(self, env):
        m, engine = env
        item = m.learn("Alice works with Bob on Project Delta", tags=["team"])
        engine.update_for_item(item)

        # The Alice page should have a "Related Context" section referencing the item
        alice_page = engine.read_page("Alice")
        assert alice_page is not None
        assert "Related Context" in alice_page
        assert item.id in alice_page

    def test_refresh_entity_page_updates_graph_neighbors(self, env):
        m, engine = env
        kg = KnowledgeGraph(db_path=":memory:")
        kg.add_fact("Alice", "works_on", "Project Delta")
        m._kg = kg

        item = m.learn("Alice works with Bob on Project Delta", tags=["team"])
        engine.update_for_item(item)

        alice_page = engine.read_page("Alice")
        assert alice_page is not None
        assert "## Graph Neighbors" in alice_page
        assert "Project Delta" in alice_page
        kg.close()

    def test_refresh_entity_page_noop_for_missing_page(self, env):
        """_refresh_entity_page should be a no-op for non-existent entities."""
        _, engine = env
        # Should not raise
        engine._refresh_entity_page("NonExistentEntity", trigger="mem-123")

    def test_refresh_entity_page_without_trigger(self, env):
        m, engine = env
        item = m.learn("Alice works with Bob on Project Delta", tags=["team"])
        engine.update_for_item(item)

        # Calling refresh without a trigger should succeed without error
        engine._refresh_entity_page("Alice", trigger=None)

        alice_page = engine.read_page("Alice")
        assert alice_page is not None


class TestCrossReferences:
    def test_cross_references_creates_bidirectional_links(self, env):
        m, engine = env
        item = m.learn("Alice works with Bob on Project Delta", tags=["team"])
        engine.update_for_item(item)

        # Both Alice and Bob pages should exist and reference each other
        alice_page = engine.read_page("Alice")
        bob_page = engine.read_page("Bob")

        assert alice_page is not None
        assert bob_page is not None

        # Check DB backlinks are bidirectional
        db = engine._get_db()
        ab = db.execute("SELECT 1 FROM backlinks WHERE source_entity = 'Alice' AND target_entity = 'Bob'").fetchone()
        ba = db.execute("SELECT 1 FROM backlinks WHERE source_entity = 'Bob' AND target_entity = 'Alice'").fetchone()
        db.close()
        assert ab is not None
        assert ba is not None

    def test_cross_references_single_entity_is_noop(self, env):
        _, engine = env
        result = engine._update_cross_references(["OnlyOne"])
        assert result == 0

    def test_cross_references_empty_list_is_noop(self, env):
        _, engine = env
        result = engine._update_cross_references([])
        assert result == 0

    def test_cross_references_idempotent(self, env):
        m, engine = env
        item = m.learn("Alice works with Bob on Project Delta", tags=["team"])
        engine.update_for_item(item)

        # Running cross-references again should not duplicate entries
        db = engine._get_db()
        count_before = db.execute("SELECT COUNT(*) FROM backlinks").fetchone()[0]
        db.close()

        engine._update_cross_references(["Alice", "Bob"])

        db = engine._get_db()
        count_after = db.execute("SELECT COUNT(*) FROM backlinks").fetchone()[0]
        db.close()
        assert count_before == count_after

    def test_cross_references_returns_count(self, env):
        _, engine = env
        # Ensure pages exist first
        engine.create_page("Alpha", entity_type="person")
        engine.create_page("Beta", entity_type="person")
        engine.create_page("Gamma", entity_type="person")

        added = engine._update_cross_references(["Alpha", "Beta", "Gamma"])
        # 3 entities → 3 pairs → 6 bidirectional links
        assert added == 6


class TestCascadingInUpdateForItem:
    def test_update_for_item_cascades_to_all_entities(self, env):
        m, engine = env
        # First item to create Alice
        item1 = m.learn("Alice is a data scientist", tags=["people"])
        engine.update_for_item(item1)

        # Second item mentioning Alice + new entity Bob
        item2 = m.learn("Alice and Bob collaborate on deep learning research", tags=["team"])
        engine.update_for_item(item2)

        # Both should be refreshed
        alice_page = engine.read_page("Alice")
        assert alice_page is not None
        assert "Related Context" in alice_page

        bob_page = engine.read_page("Bob")
        assert bob_page is not None

    def test_update_for_item_skips_already_indexed(self, env):
        m, engine = env
        item = m.learn("Alice works alone", tags=["people"])
        result1 = engine.update_for_item(item)
        assert result1.pages_created >= 1

        # Indexing the same item again should be a no-op
        result2 = engine.update_for_item(item)
        assert result2.pages_created == 0
        assert result2.pages_updated == 0

    def test_cascading_preserves_existing_content(self, env):
        m, engine = env
        item1 = m.learn("Alice works at OpenAI", tags=["people"])
        engine.update_for_item(item1)

        alice_before = engine.read_page("Alice")
        assert "OpenAI" in alice_before

        item2 = m.learn("Alice and Bob are building MemOS together", tags=["project"])
        engine.update_for_item(item2)

        alice_after = engine.read_page("Alice")
        # Original content should still be present
        assert "OpenAI" in alice_after
        # New context should be added
        assert "Related Context" in alice_after
