"""Pinecone storage backend — serverless cloud vector storage."""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from ..models import MemoryItem
from .base import StorageBackend


class PineconeBackend(StorageBackend):
    """Pinecone-backed storage for cloud-native vector search.

    Supports Pinecone Serverless (recommended) and Pod-based indexes.
    When vector embeddings are configured, search() delegates to native
    Pinecone similarity for optimal performance.

    Requirements: pinecone-client>=3.0
    """

    INDEX_PREFIX = "memos"

    def __init__(
        self,
        api_key: str,
        *,
        environment: Optional[str] = None,
        index_name: str = "memos",
        embed_host: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
        vector_size: int = 768,
        cloud: str = "aws",
        region: str = "us-east-1",
        metric: str = "cosine",
        serverless: bool = True,
        namespace_separator: str = "__",
    ) -> None:
        self._api_key = api_key
        self._environment = environment
        self._index_name = index_name
        self._embed_host = embed_host
        self._embed_model = embed_model
        self._vector_size = vector_size
        self._cloud = cloud
        self._region = region
        self._metric = metric
        self._serverless = serverless
        self._namespace_separator = namespace_separator
        self._pc = None
        self._index = None
        self._embed_cache: dict[str, list[float]] = {}

    def _ensure_client(self):
        if self._pc is not None:
            return
        try:
            from pinecone import Pinecone
        except ImportError:
            raise ImportError(
                "pinecone-client is required for PineconeBackend. "
                "Install with: pip install memos[pinecone]"
            )
        self._pc = Pinecone(api_key=self._api_key)

    def _ensure_index(self):
        self._ensure_client()
        if self._index is not None:
            return

        existing = [idx.name for idx in self._pc.list_indexes()]
        if self._index_name not in existing:
            self._create_index()

        self._index = self._pc.Index(self._index_name)

    def _create_index(self):
        from pinecone import PodSpec, ServerlessSpec

        if self._serverless:
            spec = ServerlessSpec(cloud=self._cloud, region=self._region)
        else:
            if not self._environment:
                raise ValueError(
                    "environment is required for pod-based Pinecone indexes"
                )
            spec = PodSpec(environment=self._environment)

        self._pc.create_index(
            name=self._index_name,
            dimension=self._vector_size,
            metric=self._metric,
            spec=spec,
        )

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

    def _pinecone_namespace(self, namespace: str = "") -> str:
        if namespace:
            return f"{self.INDEX_PREFIX}{self._namespace_separator}{namespace}"
        return self.INDEX_PREFIX

    @staticmethod
    def _item_to_metadata(item: MemoryItem) -> dict:
        return {
            "_original_id": item.id,
            "content": item.content,
            "tags": json.dumps(item.tags),
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
            "metadata": json.dumps(item.metadata),
        }

    @staticmethod
    def _metadata_to_item(metadata: dict) -> MemoryItem:
        tags_raw = metadata.get("tags", "[]")
        if isinstance(tags_raw, str):
            try:
                tags = json.loads(tags_raw)
            except (json.JSONDecodeError, TypeError):
                tags = []
        elif isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = []

        metadata_raw = metadata.get("metadata", "{}")
        if isinstance(metadata_raw, str):
            try:
                item_metadata = json.loads(metadata_raw)
            except (json.JSONDecodeError, TypeError):
                item_metadata = {}
        elif isinstance(metadata_raw, dict):
            item_metadata = metadata_raw
        else:
            item_metadata = {}

        return MemoryItem(
            id=metadata.get("_original_id", ""),
            content=metadata.get("content", ""),
            tags=tags,
            importance=metadata.get("importance", 0.5),
            created_at=metadata.get("created_at", time.time()),
            accessed_at=metadata.get("accessed_at", time.time()),
            access_count=metadata.get("access_count", 0),
            metadata=item_metadata,
        )

    @staticmethod
    def _id_to_valid_id(item_id: str) -> str:
        """Convert to a Pinecone-valid ID (alphanumeric + dashes)."""
        return re.sub(r"[^a-zA-Z0-9_\-]", "-", item_id)

    # --- StorageBackend interface ---

    def upsert(self, item: MemoryItem, *, namespace: str = "") -> None:
        self._ensure_index()
        vec = self._get_embedding(item.content)
        metadata = self._item_to_metadata(item)
        pinecone_id = self._id_to_valid_id(item.id)
        ns = self._pinecone_namespace(namespace)

        self._index.upsert(
            vectors=[{
                "id": pinecone_id,
                "values": vec or [0.0] * self._vector_size,
                "metadata": metadata,
            }],
            namespace=ns,
        )

    def upsert_batch(self, items: list[MemoryItem], *, namespace: str = "") -> int:
        """Batch upsert for efficiency. Returns count of upserted items."""
        self._ensure_index()
        ns = self._pinecone_namespace(namespace)
        batch_size = 100
        count = 0

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            vectors = []
            for item in batch:
                vec = self._get_embedding(item.content)
                metadata = self._item_to_metadata(item)
                pinecone_id = self._id_to_valid_id(item.id)
                vectors.append({
                    "id": pinecone_id,
                    "values": vec or [0.0] * self._vector_size,
                    "metadata": metadata,
                })
            self._index.upsert(vectors=vectors, namespace=ns)
            count += len(batch)

        return count

    def get(self, item_id: str, *, namespace: str = "") -> Optional[MemoryItem]:
        self._ensure_index()
        pinecone_id = self._id_to_valid_id(item_id)
        ns = self._pinecone_namespace(namespace)

        try:
            result = self._index.fetch(
                ids=[pinecone_id],
                namespace=ns,
            )
            vectors = result.get("vectors", result.vectors if hasattr(result, "vectors") else {})
            if not vectors:
                return None
            vec_data = vectors.get(pinecone_id) if isinstance(vectors, dict) else None
            if vec_data is None:
                return None
            metadata = vec_data.metadata if hasattr(vec_data, "metadata") else vec_data.get("metadata", {})
            return self._metadata_to_item(metadata)
        except Exception:
            return None

    def delete(self, item_id: str, *, namespace: str = "") -> bool:
        self._ensure_index()
        pinecone_id = self._id_to_valid_id(item_id)
        ns = self._pinecone_namespace(namespace)
        try:
            self._index.delete(ids=[pinecone_id], namespace=ns)
            return True
        except Exception:
            return False

    def list_all(self, *, namespace: str = "") -> list[MemoryItem]:
        self._ensure_index()
        ns = self._pinecone_namespace(namespace)
        items = []

        try:
            for ids_page in self._index.list(namespace=ns):
                if not ids_page:
                    continue
                page_ids = list(ids_page) if not isinstance(ids_page, list) else ids_page
                if not page_ids:
                    continue

                for j in range(0, len(page_ids), 100):
                    sub = page_ids[j:j + 100]
                    result = self._index.fetch(ids=sub, namespace=ns)
                    vectors = result.get("vectors", result.vectors if hasattr(result, "vectors") else {})
                    if isinstance(vectors, dict):
                        for vec_data in vectors.values():
                            metadata = vec_data.metadata if hasattr(vec_data, "metadata") else vec_data.get("metadata", {})
                            items.append(self._metadata_to_item(metadata))
        except Exception:
            pass

        return items

    def search(self, query: str, limit: int = 20, *, namespace: str = "") -> list[MemoryItem]:
        self._ensure_index()
        ns = self._pinecone_namespace(namespace)
        vector = self._get_embedding(query)

        if vector:
            try:
                results = self._index.query(
                    vector=vector,
                    top_k=limit,
                    namespace=ns,
                    include_metadata=True,
                )
                matches = results.get("matches", results.matches if hasattr(results, "matches") else [])
                items = []
                for match in matches:
                    metadata = match.get("metadata", match.metadata if hasattr(match, "metadata") else {})
                    items.append(self._metadata_to_item(metadata))
                return items
            except Exception:
                pass

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
        self._ensure_index()
        ns = self._pinecone_namespace(namespace)
        vector = self._get_embedding(query)
        if not vector:
            return []

        try:
            results = self._index.query(
                vector=vector,
                top_k=limit,
                namespace=ns,
                include_metadata=True,
            )
            matches = results.get("matches", results.matches if hasattr(results, "matches") else [])
            output = []
            for match in matches:
                score = match.get("score", match.score if hasattr(match, "score") else 0.0)
                if score < score_threshold:
                    continue
                metadata = match.get("metadata", match.metadata if hasattr(match, "metadata") else {})
                output.append((self._metadata_to_item(metadata), score))
            return output
        except Exception:
            return []

    def list_namespaces(self) -> list[str]:
        self._ensure_index()
        prefix = f"{self.INDEX_PREFIX}{self._namespace_separator}"
        try:
            namespaces = self._index.list_namespaces()
            return sorted(
                ns[len(prefix):]
                for ns in namespaces
                if ns.startswith(prefix)
            )
        except Exception:
            return []

    def _keyword_search(
        self, query: str, limit: int, namespace: str
    ) -> list[MemoryItem]:
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
