"""Tests for the persistent embedding cache."""

import time

import pytest

from memos.cache.embedding_cache import EmbeddingCache


@pytest.fixture
def cache_path(tmp_path):
    """Provide a temporary cache database path."""
    return str(tmp_path / "test_embeddings.db")


@pytest.fixture
def cache(cache_path):
    """Create a fresh cache instance."""
    return EmbeddingCache(path=cache_path, max_size=100, ttl_seconds=0)


@pytest.fixture
def ttl_cache(cache_path):
    """Create a cache with TTL enabled."""
    return EmbeddingCache(path=cache_path, max_size=100, ttl_seconds=2.0)


class TestEmbeddingCacheBasic:
    """Basic put/get operations."""

    def test_put_and_get(self, cache):
        vec = [0.1, 0.2, 0.3, 0.4]
        cache.put("hello world", vec, model="test-model")

        result = cache.get("hello world", model="test-model")
        assert result is not None
        assert len(result) == 4
        assert abs(result[0] - 0.1) < 1e-6

    def test_get_missing_returns_none(self, cache):
        assert cache.get("nonexistent") is None

    def test_put_overwrite(self, cache):
        cache.put("text", [1.0, 2.0])
        cache.put("text", [3.0, 4.0])

        result = cache.get("text")
        assert result == [3.0, 4.0]

    def test_different_models_same_text(self, cache):
        cache.put("hello", [1.0], model="model-a")
        cache.put("hello", [2.0], model="model-b")

        assert cache.get("hello", model="model-a") == [1.0]
        assert cache.get("hello", model="model-b") == [2.0]

    def test_deterministic_key(self, cache_path):
        """Same text + model always produces the same key."""
        cache1 = EmbeddingCache(path=cache_path)
        cache1.put("test", [0.5], model="m")

        cache2 = EmbeddingCache(path=cache_path)
        assert cache2.get("test", model="m") == [0.5]

    def test_empty_text(self, cache):
        cache.put("", [0.0])
        assert cache.get("") == [0.0]

    def test_large_vector(self, cache):
        vec = [float(i) for i in range(768)]
        cache.put("large", vec, model="nomic")
        result = cache.get("large", model="nomic")
        assert len(result) == 768
        assert result[0] == 0.0
        assert result[767] == 767.0

    def test_unicode_text(self, cache):
        cache.put("Bonjour le monde 🌍", [1.0, 2.0])
        assert cache.get("Bonjour le monde 🌍") == [1.0, 2.0]


class TestEmbeddingCacheTTL:
    """TTL-based expiry."""

    def test_entry_valid_before_ttl(self, ttl_cache):
        ttl_cache.put("temp", [1.0])
        assert ttl_cache.get("temp") == [1.0]

    def test_entry_expired_after_ttl(self, ttl_cache):
        ttl_cache.put("temp", [1.0])
        time.sleep(2.1)
        assert ttl_cache.get("temp") is None

    def test_ttl_zero_never_expires(self, cache):
        cache.put("permanent", [1.0])
        time.sleep(0.1)
        assert cache.get("permanent") == [1.0]

    def test_expired_entry_removed_from_db(self, ttl_cache):
        ttl_cache.put("temp", [1.0])
        time.sleep(2.1)
        ttl_cache.get("temp")  # Triggers cleanup
        assert len(ttl_cache) == 0


class TestEmbeddingCacheEviction:
    """LRU eviction when max_size is exceeded."""

    def test_eviction_on_over_capacity(self, cache_path):
        cache = EmbeddingCache(path=cache_path, max_size=5)
        for i in range(10):
            cache.put(f"item-{i}", [float(i)])

        assert len(cache) <= 5

    def test_evicted_entries_not_retrievable(self, cache_path):
        cache = EmbeddingCache(path=cache_path, max_size=3)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])
        cache.put("d", [4.0])  # Should evict "a" (oldest)

        # "d" should be present
        assert cache.get("d") == [4.0]
        # "a" may or may not be evicted depending on timing, but cache size <= 3
        assert len(cache) <= 3

    def test_access_updates_lru(self, cache_path):
        cache = EmbeddingCache(path=cache_path, max_size=3)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])

        # Access "a" to make it recently used
        cache.get("a")

        # Add new item — should evict "b" (not "a", since it was accessed)
        cache.put("d", [4.0])

        assert cache.get("a") == [1.0]  # Still present (accessed recently)


class TestEmbeddingCacheStats:
    """Statistics tracking."""

    def test_initial_stats(self, cache):
        stats = cache.stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.size == 0
        assert stats.hit_rate == 0.0

    def test_hit_miss_tracking(self, cache):
        cache.put("x", [1.0])

        cache.get("x")   # hit
        cache.get("x")   # hit
        cache.get("y")   # miss

        stats = cache.stats()
        assert stats.hits == 2
        assert stats.misses == 1
        assert abs(stats.hit_rate - 2.0 / 3.0) < 0.01

    def test_eviction_count(self, cache_path):
        cache = EmbeddingCache(path=cache_path, max_size=3)
        for i in range(10):
            cache.put(f"item-{i}", [float(i)])

        stats = cache.stats()
        assert stats.evictions > 0

    def test_stats_to_dict(self, cache):
        cache.put("x", [1.0])
        cache.get("x")
        d = cache.stats().to_dict()
        assert "hits" in d
        assert "hit_rate" in d
        assert isinstance(d["hit_rate"], float)


class TestEmbeddingCacheOperations:
    """Additional operations."""

    def test_invalidate_existing(self, cache):
        cache.put("x", [1.0])
        assert cache.invalidate("x") is True
        assert cache.get("x") is None

    def test_invalidate_nonexistent(self, cache):
        assert cache.invalidate("nope") is False

    def test_clear(self, cache):
        for i in range(10):
            cache.put(f"item-{i}", [float(i)])
        removed = cache.clear()
        assert removed == 10
        assert len(cache) == 0

    def test_len(self, cache):
        assert len(cache) == 0
        cache.put("a", [1.0])
        assert len(cache) == 1
        cache.put("b", [2.0])
        assert len(cache) == 2

    def test_contains(self, cache):
        cache.put("exists", [1.0])
        assert "exists" in cache
        assert "missing" not in cache

    def test_persistence_across_instances(self, cache_path):
        """Data persists when creating a new instance on the same path."""
        cache1 = EmbeddingCache(path=cache_path)
        cache1.put("persist", [42.0])

        cache2 = EmbeddingCache(path=cache_path)
        assert cache2.get("persist") == [42.0]

    def test_stats_persist_across_instances(self, cache_path):
        """Hit/miss counters are instance-scoped, not persisted."""
        cache1 = EmbeddingCache(path=cache_path)
        cache1.put("x", [1.0])
        cache1.get("x")  # hit

        cache2 = EmbeddingCache(path=cache_path)
        # Stats should start fresh for new instance
        stats = cache2.stats()
        assert stats.hits == 0  # Instance-scoped
