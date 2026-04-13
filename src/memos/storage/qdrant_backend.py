"""Qdrant storage backend — production-grade vector + payload storage."""

from __future__ import annotations

import json
import time
from typing import Optional

from ..models import MemoryItem
from .base import StorageBackend


class QdrantBackend(StorageBackend):
    """Qdrant-backed storage with native vector search support.

    Supports both local (in-memory / file-based) and remote Qdrant instances.
    When connected to a Qdrant server with vector embeddings configured,
    search() delegates to native vector similarity for better performance.

    Requirements: qdrant-client>=1.7
    """

    COLLECTION_PREFIX = "memos"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        *,
        api_key: Optional[str] = None,
        path: Optional[str] = None,
        prefer_grpc: bool = False,
        embed_host: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
        vector_size: int = 768,
    ) -> None:
        self._client = None
        self._collections: dict[str, bool] = {}
        self._host = host
        self._port = port
        self._api_key = api_key
        self._path = path
        self._prefer_grpc = prefer_grpc
        self._embed_host = embed_host
        self._embed_model = embed_model
        self._vector_size = vector_size
        self._embed_cache: dict[str, list[float]] = {}

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            from qdrant_client import QdrantClient
        except ImportError:
            raise ImportError("qdrant-client is required for QdrantBackend. Install with: pip install memos[qdrant]")

        if self._path:
            self._client = QdrantClient(path=self._path)
        else:
            kwargs: dict = {
                "host": self._host,
                "port": self._port,
                "prefer_grpc": self._prefer_grpc,
            }
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = QdrantClient(**kwargs)

    def _collection_name(self, namespace: str = "") -> str:
        if namespace:
            return f"{self.COLLECTION_PREFIX}__{namespace}"
        return self.COLLECTION_PREFIX

    def _ensure_collection(self, namespace: str = ""):
        self._ensure_client()
        from qdrant_client.models import Distance, VectorParams

        name = self._collection_name(namespace)
        if name not in self._collections:
            try:
                self._client.get_collection(name)
            except Exception:
                self._client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=self._vector_size,
                        distance=Distance.COSINE,
                    ),
                )
            self._collections[name] = True

    def _get_embedding(self, text: str) -> Optional[list[float]]:
        if text in self._embed_cache:
            return self._embed_cache[text]
        try:
            import httpx

            resp = httpx.post(
                f"{self._embed_host}/api/embed",
                json={"model": self._embed_model, "input": text},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings and embeddings[0]:
                vec = embeddings[0]
                self._embed_cache[text] = vec
                if len(self._embed_cache) > 5000:
                    keys = list(self._embed_cache.keys())[:2500]
                    for k in keys:
                        del self._embed_cache[k]
                return vec
        except Exception:
            pass
        return None

    # --- StorageBackend interface ---

    def upsert(self, item: MemoryItem, *, namespace: str = "") -> None:
        self._ensure_collection(namespace)
        from qdrant_client.models import PointStruct

        name = self._collection_name(namespace)
        payload = {
            "_original_id": item.id,
            "content": item.content,
            "tags": json.dumps(item.tags),
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
            "metadata": json.dumps(item.metadata),
        }

        vector = self._get_embedding(item.content)
        point_id = self._id_to_uuid(item.id)

        point = PointStruct(
            id=point_id,
            vector=vector or [],
            payload=payload,
        )
        self._client.upsert(collection_name=name, points=[point])

    def get(self, item_id: str, *, namespace: str = "") -> Optional[MemoryItem]:
        self._ensure_collection(namespace)
        name = self._collection_name(namespace)
        point_id = self._id_to_uuid(item_id)
        try:
            points = self._client.retrieve(
                collection_name=name,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                return None
            return self._point_to_item(points[0])
        except Exception:
            return None

    def delete(self, item_id: str, *, namespace: str = "") -> bool:
        self._ensure_collection(namespace)
        name = self._collection_name(namespace)
        point_id = self._id_to_uuid(item_id)
        from qdrant_client.models import PointIdsList

        try:
            self._client.delete(
                collection_name=name,
                points_selector=PointIdsList(points=[point_id]),
            )
            return True
        except Exception:
            return False

    def list_all(self, *, namespace: str = "") -> list[MemoryItem]:
        self._ensure_collection(namespace)
        name = self._collection_name(namespace)
        try:
            points, _ = self._client.scroll(
                collection_name=name,
                limit=10_000,
                with_payload=True,
                with_vectors=False,
            )
            return [self._point_to_item(p) for p in points]
        except Exception:
            return []

    def search(self, query: str, limit: int = 20, *, namespace: str = "") -> list[MemoryItem]:
        self._ensure_collection(namespace)
        name = self._collection_name(namespace)

        # Try vector search first
        vector = self._get_embedding(query)
        if vector:
            try:
                results = self._client.search(
                    collection_name=name,
                    query_vector=vector,
                    limit=limit,
                    with_payload=True,
                )
                return [self._point_to_item(r) for r in results]
            except Exception:
                pass

        # Fallback: keyword-based search
        return self._keyword_search(query, limit, namespace)

    def vector_search(
        self,
        query: str,
        limit: int = 20,
        *,
        namespace: str = "",
        score_threshold: float = 0.0,
    ) -> list[tuple[MemoryItem, float]]:
        """Native vector similarity search. Returns (item, score) pairs."""
        self._ensure_collection(namespace)
        name = self._collection_name(namespace)
        vector = self._get_embedding(query)
        if not vector:
            return []

        try:
            results = self._client.search(
                collection_name=name,
                query_vector=vector,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            return [(self._point_to_item(r), r.score) for r in results]
        except Exception:
            return []

    def hybrid_search(
        self,
        query: str,
        limit: int = 20,
        *,
        namespace: str = "",
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> list[tuple[MemoryItem, float]]:
        """Hybrid search combining vector similarity and BM25 keyword scoring.

        Returns (item, combined_score) pairs sorted by combined score.
        """
        # Vector results
        vector_results: dict[str, float] = {}
        vector = self._get_embedding(query)
        if vector:
            try:
                name = self._collection_name(namespace)
                results = self._client.search(
                    collection_name=name,
                    query_vector=vector,
                    limit=limit * 3,  # Overfetch for re-ranking
                    with_payload=True,
                )
                for r in results:
                    item = self._point_to_item(r)
                    vector_results[item.id] = r.score
            except Exception:
                pass

        # Keyword results (BM25-like)
        all_items = self.list_all(namespace=namespace)
        keyword_scores: dict[str, float] = {}
        import math
        import re

        query_tokens = set(re.findall(r"\w+", query.lower()))
        for item in all_items:
            content_tokens = set(re.findall(r"\w+", item.content.lower()))
            if not query_tokens or not content_tokens:
                continue
            overlap = query_tokens & content_tokens
            if overlap:
                tf = len(overlap) / max(len(content_tokens), 1)
                idf = math.log(1 + 1 / max(len(query_tokens) - len(overlap) + 1, 1))
                keyword_scores[item.id] = tf * idf

        # Combine scores
        all_ids = set(vector_results.keys()) | set(keyword_scores.keys())
        combined: list[tuple[MemoryItem, float]] = []
        item_map = {item.id: item for item in all_items}

        for item_id in all_ids:
            v_score = vector_results.get(item_id, 0.0)
            k_score = keyword_scores.get(item_id, 0.0)
            combined_score = vector_weight * v_score + keyword_weight * k_score
            if item_id in item_map:
                combined.append((item_map[item_id], combined_score))

        combined.sort(key=lambda x: x[1], reverse=True)
        return combined[:limit]

    def list_namespaces(self) -> list[str]:
        self._ensure_client()
        prefix = f"{self.COLLECTION_PREFIX}__"
        try:
            collections = self._client.get_collections().collections
            return sorted(c.name[len(prefix) :] for c in collections if c.name.startswith(prefix))
        except Exception:
            return []

    # --- Internal helpers ---

    def _keyword_search(self, query: str, limit: int, namespace: str) -> list[MemoryItem]:
        """Simple keyword fallback when vector search is unavailable."""
        all_items = self.list_all(namespace=namespace)
        q = query.lower()
        results = []
        for item in all_items:
            if q in item.content.lower():
                results.append(item)
            elif any(q in tag.lower() for tag in item.tags):
                results.append(item)
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _id_to_uuid(item_id: str) -> str:
        """Convert a short hex ID to a valid UUID string."""
        # Pad to 32 hex chars if needed
        padded = item_id.ljust(32, "0")[:32]
        return f"{padded[:8]}-{padded[8:12]}-{padded[12:16]}-{padded[16:20]}-{padded[20:]}"

    @staticmethod
    def _uuid_to_id(uuid_str: str) -> str:
        """Convert a UUID string back to the original hex ID."""
        return uuid_str.replace("-", "")[:16]

    @staticmethod
    def _point_to_item(point) -> MemoryItem:
        """Convert a Qdrant point to a MemoryItem."""
        payload = point.payload or {}
        point_id = str(point.id)

        # Prefer stored original ID over UUID roundtrip
        raw_id = payload.get("_original_id")
        if not raw_id:
            try:
                raw_id = QdrantBackend._uuid_to_id(point_id)
            except Exception:
                raw_id = point_id[:16]

        metadata_raw = payload.get("metadata", "{}")
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        elif isinstance(metadata_raw, dict):
            metadata = metadata_raw
        else:
            metadata = {}

        tags_raw = payload.get("tags", "[]")
        if isinstance(tags_raw, str):
            try:
                tags = json.loads(tags_raw)
            except (json.JSONDecodeError, TypeError):
                tags = []
        elif isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = []

        return MemoryItem(
            id=raw_id,
            content=payload.get("content", ""),
            tags=tags,
            importance=payload.get("importance", 0.5),
            created_at=payload.get("created_at", time.time()),
            accessed_at=payload.get("accessed_at", time.time()),
            access_count=payload.get("access_count", 0),
            metadata=metadata,
        )
