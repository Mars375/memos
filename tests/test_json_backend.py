"""Tests for JsonFileBackend — persistent file-backed storage."""

import json

import pytest

from memos.models import MemoryItem
from memos.storage.json_backend import JsonFileBackend


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "test_store.json"


@pytest.fixture
def backend(store_path):
    return JsonFileBackend(path=store_path)


def _item(content="hello", tags=None, mid=None):
    from memos.models import generate_id
    return MemoryItem(
        id=mid or generate_id(content),
        content=content,
        tags=tags or [],
        importance=0.5,
    )


class TestJsonFileBackendBasic:
    def test_empty_backend(self, backend, store_path):
        assert backend.list_all() == []
        assert backend.get("nonexistent") is None

    def test_upsert_and_get(self, backend, store_path):
        item = _item("test memory")
        backend.upsert(item)
        got = backend.get(item.id)
        assert got is not None
        assert got.content == "test memory"
        assert got.id == item.id
        # File should exist
        assert store_path.is_file()

    def test_upsert_updates_existing(self, backend):
        item = _item("original")
        backend.upsert(item)
        item.content = "updated"
        backend.upsert(item)
        got = backend.get(item.id)
        assert got.content == "updated"

    def test_delete(self, backend):
        item = _item("to delete")
        backend.upsert(item)
        assert backend.delete(item.id) is True
        assert backend.get(item.id) is None

    def test_delete_nonexistent(self, backend):
        assert backend.delete("nope") is False

    def test_list_all(self, backend):
        items = [_item(f"mem {i}") for i in range(5)]
        for item in items:
            backend.upsert(item)
        all_items = backend.list_all()
        assert len(all_items) == 5
        contents = {i.content for i in all_items}
        assert contents == {f"mem {i}" for i in range(5)}

    def test_search_content(self, backend):
        backend.upsert(_item("python is great"))
        backend.upsert(_item("java is okay"))
        backend.upsert(_item("rust is fast"))
        results = backend.search("python")
        assert len(results) == 1
        assert results[0].content == "python is great"

    def test_search_tags(self, backend):
        backend.upsert(_item("info", tags=["python", "ai"]))
        backend.upsert(_item("other", tags=["java"]))
        results = backend.search("python")
        assert len(results) == 1
        assert results[0].content == "info"

    def test_search_limit(self, backend):
        for i in range(10):
            backend.upsert(_item(f"match {i}"))
        results = backend.search("match", limit=3)
        assert len(results) == 3


class TestJsonFileBackendPersistence:
    def test_data_survives_reopen(self, store_path):
        """Critical test: data must survive process restart."""
        item = _item("persistent memory", tags=["important"])
        b1 = JsonFileBackend(path=store_path)
        b1.upsert(item)

        # Simulate new process by creating a fresh instance
        b2 = JsonFileBackend(path=store_path)
        got = b2.get(item.id)
        assert got is not None
        assert got.content == "persistent memory"
        assert got.tags == ["important"]

    def test_delete_survives_reopen(self, store_path):
        item = _item("will be deleted")
        b1 = JsonFileBackend(path=store_path)
        b1.upsert(item)
        b1.delete(item.id)

        b2 = JsonFileBackend(path=store_path)
        assert b2.get(item.id) is None

    def test_multiple_items_persist(self, store_path):
        items = [_item(f"mem {i}", tags=[f"tag{i}"]) for i in range(20)]
        b1 = JsonFileBackend(path=store_path)
        for item in items:
            b1.upsert(item)

        b2 = JsonFileBackend(path=store_path)
        all_items = b2.list_all()
        assert len(all_items) == 20

    def test_file_format_is_valid_json(self, store_path):
        b = JsonFileBackend(path=store_path)
        b.upsert(_item("check format"))
        raw = store_path.read_text()
        data = json.loads(raw)
        assert isinstance(data, dict)

    def test_corrupted_file_graceful(self, store_path):
        """If file is corrupted, start empty (no crash)."""
        store_path.write_text("NOT VALID JSON{{{")
        b = JsonFileBackend(path=store_path)
        assert b.list_all() == []

    def test_missing_directory_created(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "store.json"
        b = JsonFileBackend(path=path)
        b.upsert(_item("deep path"))
        assert path.is_file()


class TestJsonFileBackendNamespaces:
    def test_namespace_isolation(self, backend):
        item1 = _item("global")
        item2 = _item("ns1")
        backend.upsert(item1, namespace="")
        backend.upsert(item2, namespace="ns1")
        assert len(backend.list_all(namespace="")) == 1
        assert len(backend.list_all(namespace="ns1")) == 1
        assert backend.get(item2.id, namespace="") is None
        assert backend.get(item2.id, namespace="ns1") is not None

    def test_list_namespaces(self, backend):
        backend.upsert(_item("a"), namespace="alpha")
        backend.upsert(_item("b"), namespace="beta")
        ns = backend.list_namespaces()
        assert "alpha" in ns
        assert "beta" in ns
        assert "" not in ns  # default namespace not listed

    def test_namespace_persistence(self, store_path):
        b1 = JsonFileBackend(path=store_path)
        b1.upsert(_item("ns data"), namespace="test-ns")

        b2 = JsonFileBackend(path=store_path)
        items = b2.list_all(namespace="test-ns")
        assert len(items) == 1
        assert items[0].content == "ns data"


class TestMemOSWithPersistPath:
    """Integration test: MemOS with persist_path actually persists."""

    def test_memos_persist_learn_recall(self, tmp_path):
        from memos.core import MemOS
        store = tmp_path / "store.json"
        m1 = MemOS(backend="memory", persist_path=str(store), sanitize=False)
        m1.learn("persistent test", tags=["test"])

        m2 = MemOS(backend="memory", persist_path=str(store), sanitize=False)
        results = m2.recall("persistent")
        assert len(results) >= 1
        assert any("persistent test" in r.item.content for r in results)

    def test_memos_json_backend(self, tmp_path):
        from memos.core import MemOS
        store = tmp_path / "store.json"
        m = MemOS(backend="json", persist_path=str(store), sanitize=False)
        item = m.learn("json backend test", tags=["json"])
        got = m._store.get(item.id)
        assert got.content == "json backend test"

    def test_memos_forget_persists(self, tmp_path):
        from memos.core import MemOS
        store = tmp_path / "store.json"
        m1 = MemOS(backend="memory", persist_path=str(store), sanitize=False)
        m1.learn("to forget", tags=["temp"])

        m2 = MemOS(backend="memory", persist_path=str(store), sanitize=False)
        m2.forget_tag("temp")

        m3 = MemOS(backend="memory", persist_path=str(store), sanitize=False)
        results = m3.recall("forget")
        assert len(results) == 0
