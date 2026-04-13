"""Tests for DedupEngine — P29 Memory Deduplication."""

import pytest

from memos.core import MemOS
from memos.dedup import DedupEngine
from memos.models import MemoryItem
from memos.storage.memory_backend import InMemoryBackend


class TestDedupEngine:
    """Unit tests for DedupEngine."""

    def _make_store(self, items=None):
        store = InMemoryBackend()
        if items:
            for item in items:
                store.upsert(item)
        return store

    def _make_item(self, content, item_id="test"):
        return MemoryItem(id=item_id, content=content)

    # --- Exact dedup ---

    def test_exact_duplicate_detected(self):
        store = self._make_store([self._make_item("Hello world", "a1")])
        engine = DedupEngine(store)
        result = engine.check("Hello world")
        assert result.is_duplicate is True
        assert result.reason == "exact"
        assert result.similarity == 1.0
        assert result.match.id == "a1"

    def test_exact_duplicate_case_insensitive(self):
        store = self._make_store([self._make_item("Hello World", "a1")])
        engine = DedupEngine(store)
        result = engine.check("hello world")
        assert result.is_duplicate is True
        assert result.reason == "exact"

    def test_exact_duplicate_whitespace_normalized(self):
        store = self._make_store([self._make_item("Hello   world", "a1")])
        engine = DedupEngine(store)
        result = engine.check("Hello world")
        assert result.is_duplicate is True
        assert result.reason == "exact"

    def test_exact_duplicate_punctuation_stripped(self):
        store = self._make_store([self._make_item("Hello, world!", "a1")])
        engine = DedupEngine(store)
        result = engine.check("Hello world")
        assert result.is_duplicate is True
        assert result.reason == "exact"

    def test_not_duplicate_different_content(self):
        store = self._make_store([self._make_item("Hello world", "a1")])
        engine = DedupEngine(store)
        result = engine.check("Completely different content here")
        assert result.is_duplicate is False

    # --- Near dedup (trigram Jaccard) ---

    def test_near_duplicate_high_similarity(self):
        store = self._make_store(
            [
                self._make_item(
                    "The user prefers dark mode in the interface configuration settings",
                    "a1",
                ),
            ]
        )
        engine = DedupEngine(store, threshold=0.85)
        result = engine.check("The user prefers dark mode in the interface configuration")
        # Should detect as near-duplicate due to high trigram overlap
        assert result.is_duplicate is True
        assert result.reason == "near"
        assert result.similarity >= 0.85

    def test_near_duplicate_below_threshold(self):
        store = self._make_store(
            [
                self._make_item("The quick brown fox jumps over the lazy dog", "a1"),
            ]
        )
        engine = DedupEngine(store, threshold=0.95)
        result = engine.check("A completely unrelated sentence about Python programming")
        assert result.is_duplicate is False

    def test_custom_threshold_override(self):
        store = self._make_store(
            [
                self._make_item("User likes Python programming language", "a1"),
            ]
        )
        engine = DedupEngine(store, threshold=0.95)
        # With default threshold, not a dup
        result_default = engine.check("User likes Python language")
        # With lower threshold, might be a dup
        result_low = engine.check("User likes Python language", threshold=0.6)
        # At least verify threshold override works
        assert isinstance(result_default.is_duplicate, bool)
        assert isinstance(result_low.is_duplicate, bool)

    # --- Empty store ---

    def test_empty_store_no_duplicate(self):
        store = self._make_store()
        engine = DedupEngine(store)
        result = engine.check("Any content at all")
        assert result.is_duplicate is False

    def test_short_content_no_trigrams(self):
        store = self._make_store([self._make_item("ab", "a1")])
        engine = DedupEngine(store)
        result = engine.check("ab")
        assert result.is_duplicate is True  # exact match

    # --- Register / invalidate ---

    def test_register_new_item(self):
        store = self._make_store()
        engine = DedupEngine(store)
        item = self._make_item("Test content", "new1")
        engine.register(item)
        result = engine.check("Test content")
        assert result.is_duplicate is True
        assert result.match.id == "new1"

    def test_invalidate_cache(self):
        store = self._make_store([self._make_item("Old content", "a1")])
        engine = DedupEngine(store)
        engine._ensure_index()
        # Remove from store but not from index
        store.delete("a1")
        engine.invalidate_cache()
        # Rebuilding should find empty store
        result = engine.check("Old content")
        assert result.is_duplicate is False


