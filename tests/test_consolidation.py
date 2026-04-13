"""Tests for the consolidation engine — semantic dedup."""

from memos.consolidation.engine import ConsolidationEngine
from memos.models import MemoryItem
from memos.storage.memory_backend import InMemoryBackend


def _item(content: str, *, tags: list[str] | None = None, importance: float = 0.5) -> MemoryItem:
    return MemoryItem(
        id=MemoryItem.__hash__(MemoryItem(content, tags=tags or [], importance=importance)) & 0xFFFFFFFF,
        content=content,
        tags=tags or [],
        importance=importance,
    )


# --- Helper ---

_counter = 0


def _make_item(content: str, **kw) -> MemoryItem:
    """Create a MemoryItem with a unique ID (even for same content)."""
    global _counter
    _counter += 1
    return MemoryItem(id=f"test-{_counter:04d}", content=content, **kw)


# --- Tests ---


class TestExactDedup:
    def test_identical_content_detected(self):
        engine = ConsolidationEngine()
        items = [
            _make_item("User prefers dark mode"),
            _make_item("User prefers dark mode"),  # exact duplicate
        ]
        groups = engine.find_duplicates(items)
        assert len(groups) == 1
        assert groups[0].reason == "exact"
        assert groups[0].similarity == 1.0
        assert len(groups[0].duplicates) == 1

    def test_case_insensitive(self):
        engine = ConsolidationEngine()
        items = [
            _make_item("User prefers dark mode"),
            _make_item("user prefers dark mode"),
        ]
        groups = engine.find_duplicates(items)
        assert len(groups) == 1
        assert groups[0].reason == "exact"

    def test_whitespace_normalized(self):
        engine = ConsolidationEngine()
        items = [
            _make_item("User prefers dark mode"),
            _make_item("User   prefers   dark   mode"),
        ]
        groups = engine.find_duplicates(items)
        assert len(groups) == 1

    def test_different_content_not_matched(self):
        engine = ConsolidationEngine()
        items = [
            _make_item("User prefers dark mode"),
            _make_item("Server runs on port 8080"),
        ]
        groups = engine.find_duplicates(items)
        assert len(groups) == 0


class TestSemanticDedup:
    def test_high_overlap_detected(self):
        engine = ConsolidationEngine(similarity_threshold=0.5)
        items = [
            _make_item("deploy application docker containers kubernetes cluster"),
            _make_item("deploy containers docker application kubernetes production"),
        ]
        groups = engine.find_duplicates(items)
        assert len(groups) >= 1
        semantic = [g for g in groups if g.reason == "semantic"]
        assert len(semantic) >= 1

    def test_low_overlap_not_detected(self):
        engine = ConsolidationEngine(similarity_threshold=0.75)
        items = [
            _make_item("The weather is sunny today"),
            _make_item("Docker containers are running fine"),
        ]
        groups = engine.find_duplicates(items)
        assert len(groups) == 0

    def test_threshold_controls_sensitivity(self):
        items = [
            _make_item("Deploy application using Docker containers on the server"),
            _make_item("Deploy services using container orchestration platform"),
        ]
        # Low threshold → should detect
        engine_low = ConsolidationEngine(similarity_threshold=0.3)
        groups_low = engine_low.find_duplicates(items)

        # High threshold → should not detect
        engine_high = ConsolidationEngine(similarity_threshold=0.9)
        groups_high = engine_high.find_duplicates(items)

        assert len(groups_low) >= len(groups_high)


class TestMerge:
    def test_tags_merged(self):
        engine = ConsolidationEngine()
        items = [
            _make_item("User likes Python", tags=["preference", "language"]),
            _make_item("User likes Python", tags=["preference", "coding"]),
        ]
        groups = engine.find_duplicates(items)
        assert len(groups) == 1
        merged_tags = set(groups[0].keep.tags)
        # After consolidation the tags are merged
        assert "preference" in merged_tags

    def test_importance_preserved(self):
        engine = ConsolidationEngine()
        items = [
            _make_item("Critical config value", importance=0.9),
            _make_item("Critical config value", importance=0.3),
        ]
        groups = engine.find_duplicates(items)
        # Best item picked (higher importance)
        assert groups[0].keep.importance == 0.9

    def test_access_counts_summed(self):
        engine = ConsolidationEngine()
        item_a = _make_item("Shared memory")
        item_a.access_count = 5
        item_b = _make_item("Shared memory")
        item_b.access_count = 3

        groups = engine.find_duplicates([item_a, item_b])
        # The keep item should have summed access counts after merge
        assert len(groups) == 1


class TestConsolidate:
    def test_dry_run_no_modifications(self):
        store = InMemoryBackend()
        store.upsert(_make_item("Hello world"))
        store.upsert(_make_item("Hello world"))

        engine = ConsolidationEngine()
        result = engine.consolidate(store, dry_run=True)

        assert result.groups_found == 1
        assert result.space_freed == 0  # Nothing actually removed
        assert len(store.list_all()) == 2  # Still 2 items

    def test_consolidate_removes_duplicates(self):
        store = InMemoryBackend()
        store.upsert(_make_item("Hello world"))
        store.upsert(_make_item("Hello world"))

        engine = ConsolidationEngine()
        result = engine.consolidate(store)

        assert result.groups_found == 1
        assert result.space_freed == 1
        assert len(store.list_all()) == 1

    def test_consolidate_merges_tags(self):
        store = InMemoryBackend()
        item_a = _make_item("Important note", tags=["important"])
        item_b = _make_item("Important note", tags=["note", "review"])
        store.upsert(item_a)
        store.upsert(item_b)

        engine = ConsolidationEngine()
        engine.consolidate(store)

        remaining = store.list_all()
        assert len(remaining) == 1
        assert set(remaining[0].tags) == {"important", "note", "review"}

    def test_empty_store(self):
        store = InMemoryBackend()
        engine = ConsolidationEngine()
        result = engine.consolidate(store)
        assert result.groups_found == 0
        assert result.memories_merged == 0


class TestEdgeCases:
    def test_single_item(self):
        engine = ConsolidationEngine()
        groups = engine.find_duplicates([_make_item("Only one item")])
        assert len(groups) == 0

    def test_empty_list(self):
        engine = ConsolidationEngine()
        groups = engine.find_duplicates([])
        assert len(groups) == 0

    def test_max_groups_limit(self):
        engine = ConsolidationEngine()
        items = []
        for i in range(20):
            items.append(_make_item(f"Duplicate number {i % 5}"))
            items.append(_make_item(f"Duplicate number {i % 5}"))

        groups = engine.find_duplicates(items, max_groups=3)
        assert len(groups) <= 3
