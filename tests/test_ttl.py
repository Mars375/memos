"""Tests for TTL (time-to-live) memory expiry."""

import time
import pytest
from memos.models import MemoryItem, parse_ttl
from memos.core import MemOS


class TestParseTTL:
    """Test human-readable TTL parsing."""

    def test_seconds(self):
        assert parse_ttl("30s") == 30

    def test_minutes(self):
        assert parse_ttl("5m") == 300

    def test_hours(self):
        assert parse_ttl("2h") == 7200

    def test_days(self):
        assert parse_ttl("7d") == 604800

    def test_weeks(self):
        assert parse_ttl("1w") == 604800

    def test_plain_number(self):
        assert parse_ttl("3600") == 3600.0

    def test_float_hours(self):
        assert parse_ttl("1.5h") == 5400

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid TTL format"):
            parse_ttl("abc")

    def test_invalid_unit(self):
        with pytest.raises(ValueError, match="Invalid TTL format"):
            parse_ttl("5x")

    def test_negative_ttl(self):
        with pytest.raises(ValueError, match="TTL must be positive"):
            parse_ttl("-1h")

    def test_empty_ttl(self):
        with pytest.raises(ValueError, match="TTL cannot be empty"):
            parse_ttl("")


class TestMemoryItemTTL:
    """Test TTL properties on MemoryItem."""

    def test_no_ttl(self):
        item = MemoryItem(id="test", content="hello", ttl=None)
        assert item.ttl is None
        assert item.expires_at is None
        assert item.is_expired is False

    def test_zero_ttl(self):
        item = MemoryItem(id="test", content="hello", ttl=0)
        assert item.expires_at is None
        assert item.is_expired is False

    def test_future_ttl(self):
        item = MemoryItem(id="test", content="hello", ttl=3600)
        assert item.expires_at is not None
        assert item.expires_at > time.time()
        assert item.is_expired is False

    def test_expired_ttl(self):
        past = time.time() - 7200
        item = MemoryItem(id="test", content="hello", ttl=3600, created_at=past)
        assert item.is_expired is True

    def test_not_expired_yet(self):
        past = time.time() - 30
        item = MemoryItem(id="test", content="hello", ttl=3600, created_at=past)
        assert item.is_expired is False


class TestLearnWithTTL:
    """Test learn() with TTL parameter."""

    def test_learn_with_ttl(self):
        mem = MemOS(backend="memory")
        item = mem.learn("short-lived fact", tags=["temp"], ttl=300)
        assert item.ttl == 300
        assert item.is_expired is False

    def test_learn_without_ttl(self):
        mem = MemOS(backend="memory")
        item = mem.learn("permanent fact", tags=["perm"])
        assert item.ttl is None
        assert item.is_expired is False

    def test_learn_ttl_persists_in_recall(self):
        mem = MemOS(backend="memory")
        mem.learn("temp memory with ttl", ttl=3600)
        results = mem.recall("temp memory")
        assert len(results) > 0
        assert results[0].item.ttl == 3600


class TestRecallExpiryFilter:
    """Test that recall filters out expired memories."""

    def test_expired_memory_not_recalled(self):
        mem = MemOS(backend="memory")
        past = time.time() - 7200
        item = MemoryItem(
            id="expired1",
            content="expired context data",
            tags=["temp"],
            ttl=3600,
            created_at=past,
        )
        mem._store.upsert(item)
        mem._retrieval.index(item)

        results = mem.recall("expired context")
        assert len(results) == 0

    def test_valid_memory_recalled(self):
        mem = MemOS(backend="memory")
        mem.learn("active context data", tags=["temp"], ttl=3600)

        results = mem.recall("active context")
        assert len(results) > 0

    def test_mixed_expired_and_valid(self):
        mem = MemOS(backend="memory")

        mem.learn("current info", tags=["active"], ttl=3600)

        past = time.time() - 7200
        expired = MemoryItem(
            id="exp_old",
            content="old info expired",
            tags=["active"],
            ttl=3600,
            created_at=past,
        )
        mem._store.upsert(expired)
        mem._retrieval.index(expired)

        results = mem.recall("info")
        assert all(not r.item.is_expired for r in results)
        assert len(results) >= 1


class TestPruneExpired:
    """Test prune_expired() method."""

    def test_prune_expired_removes_expired(self):
        mem = MemOS(backend="memory")

        past = time.time() - 7200
        expired = MemoryItem(
            id="exp_prune",
            content="should be pruned",
            ttl=3600,
            created_at=past,
        )
        mem._store.upsert(expired)

        result = mem.prune_expired()
        assert len(result) == 1
        assert result[0].id == "exp_prune"

    def test_prune_expired_keeps_valid(self):
        mem = MemOS(backend="memory")
        mem.learn("keep me", ttl=3600)

        result = mem.prune_expired()
        assert len(result) == 0

    def test_prune_expired_dry_run(self):
        mem = MemOS(backend="memory")

        past = time.time() - 7200
        expired = MemoryItem(
            id="exp_dry",
            content="dry run test",
            ttl=3600,
            created_at=past,
        )
        mem._store.upsert(expired)

        result = mem.prune_expired(dry_run=True)
        assert len(result) == 1

        remaining = mem._store.list_all()
        assert any(i.id == "exp_dry" for i in remaining)

    def test_prune_expired_emits_event(self):
        mem = MemOS(backend="memory")

        past = time.time() - 7200
        expired = MemoryItem(
            id="exp_event",
            content="event test",
            ttl=3600,
            created_at=past,
        )
        mem._store.upsert(expired)

        mem.prune_expired()

        # Check event bus history (sync callbacks need event loop)
        history = mem.events.get_history(limit=100)
        expired_events = [e for e in history if e.type == "expired_pruned"]
        assert len(expired_events) == 1
        assert expired_events[0].data["count"] == 1


class TestStatsWithExpiry:
    """Test that stats includes expired count."""

    def test_stats_shows_expired_count(self):
        mem = MemOS(backend="memory")

        past = time.time() - 7200
        expired = MemoryItem(
            id="exp_stats",
            content="expired for stats",
            ttl=3600,
            created_at=past,
        )
        mem._store.upsert(expired)
        mem.learn("valid memory")

        stats = mem.stats()
        assert stats.expired_memories == 1

    def test_stats_no_expired(self):
        mem = MemOS(backend="memory")
        mem.learn("just a memory")

        stats = mem.stats()
        assert stats.expired_memories == 0


class TestLearnEventTTL:
    """Test that learn event includes TTL info via event bus history."""

    def test_learn_event_contains_ttl(self):
        mem = MemOS(backend="memory")
        mem.learn("ttl event test", ttl=1800)

        history = mem.events.get_history(limit=100)
        learned_events = [e for e in history if e.type == "learned"]
        assert len(learned_events) >= 1
        last = learned_events[-1]
        assert last.data["ttl"] == 1800

    def test_learn_event_no_ttl(self):
        mem = MemOS(backend="memory")
        mem.learn("no ttl event test")

        history = mem.events.get_history(limit=100)
        learned_events = [e for e in history if e.type == "learned"]
        assert len(learned_events) >= 1
        last = learned_events[-1]
        assert last.data["ttl"] is None
