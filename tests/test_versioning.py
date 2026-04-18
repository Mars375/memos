"""Tests for memory versioning and time-travel."""

from __future__ import annotations

import time

import pytest

from src.memos.core import MemOS
from src.memos.models import MemoryItem, generate_id
from src.memos.versioning.engine import VersioningEngine
from src.memos.versioning.models import MemoryVersion, VersionDiff
from src.memos.versioning.store import VersionStore

# ── MemoryVersion model tests ────────────────────────────────


class TestMemoryVersion:
    def test_from_item(self):
        item = MemoryItem(
            id="abc123",
            content="hello world",
            tags=["greeting"],
            importance=0.8,
            metadata={"source": "test"},
        )
        version = MemoryVersion.from_item(item, version_number=1, source="learn")

        assert version.version_id == "abc123#1"
        assert version.item_id == "abc123"
        assert version.version_number == 1
        assert version.content == "hello world"
        assert version.tags == ["greeting"]
        assert version.importance == 0.8
        assert version.metadata == {"source": "test"}
        assert version.source == "learn"

    def test_to_memory_item(self):
        version = MemoryVersion(
            version_id="xyz#3",
            item_id="xyz",
            version_number=3,
            content="version 3 content",
            tags=["tag1", "tag2"],
            importance=0.6,
            metadata={"key": "val"},
            created_at=1000.0,
        )
        item = version.to_memory_item()

        assert item.id == "xyz"
        assert item.content == "version 3 content"
        assert item.tags == ["tag1", "tag2"]
        assert item.importance == 0.6
        assert item.metadata == {"key": "val"}
        # Tags and metadata should be copies, not references
        item.tags.append("tag3")
        assert "tag3" not in version.tags

    def test_to_dict_from_dict_roundtrip(self):
        version = MemoryVersion(
            version_id="test#2",
            item_id="test",
            version_number=2,
            content="roundtrip",
            tags=["rt"],
            importance=0.5,
            metadata={},
            created_at=1234567890.0,
            source="upsert",
        )
        d = version.to_dict()
        restored = MemoryVersion.from_dict(d)

        assert restored.version_id == version.version_id
        assert restored.content == version.content
        assert restored.tags == version.tags
        assert restored.importance == version.importance
        assert restored.created_at == version.created_at


