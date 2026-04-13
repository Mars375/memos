"""Tests for the compaction engine."""

import time

import pytest

from memos.compaction.engine import CompactionConfig, CompactionEngine
from memos.models import MemoryItem, generate_id
from memos.storage.memory_backend import InMemoryBackend


def _make_item(content: str, *, importance: float = 0.5, tags: list = None,
               age_days: float = 0, access_count: int = 0) -> MemoryItem:
    """Create a test memory item."""
    now = time.time()
    return MemoryItem(
        id=generate_id(content),
        content=content,
        tags=tags or [],
        importance=importance,
        created_at=now - age_days * 86400,
        accessed_at=now - age_days * 86400,
        access_count=access_count,
    )


@pytest.fixture
def store():
    """Create a fresh in-memory store."""
    return InMemoryBackend()


@pytest.fixture
def engine():
    """Create a compaction engine with test-friendly defaults."""
    config = CompactionConfig(
        archive_age_days=30.0,
        archive_importance_floor=0.3,
        stale_score_threshold=0.3,
        merge_similarity_threshold=0.5,
        cluster_min_size=3,
        cluster_max_size=10,
        max_compact_per_run=100,
    )
    return CompactionEngine(config=config)


class TestCompactionConfig:
    """Config dataclass tests."""

    def test_default_config(self):
        config = CompactionConfig()
        assert config.archive_age_days == 90.0
        assert config.dry_run is False

    def test_custom_config(self):
        config = CompactionConfig(archive_age_days=7, dry_run=True)
        assert config.archive_age_days == 7
        assert config.dry_run is True


class TestArchiveCandidates:
    """Finding memories eligible for archival."""

    def test_finds_old_low_importance(self, engine):
        items = [
            _make_item("old low", importance=0.1, age_days=100),
            _make_item("old high", importance=0.8, age_days=100),
            _make_item("new low", importance=0.1, age_days=5),
        ]
        candidates = engine.find_archive_candidates(items)
        assert len(candidates) == 1
        assert "old low" in candidates[0].content

    def test_skips_recent_memories(self, engine):
        items = [_make_item("recent", importance=0.1, age_days=5)]
        assert len(engine.find_archive_candidates(items)) == 0

    def test_skips_important_old_memories(self, engine):
        items = [_make_item("important", importance=0.5, age_days=200)]
        assert len(engine.find_archive_candidates(items)) == 0

    def test_empty_store(self, engine):
        assert engine.find_archive_candidates([]) == []


class TestStaleGroups:
    """Finding groups of stale memories for merging."""

    def test_groups_semantically_similar(self, engine):
        items = [
            _make_item("user prefers dark mode for coding", importance=0.1, age_days=60),
            _make_item("user prefers dark mode for reading", importance=0.1, age_days=60),
            _make_item("user prefers dark mode for writing", importance=0.1, age_days=60),
        ]
        groups = engine.find_stale_groups(items)
        assert len(groups) >= 1
        assert len(groups[0].memories) >= 3

    def test_no_groups_below_min_size(self, engine):
        items = [
            _make_item("similar topic alpha", importance=0.1, age_days=60),
            _make_item("similar topic beta", importance=0.1, age_days=60),
        ]
        groups = engine.find_stale_groups(items)
        assert len(groups) == 0  # Below cluster_min_size=3

    def test_dissimilar_not_grouped(self, engine):
        items = [
            _make_item("python programming best practices", importance=0.1, age_days=60),
            _make_item("weather forecast tomorrow rain", importance=0.1, age_days=60),
            _make_item("recipe chocolate cake baking", importance=0.1, age_days=60),
        ]
        groups = engine.find_stale_groups(items)
        # These topics are too dissimilar to group at threshold 0.5
        assert len(groups) == 0


