"""Tests for memos get command — retrieve single memory by ID."""
import json
import pytest
from memos.core import MemOS
from memos.models import MemoryItem


class TestCoreGet:
    """Test MemOS.get() method."""

    def test_get_existing_item(self):
        m = MemOS()
        item = m.learn("hello world", tags=["test"], importance=0.8)
        retrieved = m.get(item.id)
        assert retrieved is not None
        assert retrieved.id == item.id
        assert retrieved.content == "hello world"
        assert "test" in retrieved.tags
        assert retrieved.importance == 0.8

    def test_get_nonexistent_returns_none(self):
        m = MemOS()
        item = m.get("does-not-exist")
        assert item is None

    def test_get_preserves_ttl(self):
        m = MemOS()
        item = m.learn("ttl memory", tags=["test"], ttl=3600)
        retrieved = m.get(item.id)
        assert retrieved is not None
        assert retrieved.ttl == 3600
        assert retrieved.expires_at is not None
        assert not retrieved.is_expired

    def test_get_preserves_access_count(self):
        m = MemOS()
        item = m.learn("meta memory", tags=["test"], importance=0.9)
        retrieved = m.get(item.id)
        assert retrieved is not None
        assert retrieved.access_count >= 0

    def test_get_after_recall_updates_access(self):
        m = MemOS()
        item = m.learn("recalled item", tags=["test"])
        m.recall("recalled item")
        retrieved = m.get(item.id)
        assert retrieved is not None
        assert retrieved.access_count >= 1

    def test_get_json_serializable_fields(self):
        m = MemOS()
        item = m.learn("json output test", tags=["test"])
        retrieved = m.get(item.id)
        assert retrieved is not None
        data = {
            "id": retrieved.id,
            "content": retrieved.content,
            "tags": retrieved.tags,
            "importance": retrieved.importance,
            "ttl": retrieved.ttl,
        }
        serialized = json.dumps(data)
        parsed = json.loads(serialized)
        assert parsed["id"] == item.id
        assert parsed["content"] == "json output test"
        assert parsed["ttl"] is None


class TestJsonBackendTTL:
    """Test that TTL is properly persisted in JSON backend."""

    def test_ttl_round_trip(self, tmp_path):
        from memos.storage.json_backend import JsonFileBackend
        path = str(tmp_path / "test.json")
        backend = JsonFileBackend(path=path)
        item = MemoryItem(id="test-ttl", content="ttl test", tags=[], ttl=7200)
        backend.upsert(item)
        retrieved = backend.get("test-ttl")
        assert retrieved is not None
        assert retrieved.ttl == 7200

    def test_no_ttl_round_trip(self, tmp_path):
        from memos.storage.json_backend import JsonFileBackend
        path = str(tmp_path / "test.json")
        backend = JsonFileBackend(path=path)
        item = MemoryItem(id="test-no-ttl", content="no ttl", tags=[])
        backend.upsert(item)
        retrieved = backend.get("test-no-ttl")
        assert retrieved is not None
        assert retrieved.ttl is None

    def test_ttl_survives_multiple_writes(self, tmp_path):
        from memos.storage.json_backend import JsonFileBackend
        path = str(tmp_path / "test.json")
        backend = JsonFileBackend(path=path)
        item = MemoryItem(id="multi", content="multi write", tags=[], ttl=1800, importance=0.9)
        backend.upsert(item)
        item.importance = 0.7
        backend.upsert(item)
        backend2 = JsonFileBackend(path=path)
        retrieved = backend2.get("multi")
        assert retrieved is not None
        assert retrieved.ttl == 1800
        assert retrieved.importance == 0.7