class TestVersionDiff:
    def test_diff_identical_versions(self):
        v1 = MemoryVersion(
            version_id="a#1",
            item_id="a",
            version_number=1,
            content="same",
            tags=["t1"],
            importance=0.5,
            metadata={"k": "v"},
            created_at=100.0,
        )
        v2 = MemoryVersion(
            version_id="a#2",
            item_id="a",
            version_number=2,
            content="same",
            tags=["t1"],
            importance=0.5,
            metadata={"k": "v"},
            created_at=200.0,
        )
        diff = VersionDiff.between(v1, v2)
        assert diff.item_id == "a"
        assert diff.from_version == 1
        assert diff.to_version == 2
        assert diff.changes == {}
        assert diff.delta_seconds == 100.0

    def test_diff_content_change(self):
        v1 = MemoryVersion(
            version_id="a#1",
            item_id="a",
            version_number=1,
            content="old content",
            tags=[],
            importance=0.5,
            metadata={},
            created_at=100.0,
        )
        v2 = MemoryVersion(
            version_id="a#2",
            item_id="a",
            version_number=2,
            content="new content",
            tags=[],
            importance=0.5,
            metadata={},
            created_at=200.0,
        )
        diff = VersionDiff.between(v1, v2)
        assert "content" in diff.changes
        assert diff.changes["content"]["from"] == "old content"
        assert diff.changes["content"]["to"] == "new content"

    def test_diff_tags_change(self):
        v1 = MemoryVersion(
            version_id="a#1",
            item_id="a",
            version_number=1,
            content="x",
            tags=["a", "b"],
            importance=0.5,
            metadata={},
            created_at=100.0,
        )
        v2 = MemoryVersion(
            version_id="a#2",
            item_id="a",
            version_number=2,
            content="x",
            tags=["b", "c"],
            importance=0.5,
            metadata={},
            created_at=200.0,
        )
        diff = VersionDiff.between(v1, v2)
        assert "tags" in diff.changes
        assert set(diff.changes["tags"]["added"]) == {"c"}
        assert set(diff.changes["tags"]["removed"]) == {"a"}

    def test_diff_importance_change(self):
        v1 = MemoryVersion(
            version_id="a#1",
            item_id="a",
            version_number=1,
            content="x",
            tags=[],
            importance=0.3,
            metadata={},
            created_at=100.0,
        )
        v2 = MemoryVersion(
            version_id="a#2",
            item_id="a",
            version_number=2,
            content="x",
            tags=[],
            importance=0.9,
            metadata={},
            created_at=200.0,
        )
        diff = VersionDiff.between(v1, v2)
        assert "importance" in diff.changes
        assert diff.changes["importance"]["from"] == 0.3
        assert diff.changes["importance"]["to"] == 0.9

    def test_diff_metadata_change(self):
        v1 = MemoryVersion(
            version_id="a#1",
            item_id="a",
            version_number=1,
            content="x",
            tags=[],
            importance=0.5,
            metadata={"key1": "val1"},
            created_at=100.0,
        )
        v2 = MemoryVersion(
            version_id="a#2",
            item_id="a",
            version_number=2,
            content="x",
            tags=[],
            importance=0.5,
            metadata={"key1": "val1", "key2": "val2"},
            created_at=200.0,
        )
        diff = VersionDiff.between(v1, v2)
        assert "metadata" in diff.changes
        assert "key2" in diff.changes["metadata"]["added_keys"]

    def test_diff_different_items_raises(self):
        v1 = MemoryVersion(
            version_id="a#1",
            item_id="a",
            version_number=1,
            content="x",
            tags=[],
            importance=0.5,
            metadata={},
            created_at=100.0,
        )
        v2 = MemoryVersion(
            version_id="b#1",
            item_id="b",
            version_number=1,
            content="y",
            tags=[],
            importance=0.5,
            metadata={},
            created_at=200.0,
        )
        with pytest.raises(ValueError, match="Cannot diff"):
            VersionDiff.between(v1, v2)

    def test_diff_to_dict(self):
        v1 = MemoryVersion(
            version_id="a#1",
            item_id="a",
            version_number=1,
            content="old",
            tags=[],
            importance=0.5,
            metadata={},
            created_at=100.0,
        )
        v2 = MemoryVersion(
            version_id="a#2",
            item_id="a",
            version_number=2,
            content="new",
            tags=[],
            importance=0.5,
            metadata={},
            created_at=200.0,
        )
        diff = VersionDiff.between(v1, v2)
        d = diff.to_dict()
        assert d["item_id"] == "a"
        assert d["from_version"] == 1
        assert d["to_version"] == 2
        assert "content" in d["changes"]
        assert isinstance(d["delta_seconds"], float)


# ── VersionStore tests ───────────────────────────────────────


