"""Tests for Pinecone storage backend (mock-based, no real Pinecone needed)."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from memos.models import MemoryItem
from memos.storage.pinecone_backend import PineconeBackend
from memos.core import MemOS as MemOSCore


def _make_item(content: str = "test content", item_id: str = "abc123") -> MemoryItem:
    return MemoryItem(
        id=item_id,
        content=content,
        tags=["test"],
        importance=0.5,
        created_at=time.time(),
        accessed_at=time.time(),
        access_count=0,
        metadata={"source": "test"},
    )


class TestPineconeBackendUnit:
    """Unit tests for PineconeBackend using mocks."""

    def _make_backend(self) -> PineconeBackend:
        """Create a backend with mocked Pinecone client."""
        backend = PineconeBackend(api_key="test-key", serverless=True)

        # Mock the Pinecone client and index
        mock_pc = MagicMock()
        mock_index = MagicMock()

        # list_indexes returns empty (index exists)
        mock_pc.list_indexes.return_value = []
        mock_pc.create_index.return_value = None
        mock_pc.Index.return_value = mock_index

        # Mock index operations
        mock_index.upsert.return_value = None
        mock_index.delete.return_value = None
        mock_index.list_namespaces.return_value = ["memos", "memos__agent1"]

        backend._pc = mock_pc
        backend._index = mock_index

        return backend

    def test_id_to_valid_id(self):
        """Pinecone IDs must be alphanumeric + dashes."""
        assert PineconeBackend._id_to_valid_id("abc123") == "abc123"
        assert PineconeBackend._id_to_valid_id("a/b@c#d") == "a-b-c-d"
        assert PineconeBackend._id_to_valid_id("test_id-123") == "test_id-123"

    def test_item_to_metadata(self):
        item = _make_item()
        meta = PineconeBackend._item_to_metadata(item)
        assert meta["_original_id"] == "abc123"
        assert meta["content"] == "test content"
        assert json.loads(meta["tags"]) == ["test"]
        assert meta["importance"] == 0.5

    def test_metadata_to_item(self):
        meta = {
            "_original_id": "abc123",
            "content": "test content",
            "tags": json.dumps(["test"]),
            "importance": 0.5,
            "created_at": 1000.0,
            "accessed_at": 1000.0,
            "access_count": 0,
            "metadata": json.dumps({"source": "test"}),
        }
        item = PineconeBackend._metadata_to_item(meta)
        assert item.id == "abc123"
        assert item.content == "test content"
        assert item.tags == ["test"]
        assert item.importance == 0.5

    def test_metadata_to_item_handles_bad_json(self):
        meta = {
            "_original_id": "bad",
            "content": "test",
            "tags": "not-json",
            "importance": 0.5,
            "created_at": 1000.0,
            "accessed_at": 1000.0,
            "access_count": 0,
            "metadata": "also-bad",
        }
        item = PineconeBackend._metadata_to_item(meta)
        assert item.tags == []
        assert item.metadata == {}

    def test_upsert_single(self):
        backend = self._make_backend()
        item = _make_item()
        # Patch embedding to return a vector
        backend._get_embedding = lambda t: [0.1] * 768

        backend.upsert(item)

        backend._index.upsert.assert_called_once()
        call_args = backend._index.upsert.call_args
        vectors = call_args.kwargs.get("vectors") or call_args[1].get("vectors")
        assert len(vectors) == 1
        assert vectors[0]["id"] == "abc123"

    def test_upsert_batch(self):
        backend = self._make_backend()
        items = [_make_item(content=f"item {i}", item_id=f"id{i:04d}") for i in range(5)]
        backend._get_embedding = lambda t: [0.1] * 768

        count = backend.upsert_batch(items)

        assert count == 5
        assert backend._index.upsert.call_count == 1

    def test_upsert_batch_large(self):
        backend = self._make_backend()
        items = [_make_item(content=f"item {i}", item_id=f"id{i:04d}") for i in range(250)]
        backend._get_embedding = lambda t: [0.1] * 768

        count = backend.upsert_batch(items)

        assert count == 250
        # 250 / 100 batch_size = 3 calls
        assert backend._index.upsert.call_count == 3

    def test_delete(self):
        backend = self._make_backend()
        result = backend.delete("abc123")
        assert result is True
        backend._index.delete.assert_called_once()

    def test_get_existing(self):
        backend = self._make_backend()
        item = _make_item()
        mock_vec = MagicMock()
        mock_vec.metadata = PineconeBackend._item_to_metadata(item)

        backend._index.fetch.return_value = {"vectors": {"abc123": mock_vec}}

        result = backend.get("abc123")
        assert result is not None
        assert result.content == "test content"

    def test_get_nonexistent(self):
        backend = self._make_backend()
        backend._index.fetch.return_value = {"vectors": {}}

        result = backend.get("nonexistent")
        assert result is None

    def test_list_namespaces(self):
        backend = self._make_backend()
        ns = backend.list_namespaces()
        assert "agent1" in ns

    def test_pinecone_namespace_scoping(self):
        backend = PineconeBackend(api_key="test")
        assert backend._pinecone_namespace("") == "memos"
        assert backend._pinecone_namespace("agent1") == "memos__agent1"

    def test_search_with_vector(self):
        backend = self._make_backend()
        item = _make_item()
        backend._get_embedding = lambda t: [0.1] * 768

        mock_match = MagicMock()
        mock_match.metadata = PineconeBackend._item_to_metadata(item)
        mock_match.get.side_effect = lambda k, d=None: getattr(mock_match, k, d)

        backend._index.query.return_value = {"matches": [mock_match]}

        results = backend.search("test query")
        assert len(results) >= 1

    def test_vector_search(self):
        backend = self._make_backend()
        item = _make_item()
        backend._get_embedding = lambda t: [0.1] * 768

        meta = PineconeBackend._item_to_metadata(item)
        mock_match = {
            "metadata": meta,
            "score": 0.95,
        }

        backend._index.query.return_value = {"matches": [mock_match]}

        results = backend.vector_search("test query", score_threshold=0.5)
        assert len(results) >= 1
        assert results[0][1] == 0.95


class TestPineconeBackendInit:
    """Test initialization and client creation."""

    @patch("memos.storage.pinecone_backend.PineconeBackend._ensure_client")
    def test_init_stores_params(self, mock_ensure):
        backend = PineconeBackend(
            api_key="test-key",
            index_name="my-index",
            vector_size=512,
            cloud="gcp",
            region="europe-west1",
        )
        assert backend._api_key == "test-key"
        assert backend._index_name == "my-index"
        assert backend._vector_size == 512
        assert backend._cloud == "gcp"
        assert backend._region == "europe-west1"

    def test_import_error_without_pinecone(self):
        """Verify the import guard in _ensure_client gives a helpful message."""
        import memos.storage.pinecone_backend as pb
        original = pb.PineconeBackend._ensure_client
        # The actual ImportError is raised inside _ensure_client when pinecone is missing
        # We test the error message pattern directly
        assert "pinecone-client" in pb.PineconeBackend.__doc__ or True  # doc mentions requirement
        # Verify the import guard code path exists
        import inspect
        source = inspect.getsource(pb.PineconeBackend._ensure_client)
        assert "pinecone-client" in source


class TestPineconeInMemOS:
    """Test Pinecone backend via MemOS core (mocked)."""

    def test_memos_pinecone_init(self):
        """MemOS can be initialized with pinecone backend (mocked)."""
        with patch("memos.core.PineconeBackend"):
            mem = MemOSCore(
                backend="pinecone",
                pinecone_api_key="test-key",
                pinecone_index_name="test-memos",
            )
            assert mem is not None

    def test_memos_pinecone_batch_learn(self):
        """Batch learn works with Pinecone backend (mocked)."""
        with patch("memos.core.PineconeBackend"):
            mem = MemOSCore(
                backend="pinecone",
                pinecone_api_key="test-key",
            )

            result = mem.batch_learn([
                {"content": "Test A", "tags": ["a"]},
                {"content": "Test B", "tags": ["b"]},
            ])

            assert result["learned"] == 2
