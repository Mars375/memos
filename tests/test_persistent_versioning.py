"""Tests for persistent versioning (SQLite backend)."""

import os
import tempfile
import time

from freezegun import freeze_time

from memos import MemOS
from memos.models import MemoryItem, generate_id
from memos.versioning.engine import VersioningEngine
from memos.versioning.persistent_store import SqliteVersionStore


class TestSqliteVersionStore:
    """Test SQLite-backed persistent version store."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_versions.db")
        self.store = SqliteVersionStore(self.db_path)

    def _make_item(self, content="test memory", tags=None, importance=0.5):
        return MemoryItem(
            id=generate_id(content),
            content=content,
            tags=tags or [],
            importance=importance,
        )

    def test_create_store(self):
        assert os.path.exists(self.db_path)

    def test_record_and_get(self):
        item = self._make_item("hello world")
        v = self.store.record(item, source="learn")
        assert v.item_id == item.id
        assert v.version_number == 1
        assert v.content == "hello world"

        fetched = self.store.get_version(item.id, 1)
        assert fetched is not None
        assert fetched.content == "hello world"

    def test_multiple_versions(self):
        item = self._make_item("v1")
        v1 = self.store.record(item, source="learn")

        item.content = "v2"
        v2 = self.store.record(item, source="update")

        item.content = "v3"
        v3 = self.store.record(item, source="update")

        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v3.version_number == 3

        versions = self.store.list_versions(item.id)
        assert len(versions) == 3
        assert versions[0].content == "v1"
        assert versions[2].content == "v3"

    def test_latest_version(self):
        item = self._make_item("initial")
        self.store.record(item)
        item.content = "updated"
        self.store.record(item)

        latest = self.store.latest_version(item.id)
        assert latest is not None
        assert latest.content == "updated"
        assert latest.version_number == 2

    def test_version_count(self):
        item = self._make_item("counter")
        assert self.store.version_count(item.id) == 0
        self.store.record(item)
        assert self.store.version_count(item.id) == 1
        self.store.record(item)
        assert self.store.version_count(item.id) == 2

    def test_version_at(self):
        with freeze_time("2024-01-01 12:00:00") as frozen:
            item = self._make_item("time travel")
            self.store.record(item)
            t_after_v1 = time.time()

            frozen.tick(2)
            item.content = "updated"
            v2 = self.store.record(item)
            t_after_v2 = time.time()

            assert self.store.version_at(item.id, 0.0) is None

            result = self.store.version_at(item.id, (t_after_v1 + v2.created_at) / 2)
            assert result is not None
            assert result.version_number == 1

            result = self.store.version_at(item.id, t_after_v2 + 1)
            assert result is not None
            assert result.version_number == 2

    def test_all_at(self):
        with freeze_time("2024-01-01 12:00:00") as frozen:
            item1 = self._make_item("item one")
            item2 = self._make_item("item two")

            self.store.record(item1)
            t = time.time()
            frozen.tick(2)
            self.store.record(item2)

            snapshot = self.store.all_at(t)
            assert len(snapshot) == 1
            assert snapshot[0].content == "item one"

    def test_delete_versions(self):
        item = self._make_item("deletable")
        self.store.record(item)
        self.store.record(item)
        assert self.store.delete_versions(item.id) == 2
        assert self.store.version_count(item.id) == 0

    def test_gc(self):
        item = self._make_item("old memory")
        # Record a version with old timestamp by manipulating directly
        with self.store._connect() as conn:
            conn.execute(
                """
                INSERT INTO versions
                (item_id, version_number, version_id, content, tags_json,
                 importance, metadata_json, created_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (item.id, 1, f"{item.id}#1", "old", "[]", 0.5, "{}", time.time() - 200 * 86400, "learn"),
            )
            conn.execute(
                """
                INSERT INTO versions
                (item_id, version_number, version_id, content, tags_json,
                 importance, metadata_json, created_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (item.id, 2, f"{item.id}#2", "recent", "[]", 0.5, "{}", time.time() - 1, "learn"),
            )
            conn.execute(
                """
                INSERT INTO versions
                (item_id, version_number, version_id, content, tags_json,
                 importance, metadata_json, created_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (item.id, 3, f"{item.id}#3", "latest", "[]", 0.5, "{}", time.time(), "learn"),
            )
            conn.commit()

        # GC: remove older than 90 days, keep latest 2
        removed = self.store.gc(max_age_days=90.0, keep_latest=2)
        assert removed == 1  # v1 was older than 90 days and not in latest 2
        assert self.store.version_count(item.id) == 2

    def test_stats(self):
        item = self._make_item("stats test")
        self.store.record(item)
        stats = self.store.stats()
        assert stats["total_items"] == 1
        assert stats["total_versions"] == 1
        assert stats["backend"] == "sqlite"
        assert stats["path"] == self.db_path

    def test_clear(self):
        item = self._make_item("clearable")
        self.store.record(item)
        self.store.record(item)
        self.store.clear()
        assert self.store.version_count(item.id) == 0

    def test_auto_gc_on_overflow(self):
        store = SqliteVersionStore(self.db_path, max_versions_per_item=3)
        item = self._make_item("overflow")
        for i in range(5):
            item.content = f"version {i}"
            store.record(item)

        assert store.version_count(item.id) == 3  # only keeps last 3

    def test_persistence_across_reopens(self):
        item = self._make_item("persistent")
        self.store.record(item)

        # Reopen the store
        store2 = SqliteVersionStore(self.db_path)
        assert store2.version_count(item.id) == 1
        fetched = store2.get_version(item.id, 1)
        assert fetched.content == "persistent"

    def test_thread_safety(self):
        import threading

        errors = []

        def writer(content):
            try:
                item = self._make_item(content)
                for i in range(10):
                    item.content = f"{content} v{i}"
                    self.store.record(item)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(f"thread-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestVersioningEnginePersistent:
    """Test VersioningEngine with persistent backend."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "engine_versions.db")

    def test_persistent_engine_creation(self):
        engine = VersioningEngine(persistent_path=self.db_path)
        assert engine.is_persistent

    def test_in_memory_engine_not_persistent(self):
        engine = VersioningEngine()
        assert not engine.is_persistent

    def test_persistent_history_and_recall(self):
        engine = VersioningEngine(persistent_path=self.db_path)

        item = MemoryItem(
            id="test-123",
            content="hello",
            tags=["test"],
            importance=0.7,
        )
        engine.record_version(item, source="learn")
        item.content = "world"
        engine.record_version(item, source="update")

        history = engine.history("test-123")
        assert len(history) == 2
        assert history[0].content == "hello"
        assert history[1].content == "world"

    def test_persistent_diff(self):
        engine = VersioningEngine(persistent_path=self.db_path)

        item = MemoryItem(
            id="diff-test",
            content="v1",
            tags=["a"],
            importance=0.5,
        )
        engine.record_version(item)
        item.content = "v2"
        item.tags = ["a", "b"]
        engine.record_version(item)

        diff = engine.diff("diff-test", 1, 2)
        assert diff is not None
        assert "content" in diff.changes
        assert "tags" in diff.changes


class TestMemOSPersistentVersioning:
    """Test MemOS with persistent versioning."""

    def test_versioning_path_option(self):
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "memos_versions.db")
        mem = MemOS(backend="memory", versioning_path=db_path)

        item = mem.learn("persistent versioning test", tags=["test"])
        assert mem.versioning.is_persistent

        history = mem.history(item.id)
        assert len(history) == 1
        assert history[0].source == "learn"

    def test_persistent_versioning_survives_restart(self):
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "memos_versions.db")

        # Session 1
        mem1 = MemOS(backend="memory", versioning_path=db_path)
        item = mem1.learn("important memory", tags=["persistent"])
        mem1._versioning.record_version(
            MemoryItem(id=item.id, content="updated memory", tags=["persistent", "v2"]),
            source="update",
        )

        # Session 2 (re-open)
        mem2 = MemOS(backend="memory", versioning_path=db_path)
        history = mem2.history(item.id)
        assert len(history) == 2
        assert history[0].content == "important memory"
        assert history[1].content == "updated memory"