class TestVersionStore:
    def test_record_and_get(self):
        store = VersionStore()
        item = MemoryItem(id="m1", content="v1", tags=["t1"])
        v = store.record(item)

        assert v.version_number == 1
        assert v.content == "v1"

        retrieved = store.get_version("m1", 1)
        assert retrieved is not None
        assert retrieved.content == "v1"

    def test_multiple_versions(self):
        store = VersionStore()

        item_v1 = MemoryItem(id="m1", content="content v1", tags=["t1"])
        store.record(item_v1)

        item_v2 = MemoryItem(id="m1", content="content v2", tags=["t1", "t2"])
        store.record(item_v2)

        item_v3 = MemoryItem(id="m1", content="content v3", tags=["t1", "t2", "t3"])
        store.record(item_v3)

        versions = store.list_versions("m1")
        assert len(versions) == 3
        assert versions[0].content == "content v1"
        assert versions[1].content == "content v2"
        assert versions[2].content == "content v3"

        assert store.version_count("m1") == 3

    def test_latest_version(self):
        store = VersionStore()
        assert store.latest_version("m1") is None

        item = MemoryItem(id="m1", content="first")
        store.record(item)
        assert store.latest_version("m1").content == "first"

        item2 = MemoryItem(id="m1", content="second")
        store.record(item2)
        assert store.latest_version("m1").content == "second"

    def test_version_at_exact_time(self):
        store = VersionStore()

        t1 = time.time()
        item1 = MemoryItem(id="m1", content="before")
        v1 = store.record(item1)
        # Override created_at for testing
        v1.created_at = t1 - 100

        t2 = time.time()
        item2 = MemoryItem(id="m1", content="after")
        v2 = store.record(item2)
        v2.created_at = t2

        # Query at midpoint
        result = store.version_at("m1", t1 - 50)
        assert result is not None
        assert result.content == "before"

        result = store.version_at("m1", t2 + 10)
        assert result is not None
        assert result.content == "after"

    def test_version_at_before_any_version(self):
        store = VersionStore()
        item = MemoryItem(id="m1", content="exists")
        v = store.record(item)
        v.created_at = 2000.0

        assert store.version_at("m1", 1000.0) is None

    def test_all_at(self):
        store = VersionStore()

        item1 = MemoryItem(id="m1", content="mem1")
        v1 = store.record(item1)
        v1.created_at = 1000.0

        item2 = MemoryItem(id="m2", content="mem2")
        v2 = store.record(item2)
        v2.created_at = 2000.0

        # At t=1500, only m1 existed
        snapshot = store.all_at(1500.0)
        assert len(snapshot) == 1
        assert snapshot[0].item_id == "m1"

        # At t=2500, both exist
        snapshot = store.all_at(2500.0)
        assert len(snapshot) == 2

    def test_max_versions_gc(self):
        store = VersionStore(max_versions_per_item=5)

        item = MemoryItem(id="m1", content="base")
        for i in range(10):
            item = MemoryItem(id="m1", content=f"v{i}")
            store.record(item)

        # Should be capped at 5
        versions = store.list_versions("m1")
        assert len(versions) == 5
        # Should keep the latest versions
        assert versions[0].content == "v5"
        assert versions[-1].content == "v9"

    def test_delete_versions(self):
        store = VersionStore()
        item = MemoryItem(id="m1", content="x")
        store.record(item)
        assert store.version_count("m1") == 1

        deleted = store.delete_versions("m1")
        assert deleted == 1
        assert store.version_count("m1") == 0

    def test_gc(self):
        store = VersionStore()
        now = time.time()

        # Create old versions
        for i in range(5):
            item = MemoryItem(id="m1", content=f"old-{i}")
            v = store.record(item)
            v.created_at = now - 200 * 86400  # 200 days ago

        # Create recent versions
        for i in range(3):
            item = MemoryItem(id="m1", content=f"recent-{i}")
            v = store.record(item)
            v.created_at = now - 1 * 86400  # 1 day ago

        # GC: remove older than 90 days, keep at least 3
        removed = store.gc(max_age_days=90.0, keep_latest=3)
        assert removed == 5

        versions = store.list_versions("m1")
        assert len(versions) == 3
        assert all("recent" in v.content for v in versions)

    def test_stats(self):
        store = VersionStore()
        item = MemoryItem(id="m1", content="a")
        store.record(item)
        store.record(MemoryItem(id="m1", content="b"))
        store.record(MemoryItem(id="m2", content="c"))

        stats = store.stats()
        assert stats["total_items"] == 2
        assert stats["total_versions"] == 3
        assert stats["avg_versions_per_item"] == 1.5

    def test_clear(self):
        store = VersionStore()
        store.record(MemoryItem(id="m1", content="x"))
        store.clear()
        assert store.stats()["total_items"] == 0


# ── VersioningEngine tests ───────────────────────────────────


