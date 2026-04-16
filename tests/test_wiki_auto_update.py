"""Tests for auto-update wiki pages on every learn/ingest (Task 3.1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memos.core import MemOS
from memos.wiki_living import LivingWikiEngine


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def mem():
    """MemOS instance with in-memory backend."""
    return MemOS(backend="memory")


@pytest.fixture
def mem_with_wiki(mem, tmp_path):
    """MemOS instance with living wiki auto-update enabled."""
    mem.enable_compounding_ingest(wiki_dir=str(tmp_path / "wiki"))
    return mem


# ── Test: learn() triggers wiki update when auto_update is enabled ──


def test_learn_triggers_wiki_update_when_enabled(mem_with_wiki):
    """When wiki_auto_update is True, learn() should call update_for_item."""
    wiki = mem_with_wiki._living_wiki
    assert wiki is not None

    # Spy on update_for_item
    original = wiki.update_for_item
    called = {"count": 0, "item_id": None}

    def spy(item):
        called["count"] += 1
        called["item_id"] = item.id
        return original(item)

    wiki.update_for_item = spy

    item = mem_with_wiki.learn("Alice works on Project Phoenix")
    assert called["count"] == 1
    assert called["item_id"] == item.id


def test_learn_updates_wiki_pages(mem_with_wiki):
    """learn() should create entity pages in the wiki."""
    mem_with_wiki.learn("Alice works on Project Phoenix", tags=["project"])

    wiki = mem_with_wiki._living_wiki
    wiki_dir = Path(wiki._wiki_dir)

    # Check that entity pages were created
    pages_dir = wiki_dir / "pages"
    assert pages_dir.exists()

    # At least some entity pages should exist
    page_files = list(pages_dir.glob("*.md"))
    assert len(page_files) > 0


def test_learn_creates_entity_pages_for_new_entities(mem_with_wiki):
    """Wiki pages should be created for entities found in the memory content."""
    mem_with_wiki.learn("Alice Smith is working on Project Neptune", tags=["space"])

    wiki = mem_with_wiki._living_wiki
    pages_dir = Path(wiki._wiki_dir) / "pages"

    # Should have created pages for extracted entities and tags
    page_slugs = [p.stem for p in pages_dir.glob("*.md")]
    # At minimum the tag "space" should be a topic page
    assert "space" in page_slugs


# ── Test: disabling auto_update skips wiki update ──


def test_disabling_auto_update_skips_wiki(mem_with_wiki):
    """When wiki_auto_update is disabled, learn() should NOT update wiki."""
    wiki = mem_with_wiki._living_wiki

    # Disable auto-update
    mem_with_wiki.wiki_auto_update = False
    assert not mem_with_wiki.wiki_auto_update

    # Spy on update_for_item
    called = {"count": 0}

    def spy(item):
        called["count"] += 1

    wiki.update_for_item = spy

    mem_with_wiki.learn("This should not trigger wiki update")
    assert called["count"] == 0


def test_disable_compounding_ingest_skips_wiki(mem_with_wiki):
    """disable_compounding_ingest() should stop wiki auto-updates."""
    wiki = mem_with_wiki._living_wiki

    # Spy on update_for_item
    called = {"count": 0}

    def spy(item):
        called["count"] += 1

    wiki.update_for_item = spy

    # Disable
    mem_with_wiki.disable_compounding_ingest()

    assert mem_with_wiki._living_wiki is None
    assert not mem_with_wiki.wiki_auto_update

    mem_with_wiki.learn("No wiki update expected")
    assert called["count"] == 0


# ── Test: wiki update failure doesn't break learn() ──


def test_wiki_update_failure_does_not_break_learn(mem_with_wiki):
    """If wiki update raises, learn() should still return the item."""
    wiki = mem_with_wiki._living_wiki

    # Make update_for_item raise an exception
    wiki.update_for_item = MagicMock(side_effect=RuntimeError("Wiki DB corrupted"))

    # learn() should not raise
    item = mem_with_wiki.learn("This memory should still be saved")
    assert item is not None
    assert item.content == "This memory should still be saved"

    # Verify the memory was actually stored
    results = mem_with_wiki.recall("memory should still be saved")
    assert len(results) >= 1


def test_wiki_update_failure_with_various_exceptions(mem_with_wiki):
    """learn() is resilient to any exception type from wiki update."""
    wiki = mem_with_wiki._living_wiki

    for exc_cls in [ValueError, OSError, KeyError, AttributeError]:
        wiki.update_for_item = MagicMock(side_effect=exc_cls("boom"))
        item = mem_with_wiki.learn(f"Resilient memory {exc_cls.__name__}")
        assert item is not None


# ── Test: no wiki when not initialized ──


def test_no_wiki_update_when_not_initialized(mem):
    """By default, learn() should not attempt any wiki update."""
    assert mem._living_wiki is None
    assert not mem.wiki_auto_update

    # Should work fine without any wiki
    item = mem.learn("Just a normal memory")
    assert item is not None


# ── Test: wiki pages accumulate across multiple learn() calls ──


def test_wiki_pages_accumulate_across_learns(mem_with_wiki):
    """Multiple learn() calls should accumulate entities across pages."""
    mem_with_wiki.learn("Alice works on Alpha", tags=["team"])
    mem_with_wiki.learn("Bob works on Beta", tags=["team"])

    wiki = mem_with_wiki._living_wiki
    pages_dir = Path(wiki._wiki_dir) / "pages"
    page_slugs = [p.stem for p in pages_dir.glob("*.md")]

    # Both "team" tag should be there, plus entities from both memories
    assert "team" in page_slugs
    assert len(page_slugs) >= 2


# ── Test: re-enabling auto_update works ──


def test_reenable_auto_update(mem_with_wiki):
    """Toggling wiki_auto_update off then on should resume updates."""
    wiki = mem_with_wiki._living_wiki

    # Disable
    mem_with_wiki.wiki_auto_update = False

    called = {"count": 0}

    def spy(item):
        called["count"] += 1

    wiki.update_for_item = spy

    mem_with_wiki.learn("No update")
    assert called["count"] == 0

    # Re-enable
    mem_with_wiki.wiki_auto_update = True
    mem_with_wiki.learn("Now update")
    assert called["count"] == 1
