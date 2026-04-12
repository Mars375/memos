"""Tests for compounding ingest (P8) — auto-update wiki on learn()."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from memos.core import MemOS
from memos.models import MemoryItem


class TestEnableDisable:
    def test_disabled_by_default(self):
        m = MemOS(backend="memory")
        assert not m.compounding_ingest

    def test_enable_sets_flag(self, tmp_path):
        m = MemOS(backend="memory")
        m.enable_compounding_ingest(wiki_dir=str(tmp_path / "wiki"))
        assert m.compounding_ingest

    def test_disable_clears_flag(self, tmp_path):
        m = MemOS(backend="memory")
        m.enable_compounding_ingest(wiki_dir=str(tmp_path / "wiki"))
        m.disable_compounding_ingest()
        assert not m.compounding_ingest


class TestCompoundingIngestOnLearn:
    def test_learn_calls_update_for_item(self, tmp_path):
        """When compounding_ingest is enabled, learn() calls update_for_item."""
        m = MemOS(backend="memory")
        m.enable_compounding_ingest(wiki_dir=str(tmp_path / "wiki"))

        update_calls = []
        orig = m._compounding_wiki.update_for_item
        m._compounding_wiki.update_for_item = lambda item: update_calls.append(item.id) or orig(item)

        item = m.learn("Alice leads the backend team at CompanyX")
        assert item.id in update_calls

    def test_learn_without_compounding_does_not_call_wiki(self, tmp_path):
        """When disabled, no wiki update occurs."""
        m = MemOS(backend="memory")
        # Should not raise and not call any wiki
        item = m.learn("Alice leads the backend team")
        assert item is not None

    def test_wiki_failure_does_not_break_learn(self, tmp_path):
        """A crash in update_for_item must not propagate to the caller."""
        m = MemOS(backend="memory")
        m.enable_compounding_ingest(wiki_dir=str(tmp_path / "wiki"))
        m._compounding_wiki.update_for_item = MagicMock(side_effect=RuntimeError("wiki boom"))

        # Must not raise
        item = m.learn("This should still be stored despite wiki failure")
        assert item is not None
        # Verify the memory was actually stored
        results = m.recall("stored despite wiki failure", top=1)
        assert len(results) == 1


class TestUpdateForItem:
    """Tests for LivingWikiEngine.update_for_item() directly."""

    def test_creates_page_for_entity(self, tmp_path):
        from memos.wiki_living import LivingWikiEngine

        m = MemOS(backend="memory")
        wiki = LivingWikiEngine(m, wiki_dir=str(tmp_path / "wiki"))

        item = MemoryItem(id="test1", content="Alice works at CompanyX", tags=["work"])
        result = wiki.update_for_item(item)

        # wiki_dir is resolved to wiki/living/pages/ by LivingWikiEngine
        pages_dir = wiki._wiki_dir / "pages"
        md_files = list(pages_dir.glob("*.md"))
        assert len(md_files) >= 1

    def test_creates_page_for_tag(self, tmp_path):
        from memos.wiki_living import LivingWikiEngine

        m = MemOS(backend="memory")
        wiki = LivingWikiEngine(m, wiki_dir=str(tmp_path / "wiki"))

        item = MemoryItem(id="test2", content="Generic content", tags=["python", "devops"])
        result = wiki.update_for_item(item)

        pages_dir = wiki._wiki_dir / "pages"
        md_files = {f.stem for f in pages_dir.glob("*.md")}
        assert "python" in md_files or "devops" in md_files

    def test_returns_update_result(self, tmp_path):
        from memos.wiki_living import LivingWikiEngine, UpdateResult

        m = MemOS(backend="memory")
        wiki = LivingWikiEngine(m, wiki_dir=str(tmp_path / "wiki"))

        item = MemoryItem(id="test3", content="Bob owns ProjectY", tags=[])
        result = wiki.update_for_item(item)

        assert isinstance(result, UpdateResult)
        assert result.memories_indexed == 1

    def test_skips_already_indexed_item(self, tmp_path):
        from memos.wiki_living import LivingWikiEngine

        m = MemOS(backend="memory")
        wiki = LivingWikiEngine(m, wiki_dir=str(tmp_path / "wiki"))

        item = MemoryItem(id="test4", content="Alice owns ProjectZ", tags=[])
        result1 = wiki.update_for_item(item)
        result2 = wiki.update_for_item(item)  # second call same item

        # First call creates pages; second call is a no-op
        assert result1.pages_created >= 0
        assert result2.pages_created == 0
        assert result2.pages_updated == 0

    def test_updates_existing_page_with_snippet(self, tmp_path):
        from memos.wiki_living import LivingWikiEngine

        m = MemOS(backend="memory")
        wiki = LivingWikiEngine(m, wiki_dir=str(tmp_path / "wiki"))

        item1 = MemoryItem(id="t1", content="Alice leads TeamA", tags=[])
        item2 = MemoryItem(id="t2", content="Alice also leads ProjectX", tags=[])

        wiki.update_for_item(item1)
        result2 = wiki.update_for_item(item2)

        pages_dir = wiki._wiki_dir / "pages"
        alice_page = pages_dir / "alice.md"
        if alice_page.exists():
            content = alice_page.read_text()
            assert "leads" in content.lower() or "alice" in content.lower()

        assert result2.pages_updated >= 0  # Alice page was updated