class TestVersioningEngine:
    def test_record_version(self):
        engine = VersioningEngine()
        item = MemoryItem(id="m1", content="hello")
        v = engine.record_version(item, source="learn")

        assert v.version_number == 1
        assert v.source == "learn"
        assert v.content == "hello"

    def test_history(self):
        engine = VersioningEngine()
        for i in range(4):
            engine.record_version(MemoryItem(id="m1", content=f"v{i}"))

        history = engine.history("m1")
        assert len(history) == 4
        assert history[0].content == "v0"
        assert history[3].content == "v3"

    def test_get_version(self):
        engine = VersioningEngine()
        engine.record_version(MemoryItem(id="m1", content="first"))
        engine.record_version(MemoryItem(id="m1", content="second"))

        v1 = engine.get_version("m1", 1)
        assert v1.content == "first"

        v2 = engine.get_version("m1", 2)
        assert v2.content == "second"

        assert engine.get_version("m1", 99) is None

    def test_latest_version(self):
        engine = VersioningEngine()
        assert engine.latest_version("m1") is None

        engine.record_version(MemoryItem(id="m1", content="a"))
        engine.record_version(MemoryItem(id="m1", content="b"))
        assert engine.latest_version("m1").content == "b"

    def test_diff(self):
        engine = VersioningEngine()
        engine.record_version(MemoryItem(id="m1", content="old", tags=["a"], importance=0.3))
        engine.record_version(MemoryItem(id="m1", content="new", tags=["b"], importance=0.9))

        diff = engine.diff("m1", 1, 2)
        assert diff is not None
        assert "content" in diff.changes
        assert "tags" in diff.changes
        assert "importance" in diff.changes
        assert diff.changes["tags"]["added"] == ["b"]
        assert diff.changes["tags"]["removed"] == ["a"]

    def test_diff_nonexistent(self):
        engine = VersioningEngine()
        assert engine.diff("m1", 1, 2) is None

    def test_diff_latest(self):
        engine = VersioningEngine()
        assert engine.diff_latest("m1") is None

        engine.record_version(MemoryItem(id="m1", content="only"))
        assert engine.diff_latest("m1") is None  # Only 1 version

        engine.record_version(MemoryItem(id="m1", content="second"))
        diff = engine.diff_latest("m1")
        assert diff is not None
        assert diff.changes["content"]["from"] == "only"
        assert diff.changes["content"]["to"] == "second"

    def test_snapshot_at(self):
        engine = VersioningEngine()
        now = time.time()

        v1 = engine.record_version(MemoryItem(id="m1", content="old"))
        v1.created_at = now - 200

        v2 = engine.record_version(MemoryItem(id="m2", content="recent"))
        v2.created_at = now - 50

        # At now-100, only m1 existed
        snap = engine.snapshot_at(now - 100)
        assert len(snap) == 1
        assert snap[0].item_id == "m1"

    def test_version_at(self):
        engine = VersioningEngine()
        now = time.time()

        v = engine.record_version(MemoryItem(id="m1", content="past"))
        v.created_at = now - 100

        result = engine.version_at("m1", now - 50)
        assert result is not None
        assert result.content == "past"

    def test_recall_at(self):
        engine = VersioningEngine()
        now = time.time()

        # Record m1 in the past
        v1 = engine.record_version(MemoryItem(id="m1", content="past content"))
        v1.created_at = now - 200

        # Record m2 more recently
        v2 = engine.record_version(MemoryItem(id="m2", content="recent content"))
        v2.created_at = now - 50

        items = [
            MemoryItem(id="m1", content="current m1"),
            MemoryItem(id="m2", content="current m2"),
        ]
        result = engine.recall_at(items, now - 100)
        assert len(result) == 1
        assert result[0].content == "past content"


# ── Integration tests (MemOS) ────────────────────────────────