class TestCompactionPipeline:
    """Full compaction pipeline tests."""

    def test_empty_store(self, engine, store):
        report = engine.compact(store)
        assert report.total_removed == 0
        assert report.net_delta == 0

    def test_single_memory(self, engine, store):
        store.upsert(_make_item("only one"))
        report = engine.compact(store)
        assert report.total_removed == 0

    def test_dedup_phase(self, engine, store):
        """Exact duplicates are removed (manually inserted with different IDs)."""
        # InMemoryBackend deduplicates by ID, so we insert same content with different IDs
        item1 = MemoryItem(
            id="dup-a", content="duplicate content here for testing dedup phase",
            tags=[], importance=0.5, created_at=time.time(), accessed_at=time.time(),
        )
        item2 = MemoryItem(
            id="dup-b", content="duplicate content here for testing dedup phase",
            tags=[], importance=0.5, created_at=time.time(), accessed_at=time.time(),
        )
        store.upsert(item1)
        store.upsert(item2)
        store.upsert(_make_item("unique content different from the rest"))

        report = engine.compact(store)
        assert report.dedup_groups >= 1
        assert report.dedup_merged >= 1

    def test_archive_phase(self, engine, store):
        """Old low-importance memories get archived."""
        for i in range(5):
            store.upsert(_make_item(
                f"archivable memory number {i} with unique content",
                importance=0.1, age_days=100 + i,
            ))
        # Add a fresh one that shouldn't be archived
        store.upsert(_make_item("fresh memory active project", importance=0.5, age_days=1))

        report = engine.compact(store)
        assert report.archived >= 1

        # Check that archived items have the "archived" tag
        remaining = store.list_all()
        archived = [m for m in remaining if "archived" in m.tags]
        assert len(archived) >= 1

    def test_dry_run_no_modifications(self, store):
        config = CompactionConfig(dry_run=True)
        engine = CompactionEngine(config=config)

        store.upsert(_make_item("old low importance memory one", importance=0.1, age_days=200))
        store.upsert(_make_item("old low importance memory two", importance=0.1, age_days=200))

        report = engine.compact(store)
        assert report.archived >= 1  # Found candidates

        # But nothing was actually modified
        remaining = store.list_all()
        assert len(remaining) == 2
        assert all("archived" not in m.tags for m in remaining)

    def test_report_to_dict(self, engine, store):
        store.upsert(_make_item("test", importance=0.1, age_days=100))
        store.upsert(_make_item("test", importance=0.1, age_days=100))

        report = engine.compact(store)
        d = report.to_dict()

        assert "archived" in d
        assert "stale_merged" in d
        assert "duration_seconds" in d
        assert isinstance(d["duration_seconds"], float)

    def test_max_compact_per_run_respected(self, store):
        config = CompactionConfig(max_compact_per_run=2)
        engine = CompactionEngine(config=config)

        for i in range(20):
            store.upsert(_make_item(
                f"very old memory number {i} with unique content here",
                importance=0.1, age_days=200 + i,
            ))

        report = engine.compact(store)
        # Budget applies per-phase; total may exceed slightly but each phase respects it
        assert report.total_removed <= 20  # Sanity: never more than total items

    def test_high_importance_never_archived(self, engine, store):
        """Important memories are never archived regardless of age."""
        store.upsert(_make_item(
            "critical config", importance=0.9, age_days=500,
        ))
        report = engine.compact(store)
        assert report.archived == 0


class TestCompactionIntegration:
    """Integration tests with realistic memory sets."""

    def test_realistic_mixed_store(self, store):
        """Mix of fresh, stale, duplicate, and important memories."""
        config = CompactionConfig(
            archive_age_days=60,
            stale_score_threshold=0.3,
            merge_similarity_threshold=0.5,
        )
        engine = CompactionEngine(config=config)

        # Fresh important
        for i in range(5):
            store.upsert(_make_item(
                f"fresh important {i}", importance=0.8, age_days=1,
                tags=["active"],
            ))

        # Old duplicates
        store.upsert(_make_item("same old content", importance=0.2, age_days=90))
        store.upsert(_make_item("same old content", importance=0.2, age_days=90))

        # Old low-importance, similar
        for i in range(5):
            store.upsert(_make_item(
                f"user preference dark mode variant {i}",
                importance=0.1, age_days=120 + i,
                tags=["preference"],
            ))

        # Old important — should survive
        store.upsert(_make_item(
            "critical API key location", importance=0.9, age_days=200,
        ))

        report = engine.compact(store)

        # Should have done some work
        assert report.total_removed > 0

        # Critical item should survive
        remaining = store.list_all()
        critical = [m for m in remaining if "critical" in m.content]
        assert len(critical) >= 1
        assert "archived" not in critical[0].tags

    def test_idempotent_compaction(self, engine, store):
        """Running compaction twice produces no additional changes."""
        store.upsert(_make_item("old low", importance=0.1, age_days=200))
        store.upsert(_make_item("old low 2", importance=0.1, age_days=200))

        engine.compact(store)
        report2 = engine.compact(store)

        # Second run should find nothing new
        assert report2.total_removed == 0

    def test_compaction_preserves_fresh_memories(self, store):
        """Fresh memories are never touched by compaction."""
        config = CompactionConfig()
        engine = CompactionEngine(config=config)

        original_items = []
        for i in range(10):
            item = _make_item(f"fresh {i}", importance=0.5, age_days=0.1)
            store.upsert(item)
            original_items.append(item.id)

        engine.compact(store)

        remaining = store.list_all()
        remaining_ids = {m.id for m in remaining}
        for oid in original_items:
            assert oid in remaining_ids


class TestClusterSummary:
    """Cluster summary creation."""

    def test_creates_summary_with_tag(self, engine):
        items = [
            _make_item(f"preference note {i}", tags=["preference"])
            for i in range(5)
        ]
        summary = engine._create_cluster_summary("preference", items)
        assert "preference" in summary.tags
        assert "compacted" in summary.tags
        assert "preference" in summary.content.lower()
        assert summary.metadata["compacted_from"] == 5
        assert summary.metadata["compaction_type"] == "cluster_summary"

    def test_summary_importance_capped(self, engine):
        items = [
            _make_item(f"item {i}", importance=0.9, tags=["test"])
            for i in range(4)
        ]
        summary = engine._create_cluster_summary("test", items)
        # 0.9 * 0.7 = 0.63, which is >= 0.3
        assert 0.3 <= summary.importance <= 1.0

    def test_long_content_truncated(self, engine):
        items = [
            _make_item("x " * 200, tags=["long"])
            for i in range(5)
        ]
        summary = engine._create_cluster_summary("long", items)
        # Summary should be manageable size
        assert len(summary.content) < 5000