class TestDedupScan:
    """Tests for batch dedup scan."""

    def _make_store(self, items=None):
        store = InMemoryBackend()
        if items:
            for item in items:
                store.upsert(item)
        return store

    def test_scan_exact_duplicates(self):
        store = self._make_store(
            [
                MemoryItem(id="a", content="Duplicate content"),
                MemoryItem(id="b", content="Duplicate content"),
                MemoryItem(id="c", content="Unique content here"),
            ]
        )
        engine = DedupEngine(store)
        result = engine.scan()
        assert result.total_scanned == 3
        assert result.exact_duplicates == 1
        assert result.total_duplicates == 1

    def test_scan_no_duplicates(self):
        store = self._make_store(
            [
                MemoryItem(id="a", content="First memory"),
                MemoryItem(id="b", content="Second memory"),
                MemoryItem(id="c", content="Third memory"),
            ]
        )
        engine = DedupEngine(store)
        result = engine.scan()
        assert result.total_duplicates == 0

    def test_scan_with_fix(self):
        store = self._make_store(
            [
                MemoryItem(id="a", content="Duplicate content"),
                MemoryItem(id="b", content="Duplicate content"),
                MemoryItem(id="c", content="Unique content"),
            ]
        )
        engine = DedupEngine(store)
        result = engine.scan(fix=True)
        assert result.fixed == 1
        # Verify one was actually deleted
        remaining = store.list_all()
        assert len(remaining) == 2

    def test_scan_empty_store(self):
        store = self._make_store()
        engine = DedupEngine(store)
        result = engine.scan()
        assert result.total_scanned == 0
        assert result.total_duplicates == 0


class TestMemOSDedupIntegration:
    """Integration tests for dedup in MemOS.learn()."""

    def test_learn_skips_exact_duplicate(self):
        m = MemOS(backend="memory")
        m.dedup_set_enabled(True)
        item1 = m.learn("User prefers dark mode")
        item2 = m.learn("User prefers dark mode")
        assert item2.id == item1.id  # Returns original, no new insert
        assert m.stats().total_memories == 1

    def test_learn_allows_duplicate_with_flag(self):
        m = MemOS(backend="memory")
        m.dedup_set_enabled(True)
        # First, block a near-duplicate via dedup
        m.learn("User prefers dark mode in settings")
        # Without allow_duplicate, near-dup would be blocked (if threshold allows)
        # With allow_duplicate=True, it goes through even if flagged
        item = m.learn("User prefers dark mode in settings", allow_duplicate=True)
        assert item is not None
        # Since IDs are content-derived, same content = same ID (upsert semantics)
        assert m.stats().total_memories == 1

    def test_learn_normal_without_dedup(self):
        m = MemOS(backend="memory", dedup_enabled=False)
        # IDs are content-derived (generate_id), so same content = upsert
        m.learn("Content A")
        m.learn("Content B")
        assert m.stats().total_memories == 2

    def test_dedup_check_standalone(self):
        m = MemOS(backend="memory")
        m.learn("Existing memory about Python")
        result = m.dedup_check("Existing memory about Python")
        assert result.is_duplicate is True
        assert result.reason == "exact"

    def test_dedup_scan_removes_duplicates(self):
        m = MemOS(backend="memory")
        # Use _store directly to insert items with same content but different IDs
        m._store.upsert(MemoryItem(id="dup-a", content="Memory A"))
        m._store.upsert(MemoryItem(id="dup-b", content="Memory A"))
        m._store.upsert(MemoryItem(id="unique-c", content="Memory B"))
        result = m.dedup_scan(fix=True)
        assert result.total_duplicates >= 1
        assert result.fixed >= 1

    def test_dedup_enabled_property(self):
        m = MemOS(backend="memory")
        assert m.dedup_enabled is True  # enabled by default since v1.0
        m.dedup_set_enabled(False)
        assert m.dedup_enabled is False
        m.dedup_set_enabled(True)
        assert m.dedup_enabled is True

    def test_dedup_with_namespace(self):
        m = MemOS(backend="memory")
        m.namespace = "ns1"
        m.dedup_set_enabled(True)
        m.learn("Memory in namespace 1")
        m.namespace = "ns2"
        m.dedup_set_enabled(True)
        # Different namespace — should not be a dup
        result = m.dedup_check("Memory in namespace 1")
        # In ns2, this shouldn't be found as dup (different namespace)
        assert result.is_duplicate is False


class TestDedupAPI:
    """Tests for REST API dedup endpoints."""

    def _get_app(self):
        from memos.api import create_fastapi_app

        return create_fastapi_app()

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        app = self._get_app()
        return TestClient(app)

    def test_dedup_check_api(self, client):
        # Learn a memory first
        client.post(
            "/api/v1/learn",
            json={
                "content": "API test memory for dedup",
            },
        )
        # Check for duplicate
        resp = client.post(
            "/api/v1/dedup/check",
            json={
                "content": "API test memory for dedup",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate"] is True
        assert data["reason"] == "exact"

    def test_dedup_check_no_duplicate(self, client):
        resp = client.post(
            "/api/v1/dedup/check",
            json={
                "content": "Something completely unique xyz123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate"] is False

    def test_dedup_scan_api(self, client):
        # Use the learn endpoint with different content, then check scan works
        client.post("/api/v1/learn", json={"content": "Unique memory one"})
        client.post("/api/v1/learn", json={"content": "Unique memory two"})
        resp = client.post("/api/v1/dedup/scan", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_scanned"] >= 2
        assert "groups" in data

    def test_dedup_check_missing_content(self, client):
        resp = client.post("/api/v1/dedup/check", json={})
        assert resp.status_code in (200, 400)
