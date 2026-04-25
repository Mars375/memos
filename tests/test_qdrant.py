"""Tests for Qdrant storage backend — mocked client, no server required."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("qdrant_client", reason="Qdrant tests require the optional qdrant extra")

from memos.models import MemoryItem
from memos.storage.qdrant_backend import QdrantBackend


def _make_item(**overrides):
    defaults = dict(
        id="test-1",
        content="hello world from docker",
        tags=["greeting", "infra"],
        importance=0.7,
        created_at=time.time(),
        accessed_at=time.time(),
        access_count=0,
        metadata={"source": "test"},
    )
    defaults.update(overrides)
    return MemoryItem(**defaults)


class FakePoint:
    """Fake Qdrant point for testing."""

    def __init__(self, point_id, payload, score=None, vector=None):
        self.id = point_id
        self.payload = payload
        self.score = score or 0.0
        self.vector = vector


class TestQdrantBackend:
    """All tests mock the qdrant_client — no server needed."""

    def setup_method(self):
        self.backend = QdrantBackend(host="localhost", port=6333)
        # Pre-mock the internals
        self.mock_client = MagicMock()
        self.backend._client = self.mock_client
        self.backend._collections["memos"] = True

    def _mock_collection_exists(self):
        """Ensure get_collection succeeds (collection exists)."""
        self.mock_client.get_collection.return_value = MagicMock()

    # --- UUID conversion ---
    def test_id_to_uuid_format(self):
        uuid_str = QdrantBackend._id_to_uuid("abc123")
        parts = uuid_str.split("-")
        assert len(parts) == 5
        assert parts[0] == "abc12300"  # padded

    def test_uuid_to_id_roundtrip(self):
        original = "a1b2c3d4e5f67890"
        uuid_str = QdrantBackend._id_to_uuid(original)
        recovered = QdrantBackend._uuid_to_id(uuid_str)
        assert recovered == original

    def test_uuid_to_id_short(self):
        original = "abc"
        uuid_str = QdrantBackend._id_to_uuid(original)
        assert "-" in uuid_str
        recovered = QdrantBackend._uuid_to_id(uuid_str)
        assert recovered.startswith("abc")

    # --- upsert ---
    def test_upsert_stores_item(self):
        item = _make_item()
        # Mock embedding to return None (no embedding service)
        self.backend._get_embedding = MagicMock(return_value=None)
        self.backend.upsert(item)
        self.mock_client.upsert.assert_called_once()
        call = self.mock_client.upsert.call_args
        assert call.kwargs["collection_name"] == "memos"
        points = call.kwargs["points"]
        assert len(points) == 1
        assert points[0].payload["content"] == item.content

    def test_upsert_with_embedding(self):
        item = _make_item()
        fake_vector = [0.1] * 768
        self.backend._get_embedding = MagicMock(return_value=fake_vector)
        self.backend.upsert(item)
        points = self.mock_client.upsert.call_args.kwargs["points"]
        assert points[0].vector == fake_vector

    def test_upsert_with_namespace(self):
        item = _make_item()
        self.backend._get_embedding = MagicMock(return_value=None)
        self.backend._collections["memos__agent1"] = True
        self.backend.upsert(item, namespace="agent1")
        call = self.mock_client.upsert.call_args
        assert call.kwargs["collection_name"] == "memos__agent1"

    def test_upsert_metadata_serialized(self):
        item = _make_item(tags=["a", "b"], importance=0.9, metadata={"key": "val"})
        self.backend._get_embedding = MagicMock(return_value=None)
        self.backend.upsert(item)
        payload = self.mock_client.upsert.call_args.kwargs["points"][0].payload
        assert json.loads(payload["tags"]) == ["a", "b"]
        assert payload["importance"] == 0.9
        assert json.loads(payload["metadata"]) == {"key": "val"}

    # --- get ---
    def test_get_existing(self):
        item = _make_item()
        point_id = QdrantBackend._id_to_uuid(item.id)
        mock_point = FakePoint(
            point_id=point_id,
            payload={
                "_original_id": item.id,
                "content": item.content,
                "tags": json.dumps(item.tags),
                "importance": item.importance,
                "created_at": item.created_at,
                "accessed_at": item.accessed_at,
                "access_count": item.access_count,
                "metadata": json.dumps(item.metadata),
            },
        )
        self.mock_client.retrieve.return_value = [mock_point]
        result = self.backend.get(item.id)
        assert result is not None
        assert result.id == item.id
        assert result.content == "hello world from docker"

    def test_get_missing_returns_none(self):
        self.mock_client.retrieve.return_value = []
        assert self.backend.get("nonexistent") is None

    def test_get_exception_returns_none(self):
        self.mock_client.retrieve.side_effect = Exception("connection error")
        assert self.backend.get("any-id") is None

    # --- delete ---
    def test_delete_returns_true(self):
        self.backend.delete("any-id")
        self.mock_client.delete.assert_called_once()

    def test_delete_exception_returns_false(self):
        self.mock_client.delete.side_effect = Exception("fail")
        assert self.backend.delete("any-id") is False

    # --- list_all ---
    def test_list_all_empty(self):
        self.mock_client.scroll.return_value = ([], None)
        assert self.backend.list_all() == []

    def test_list_all_returns_items(self):
        points = [
            FakePoint(
                "id1-0000-0000-0000-000000000000",
                {
                    "content": "content1",
                    "tags": "[]",
                    "importance": 0.5,
                    "created_at": 0,
                    "accessed_at": 0,
                    "access_count": 0,
                    "metadata": "{}",
                },
            ),
            FakePoint(
                "id2-0000-0000-0000-000000000000",
                {
                    "content": "content2",
                    "tags": '["x"]',
                    "importance": 0.8,
                    "created_at": 0,
                    "accessed_at": 0,
                    "access_count": 1,
                    "metadata": "{}",
                },
            ),
        ]
        self.mock_client.scroll.return_value = (points, None)
        items = self.backend.list_all()
        assert len(items) == 2
        assert items[1].content == "content2"
        assert items[1].tags == ["x"]

    def test_list_all_exception_returns_empty(self):
        self.mock_client.scroll.side_effect = Exception("fail")
        assert self.backend.list_all() == []

    # --- search (vector) ---
    def test_search_with_vector(self):
        fake_vector = [0.1] * 768
        self.backend._get_embedding = MagicMock(return_value=fake_vector)
        mock_point = FakePoint(
            "srch-0000-0000-0000-000000000000",
            {
                "content": "docker nginx",
                "tags": "[]",
                "importance": 0.5,
                "created_at": 0,
                "accessed_at": 0,
                "access_count": 0,
                "metadata": "{}",
            },
            score=0.92,
        )
        self.mock_client.search.return_value = [mock_point]
        results = self.backend.search("docker", limit=5)
        assert len(results) == 1
        assert "docker" in results[0].content

    def test_search_fallback_to_keyword(self):
        self.backend._get_embedding = MagicMock(return_value=None)
        # list_all returns items for keyword fallback
        points = [
            FakePoint(
                "key1-0000-0000-0000-000000000000",
                {
                    "content": "docker nginx config",
                    "tags": "[]",
                    "importance": 0.5,
                    "created_at": 0,
                    "accessed_at": 0,
                    "access_count": 0,
                    "metadata": "{}",
                },
            ),
        ]
        self.mock_client.scroll.return_value = (points, None)
        results = self.backend.search("docker", limit=5)
        assert len(results) == 1
        assert "docker" in results[0].content

    def test_search_empty_collection(self):
        self.backend._get_embedding = MagicMock(return_value=None)
        self.mock_client.scroll.return_value = ([], None)
        assert self.backend.search("anything") == []

    # --- vector_search ---
    def test_vector_search_returns_scored(self):
        fake_vector = [0.1] * 768
        self.backend._get_embedding = MagicMock(return_value=fake_vector)
        mock_point = FakePoint(
            "v1-000-0000-0000-000000000000",
            {
                "content": "test content",
                "tags": "[]",
                "importance": 0.5,
                "created_at": 0,
                "accessed_at": 0,
                "access_count": 0,
                "metadata": "{}",
            },
            score=0.88,
        )
        self.mock_client.search.return_value = [mock_point]
        results = self.backend.vector_search("test", limit=5)
        assert len(results) == 1
        item, score = results[0]
        assert isinstance(item, MemoryItem)
        assert score == 0.88

    def test_vector_search_no_embedding_returns_empty(self):
        self.backend._get_embedding = MagicMock(return_value=None)
        assert self.backend.vector_search("test") == []

    # --- hybrid_search ---
    def test_hybrid_search_combines_scores(self):
        fake_vector = [0.1] * 768
        self.backend._get_embedding = MagicMock(return_value=fake_vector)

        # Vector search result
        mock_point = FakePoint(
            "h1-00-0000-0000-000000000000",
            {
                "content": "docker compose setup",
                "tags": "[]",
                "importance": 0.5,
                "created_at": 0,
                "accessed_at": 0,
                "access_count": 0,
                "metadata": "{}",
            },
            score=0.9,
        )
        self.mock_client.search.return_value = [mock_point]

        # list_all for keyword scoring
        self.mock_client.scroll.return_value = (
            [
                FakePoint(
                    "h1-00-0000-0000-000000000000",
                    {
                        "content": "docker compose setup",
                        "tags": "[]",
                        "importance": 0.5,
                        "created_at": 0,
                        "accessed_at": 0,
                        "access_count": 0,
                        "metadata": "{}",
                    },
                )
            ],
            None,
        )

        results = self.backend.hybrid_search("docker", limit=5)
        assert len(results) >= 1
        item, score = results[0]
        assert "docker" in item.content
        # Combined score should include vector + keyword components
        assert score > 0

    def test_hybrid_search_keyword_only(self):
        self.backend._get_embedding = MagicMock(return_value=None)
        self.mock_client.scroll.return_value = (
            [
                FakePoint(
                    "kw1-000-0000-0000-000000000000",
                    {
                        "content": "python web server",
                        "tags": '["dev"]',
                        "importance": 0.6,
                        "created_at": 0,
                        "accessed_at": 0,
                        "access_count": 0,
                        "metadata": "{}",
                    },
                )
            ],
            None,
        )
        results = self.backend.hybrid_search("python", limit=5)
        assert len(results) == 1
        item, score = results[0]
        assert "python" in item.content
        assert score > 0

    def test_hybrid_search_avoids_scroll_when_vector_candidates_exist(self):
        fake_vector = [0.1] * 768
        self.backend._get_embedding = MagicMock(return_value=fake_vector)
        mock_point = FakePoint(
            "h2-00-0000-0000-000000000000",
            {
                "content": "docker compose setup",
                "tags": json.dumps(["infra"]),
                "importance": 0.5,
                "created_at": 0,
                "accessed_at": 0,
                "access_count": 0,
                "metadata": "{}",
            },
            score=0.9,
        )
        self.mock_client.search.return_value = [mock_point]

        results = self.backend.hybrid_search("docker", limit=5)

        assert len(results) == 1
        self.mock_client.scroll.assert_not_called()

    # --- list_namespaces ---
    def test_list_namespaces(self):
        mock_col = MagicMock()
        mock_col.name = "memos__agent1"
        self.mock_client.get_collections.return_value = MagicMock(collections=[mock_col])
        ns = self.backend.list_namespaces()
        assert ns == ["agent1"]

    def test_list_namespaces_empty(self):
        self.mock_client.get_collections.return_value = MagicMock(collections=[])
        assert self.backend.list_namespaces() == []

    # --- _point_to_item ---
    def test_point_to_item_handles_dict_tags(self):
        point = FakePoint(
            "abcd-1234-5678-ef01-234567890abc",
            {
                "content": "test",
                "tags": ["a", "b"],
                "importance": 0.5,
                "created_at": 1000,
                "accessed_at": 2000,
                "access_count": 3,
                "metadata": {"custom": "val"},
            },
        )
        item = QdrantBackend._point_to_item(point)
        assert item.tags == ["a", "b"]
        assert item.metadata == {"custom": "val"}
        assert item.access_count == 3

    def test_point_to_item_handles_bad_metadata(self):
        point = FakePoint(
            "abcd-0000-0000-0000-000000000000",
            {
                "content": "test",
                "tags": "invalid-json{{{",
                "importance": 0.5,
                "created_at": 0,
                "accessed_at": 0,
                "access_count": 0,
                "metadata": "also-bad{{{}}",
            },
        )
        item = QdrantBackend._point_to_item(point)
        assert item.tags == []
        assert item.metadata == {}

    # --- lazy init ---
    def test_lazy_init_remote(self):
        mock_qdrant = MagicMock()
        mock_client_instance = MagicMock()
        mock_qdrant.QdrantClient.return_value = mock_client_instance
        mock_client_instance.get_collection.side_effect = Exception("not found")
        mock_client_instance.create_collection.return_value = None

        with patch.dict("sys.modules", {"qdrant_client": mock_qdrant}):
            fresh = QdrantBackend(host="remote-host", port=6333)
            fresh._client = None
            fresh._collections = {}
            fresh._ensure_client()
            mock_qdrant.QdrantClient.assert_called_once()

    def test_lazy_init_local_path(self, tmp_path):
        qdrant_data_path = str(tmp_path / "qdrant_data")
        mock_qdrant = MagicMock()
        mock_client_instance = MagicMock()
        mock_qdrant.QdrantClient.return_value = mock_client_instance

        with patch.dict("sys.modules", {"qdrant_client": mock_qdrant}):
            fresh = QdrantBackend(path=qdrant_data_path)
            fresh._client = None
            fresh._collections = {}
            fresh._ensure_client()
            mock_qdrant.QdrantClient.assert_called_once_with(path=qdrant_data_path)

    def test_lazy_init_import_error(self):
        fresh = QdrantBackend()
        with patch.dict("sys.modules", {"qdrant_client": None}):
            with pytest.raises(ImportError, match="qdrant-client"):
                fresh._ensure_client()

    # --- roundtrip ---
    def test_upsert_then_get_roundtrip(self):
        item = _make_item(
            tags=["roundtrip"],
            importance=0.88,
            access_count=3,
            metadata={"env": "production"},
        )
        self.backend._get_embedding = MagicMock(return_value=None)

        # Capture what was upserted
        upserted_payload = None
        upserted_id = None

        def capture_upsert(**kwargs):
            nonlocal upserted_payload, upserted_id
            pts = kwargs["points"]
            upserted_payload = pts[0].payload
            upserted_id = pts[0].id

        self.mock_client.upsert.side_effect = capture_upsert
        self.backend.upsert(item)

        # Mock retrieve to return the same data
        mock_point = FakePoint(
            upserted_id,
            upserted_payload,
        )
        self.mock_client.retrieve.return_value = [mock_point]

        result = self.backend.get(item.id)
        assert result is not None
        assert result.tags == ["roundtrip"]
        assert result.importance == 0.88
        assert result.access_count == 3
        assert result.metadata == {"env": "production"}


class TestQdrantIdConversion:
    """Dedicated tests for ID/UUID conversion edge cases."""

    def test_short_id_padding(self):
        uuid_str = QdrantBackend._id_to_uuid("ab")
        # Should be padded to 32 hex chars
        clean = uuid_str.replace("-", "")
        assert len(clean) == 32
        assert clean.startswith("ab")

    def test_exact_16_char_id(self):
        original = "0123456789abcdef"
        uuid_str = QdrantBackend._id_to_uuid(original)
        recovered = QdrantBackend._uuid_to_id(uuid_str)
        assert recovered == original

    def test_long_id_truncated(self):
        original = "a" * 64
        uuid_str = QdrantBackend._id_to_uuid(original)
        clean = uuid_str.replace("-", "")
        assert len(clean) == 32

    def test_hex_format_valid(self):
        uuid_str = QdrantBackend._id_to_uuid("abc123")
        # UUID format: 8-4-4-4-12
        parts = uuid_str.split("-")
        assert [len(p) for p in parts] == [8, 4, 4, 4, 12]


class TestQdrantKeywordSearch:
    """Tests for the _keyword_search fallback."""

    def setup_method(self):
        self.backend = QdrantBackend(host="localhost", port=6333)
        self.mock_client = MagicMock()
        self.backend._client = self.mock_client
        self.backend._collections["memos"] = True

    def test_keyword_matches_content(self):
        items = [
            FakePoint(
                "k1-00-0000-0000-000000000000",
                {
                    "content": "docker nginx config",
                    "tags": "[]",
                    "importance": 0.5,
                    "created_at": 0,
                    "accessed_at": 0,
                    "access_count": 0,
                    "metadata": "{}",
                },
            ),
            FakePoint(
                "k2-00-0000-0000-000000000000",
                {
                    "content": "python flask app",
                    "tags": "[]",
                    "importance": 0.5,
                    "created_at": 0,
                    "accessed_at": 0,
                    "access_count": 0,
                    "metadata": "{}",
                },
            ),
        ]
        self.mock_client.scroll.return_value = (items, None)
        results = self.backend._keyword_search("docker", limit=10, namespace="")
        assert len(results) == 1
        assert "docker" in results[0].content

    def test_keyword_matches_tags(self):
        items = [
            FakePoint(
                "t1-00-0000-0000-000000000000",
                {
                    "content": "some content",
                    "tags": '["docker"]',
                    "importance": 0.5,
                    "created_at": 0,
                    "accessed_at": 0,
                    "access_count": 0,
                    "metadata": "{}",
                },
            ),
        ]
        self.mock_client.scroll.return_value = (items, None)
        results = self.backend._keyword_search("docker", limit=10, namespace="")
        assert len(results) == 1

    def test_keyword_respects_limit(self):
        items = [
            FakePoint(
                f"l{i}-00-0000-0000-000000000000",
                {
                    "content": f"docker item {i}",
                    "tags": "[]",
                    "importance": 0.5,
                    "created_at": 0,
                    "accessed_at": 0,
                    "access_count": 0,
                    "metadata": "{}",
                },
            )
            for i in range(10)
        ]
        self.mock_client.scroll.return_value = (items, None)
        results = self.backend._keyword_search("docker", limit=3, namespace="")
        assert len(results) == 3
