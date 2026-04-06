"""Tests for ChromaDB backend — mocked client, no server required."""

import json
import time
import pytest
from unittest.mock import MagicMock, patch
from memos.models import MemoryItem
from memos.storage.chroma_backend import ChromaBackend


def _make_item(**overrides):
    defaults = dict(
        id="test-1",
        content="hello world",
        tags=["greeting"],
        importance=0.7,
        created_at=time.time(),
        accessed_at=time.time(),
        access_count=0,
    )
    defaults.update(overrides)
    return MemoryItem(**defaults)


def _chroma_results(ids, documents, metadatas):
    """Build a ChromaDB-style result dict."""
    return {"ids": ids, "documents": documents, "metadatas": metadatas}


class TestChromaBackend:
    """All tests mock the chromadb client — no server needed."""

    def setup_method(self):
        self.backend = ChromaBackend(host="localhost", port=8000)
        # Pre-mock the internals so we never touch the real client
        self.mock_collection = MagicMock()
        self.mock_client = MagicMock()
        self.backend._client = self.mock_client
        self.backend._collections[""] = self.mock_collection

    def _reset_collection(self):
        """Ensure the default mock collection is active."""
        self.backend._collections[""] = self.mock_collection

    # --- upsert ---
    def test_upsert_stores_item(self):
        item = _make_item()
        self.backend.upsert(item)
        self.mock_collection.upsert.assert_called_once()
        call = self.mock_collection.upsert.call_args
        assert call.kwargs["ids"] == [item.id]
        assert call.kwargs["documents"] == [item.content]

    def test_upsert_metadata_json(self):
        item = _make_item(tags=["a", "b"], importance=0.9)
        self.backend.upsert(item)
        meta = self.mock_collection.upsert.call_args.kwargs["metadatas"][0]
        assert json.loads(meta["tags"]) == ["a", "b"]
        assert meta["importance"] == 0.9

    # --- get ---
    def test_get_existing(self):
        item = _make_item()
        self.mock_collection.get.return_value = _chroma_results(
            [item.id], [item.content],
            [{"tags": json.dumps(item.tags), "importance": item.importance,
              "created_at": item.created_at, "accessed_at": item.accessed_at,
              "access_count": item.access_count}]
        )
        result = self.backend.get(item.id)
        assert result is not None
        assert result.id == item.id
        assert result.content == "hello world"

    def test_get_missing_returns_none(self):
        self.mock_collection.get.return_value = _chroma_results([], [], [])
        assert self.backend.get("nonexistent") is None

    # --- delete ---
    def test_delete_returns_true(self):
        self.backend.delete("any-id")
        self.mock_collection.delete.assert_called_once_with(ids=["any-id"])

    # --- list_all ---
    def test_list_all_empty(self):
        self.mock_collection.get.return_value = _chroma_results([], [], [])
        assert self.backend.list_all() == []

    def test_list_all_returns_items(self):
        self.mock_collection.get.return_value = _chroma_results(
            ["id1", "id2"], ["content1", "content2"],
            [
                {"tags": "[]", "importance": 0.5, "created_at": 0, "accessed_at": 0, "access_count": 0},
                {"tags": "[\"x\"]", "importance": 0.8, "created_at": 0, "accessed_at": 0, "access_count": 1},
            ]
        )
        items = self.backend.list_all()
        assert len(items) == 2
        assert items[1].tags == ["x"]
        assert items[1].access_count == 1

    # --- search ---
    def test_search_returns_results(self):
        self.mock_collection.count.return_value = 2
        self.mock_collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["docker nginx"]],
            "metadatas": [[{"tags": "[]", "importance": 0.5, "created_at": 0, "accessed_at": 0, "access_count": 0}]],
        }
        results = self.backend.search("docker", limit=5)
        assert len(results) == 1
        assert "docker" in results[0].content

    def test_search_empty_collection(self):
        self.mock_collection.count.return_value = 0
        self.mock_collection.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]]}
        assert self.backend.search("anything") == []

    # --- lazy init ---
    def test_lazy_init_on_first_upsert(self):
        mock_chroma = MagicMock()
        mock_client = MagicMock()
        mock_chroma.HttpClient.return_value = mock_client
        mock_client.get_or_create_collection.return_value = MagicMock()
        with patch.dict("sys.modules", {"chromadb": mock_chroma}):
            fresh = ChromaBackend()
            item = _make_item()
            fresh.upsert(item)
            mock_chroma.HttpClient.assert_called_once_with(host="localhost", port=8000)
            mock_client.get_or_create_collection.assert_called_once()

    def test_lazy_init_import_error(self):
        fresh = ChromaBackend()
        with patch.dict("sys.modules", {"chromadb": None}):
            with pytest.raises(ImportError, match="chromadb"):
                fresh._ensure_client()

    # --- roundtrip ---
    def test_upsert_then_get_roundtrip(self):
        item = _make_item(tags=["roundtrip"], importance=0.88, access_count=3)
        self.mock_collection.get.return_value = _chroma_results(
            [item.id], [item.content],
            [{"tags": json.dumps(item.tags), "importance": item.importance,
              "created_at": item.created_at, "accessed_at": item.accessed_at,
              "access_count": item.access_count}]
        )
        self.backend.upsert(item)
        result = self.backend.get(item.id)
        assert result.tags == ["roundtrip"]
        assert result.importance == 0.88
        assert result.access_count == 3