class TestMemOSVersioning:
    def test_learn_creates_version(self):
        mem = MemOS()
        item = mem.learn("first memory", tags=["v1"])
        versions = mem.history(item.id)
        assert len(versions) == 1
        assert versions[0].content == "first memory"
        assert versions[0].source == "learn"

    def test_multiple_learns_create_versions(self):
        mem = MemOS()
        content = "unique test content for version test"

        item1 = mem.learn(content, tags=["v1"], importance=0.3)
        # Re-learn same content updates the item
        item2 = mem.learn(content, tags=["v1", "v2"], importance=0.9)

        # Same ID (deterministic from content)
        assert item1.id == item2.id

        versions = mem.history(item1.id)
        assert len(versions) == 2
        assert versions[0].tags == ["v1"]
        assert versions[1].tags == ["v1", "v2"]

    def test_get_specific_version(self):
        mem = MemOS()
        content = "versioned item content"
        mem.learn(content, tags=["initial"], importance=0.5)
        mem.learn(content, tags=["updated"], importance=0.8)

        item_id = generate_id(content)
        v1 = mem.get_version(item_id, 1)
        assert v1 is not None
        assert v1.tags == ["initial"]

        v2 = mem.get_version(item_id, 2)
        assert v2 is not None
        assert v2.tags == ["updated"]

    def test_diff_between_versions(self):
        mem = MemOS()
        content = "diff test content unique"
        mem.learn(content, tags=["old"], importance=0.3)
        mem.learn(content, tags=["new"], importance=0.9)

        item_id = generate_id(content)
        diff = mem.diff(item_id, 1, 2)
        assert diff is not None
        assert "tags" in diff.changes
        assert "importance" in diff.changes

    def test_diff_latest(self):
        mem = MemOS()
        content = "diff latest test unique"
        mem.learn(content, tags=["first"])
        assert mem.diff_latest(generate_id(content)) is None  # Only 1 version

        mem.learn(content, tags=["second"])
        diff = mem.diff_latest(generate_id(content))
        assert diff is not None
        assert "tags" in diff.changes

    def test_time_travel_recall(self):
        mem = MemOS()

        # Learn item 1
        item1 = mem.learn("ancient knowledge about python", tags=["python"])

        # Manually set version timestamp to the past
        versions = mem.history(item1.id)
        versions[0].created_at = time.time() - 3600  # 1 hour ago

        # Learn item 2 now
        mem.learn("recent knowledge about rust", tags=["rust"])

        # Recall at a time when only item1 existed
        past_ts = time.time() - 1800  # 30 min ago
        results = mem.recall_at("programming knowledge", past_ts)

        # Should only find item1 (item2 didn't exist 30min ago)
        ids = [r.item.id for r in results]
        assert item1.id in ids

    def test_snapshot_at(self):
        mem = MemOS()

        item1 = mem.learn("snapshot item 1")
        versions = mem.history(item1.id)
        versions[0].created_at = time.time() - 200

        item2 = mem.learn("snapshot item 2")
        versions2 = mem.history(item2.id)
        versions2[0].created_at = time.time() - 100

        snapshot = mem.snapshot_at(time.time() - 50)
        assert len(snapshot) == 2

        snapshot_old = mem.snapshot_at(time.time() - 150)
        assert len(snapshot_old) == 1

    def test_rollback(self):
        mem = MemOS()
        content = "rollback test content unique"

        mem.learn(content, tags=["original"], importance=0.5)
        mem.learn(content, tags=["modified"], importance=0.9)

        item_id = generate_id(content)

        # Rollback to version 1
        restored = mem.rollback(item_id, 1)
        assert restored is not None
        assert restored.tags == ["original"]
        assert restored.importance == 0.5

        # Should have created a new version (rollback)
        versions = mem.history(item_id)
        assert len(versions) == 3
        assert versions[-1].source.startswith("rollback")

    def test_rollback_nonexistent_version(self):
        mem = MemOS()
        item = mem.learn("some content for rollback")
        assert mem.rollback(item.id, 99) is None

    def test_versioning_stats(self):
        mem = MemOS()
        mem.learn("stats test 1")
        mem.learn("stats test 2")

        stats = mem.versioning_stats()
        assert stats["total_items"] == 2
        assert stats["total_versions"] == 2

    def test_versioning_gc(self):
        mem = MemOS()
        content = "gc test content unique"
        now = time.time()

        # Create old versions
        for i in range(5):
            item = mem.learn(content, tags=[f"old-{i}"])
            versions = mem.history(item.id)
            versions[-1].created_at = now - 200 * 86400

        # Create recent version
        mem.learn(content, tags=["recent"])

        removed = mem.versioning_gc(max_age_days=90.0, keep_latest=2)
        assert removed > 0

    def test_versioning_property_access(self):
        mem = MemOS()
        assert mem.versioning is not None
        assert isinstance(mem.versioning, VersioningEngine)

    def test_recall_at_excludes_nonexistent(self):
        mem = MemOS()

        # Learn something now
        mem.learn("only recent memory")

        # Recall at a time before this item existed
        past_ts = time.time() - 86400  # 1 day ago
        results = mem.recall_at("memory", past_ts)
        assert len(results) == 0

    def test_time_travel_event_emitted(self):
        mem = MemOS()

        item = mem.learn("event test memory")
        versions = mem.history(item.id)
        versions[0].created_at = time.time() - 100

        # Time-travel recall
        mem.recall_at("event", time.time() - 50)

        events = mem.events.get_history("time_traveled")
        assert len(events) == 1
        assert events[0].data["results"] >= 1

    def test_rollback_event_emitted(self):
        mem = MemOS()
        content = "rollback event test"
        mem.learn(content, tags=["v1"])
        mem.learn(content, tags=["v2"])

        item_id = generate_id(content)
        mem.rollback(item_id, 1)

        events = mem.events.get_history("rolled_back")
        assert len(events) == 1
        assert events[0].data["to_version"] == 1

    def test_batch_learn_creates_versions(self):
        mem = MemOS()
        result = mem.batch_learn(
            [
                {"content": "batch item 1 unique", "tags": ["batch"]},
                {"content": "batch item 2 unique", "tags": ["batch"]},
                {"content": "batch item 3 unique", "tags": ["batch"]},
            ]
        )

        assert result["learned"] == 3
        stats = mem.versioning_stats()
        assert stats["total_items"] == 3
        assert stats["total_versions"] == 3

    def test_different_items_independent_versions(self):
        mem = MemOS()

        mem.learn("item alpha content", tags=["alpha"])
        mem.learn("item alpha content", tags=["alpha", "updated"])

        mem.learn("item beta content", tags=["beta"])

        alpha_id = generate_id("item alpha content")
        beta_id = generate_id("item beta content")

        assert len(mem.history(alpha_id)) == 2
        assert len(mem.history(beta_id)) == 1


# ── Phase 2 runtime-path hardening tests ───────────────────────


class TestForgetVersionRecording:
    def test_forget_records_deletion_version(self):
        mem = MemOS()
        item = mem.learn("to be forgotten unique content", tags=["temp"])
        versions_before = mem.history(item.id)
        assert len(versions_before) == 1

        mem.forget(item.id)

        versions_after = mem.history(item.id)
        assert len(versions_after) == 2
        assert versions_after[-1].source == "forget"

    def test_forget_tag_records_deletion_version(self):
        mem = MemOS()
        item_a = mem.learn("tagged item alpha unique", tags=["doomed"])
        item_b = mem.learn("tagged item beta unique", tags=["doomed"])
        mem.learn("safe item unique", tags=["safe"])

        removed = mem.forget_tag("doomed")
        assert removed == 2

        versions_a = mem.history(item_a.id)
        assert len(versions_a) == 2
        assert versions_a[-1].source == "forget_tag"

        versions_b = mem.history(item_b.id)
        assert len(versions_b) == 2
        assert versions_b[-1].source == "forget_tag"

    def test_forget_nonexistent_no_version(self):
        mem = MemOS()
        result = mem.forget("nonexistent-id")
        assert result is False
        assert mem.versioning_stats()["total_versions"] == 0


class TestTagMutationVersionRecording:
    def test_rename_tag_records_version(self):
        mem = MemOS()
        item = mem.learn("tagged memory unique for rename", tags=["old-tag"])

        updated = mem.rename_tag("old-tag", "new-tag")
        assert updated == 1

        versions = mem.history(item.id)
        assert len(versions) == 2
        assert versions[0].source == "learn"
        assert versions[1].source == "rename_tag"
        assert "new-tag" in versions[1].tags
        assert "old-tag" not in versions[1].tags

    def test_delete_tag_records_version(self):
        mem = MemOS()
        item = mem.learn("memory with removable tag unique", tags=["keep", "remove"])

        updated = mem.delete_tag("remove")
        assert updated == 1

        versions = mem.history(item.id)
        assert len(versions) == 2
        assert versions[0].source == "learn"
        assert versions[1].source == "delete_tag"
        assert "remove" not in versions[1].tags
        assert "keep" in versions[1].tags

    def test_rename_tag_version_diff(self):
        mem = MemOS()
        item = mem.learn("diff test after rename unique", tags=["original"])

        mem.rename_tag("original", "renamed")

        diff = mem.diff_latest(item.id)
        assert diff is not None
        assert "tags" in diff.changes
        assert "renamed" in diff.changes["tags"]["added"]


class TestImportVersionSource:
    def test_import_json_version_source_is_import(self):
        mem = MemOS()
        mem.import_json(
            {"memories": [{"content": "check source unique content", "tags": ["src-test"]}]}
        )
        items = mem._store.list_all()
        versions = mem.history(items[0].id)
        assert len(versions) == 1
        assert versions[0].source == "import"

    def test_import_json_then_learn_adds_second_version(self):
        mem = MemOS()
        content = "version lifecycle test unique content"
        mem.import_json(
            {"memories": [{"content": content, "tags": ["imported"]}]}
        )
        item_id = mem._store.list_all()[0].id

        mem.learn(content, tags=["imported", "updated"])

        versions = mem.history(item_id)
        assert len(versions) == 2
        assert versions[0].source == "import"
        assert versions[1].source == "learn"
