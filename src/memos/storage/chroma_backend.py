"""ChromaDB storage backend — for production use."""

from __future__ import annotations

import json
import time
from typing import Optional

from .base import StorageBackend
from ..models import MemoryItem


class ChromaBackend(StorageBackend):
    """ChromaDB-backed storage. Requires chromadb>=0.4."""

    COLLECTION_PREFIX = "memos"

    def __init__(self, host: str = "localhost", port: int = 8000) -> None:
        self._client = None
        self._collections: dict[str, object] = {}
        self._host = host
        self._port = port

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "chromadb is required for ChromaBackend. "
                "Install with: pip install memos[chroma]"
            )
        self._client = chromadb.HttpClient(host=self._host, port=self._port)

    def _collection_for(self, namespace: str = ""):
        self._ensure_client()
        if namespace not in self._collections:
            name = f"{self.COLLECTION_PREFIX}__{namespace}" if namespace else self.COLLECTION_PREFIX
            self._collections[namespace] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[namespace]

    def upsert(self, item: MemoryItem, *, namespace: str = "") -> None:
        col = self._collection_for(namespace)
        metadata = {
            "tags": json.dumps(item.tags),
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
        }
        col.upsert(ids=[item.id], documents=[item.content], metadatas=[metadata])

    def get(self, item_id: str, *, namespace: str = "") -> Optional[MemoryItem]:
        col = self._collection_for(namespace)
        results = col.get(ids=[item_id])
        if not results["ids"]:
            return None
        return self._doc_to_item(results, 0)

    def delete(self, item_id: str, *, namespace: str = "") -> bool:
        col = self._collection_for(namespace)
        col.delete(ids=[item_id])
        return True

    def list_all(self, *, namespace: str = "") -> list[MemoryItem]:
        col = self._collection_for(namespace)
        results = col.get()
        return [self._doc_to_item(results, i) for i in range(len(results["ids"]))]

    def search(self, query: str, limit: int = 20, *, namespace: str = "") -> list[MemoryItem]:
        col = self._collection_for(namespace)
        n = col.count()
        if n == 0:
            return []
        results = col.query(query_texts=[query], n_results=min(limit, n))
        if not results["ids"]:
            return []
        return [self._doc_to_item(results, 0, i) for i in range(len(results["ids"][0]))]

    def list_namespaces(self) -> list[str]:
        self._ensure_client()
        prefix = f"{self.COLLECTION_PREFIX}__"
        return sorted(
            c.name[len(prefix):]
            for c in self._client.list_collections()
            if c.name.startswith(prefix)
        )

    @staticmethod
    def _doc_to_item(results, idx: int, doc_idx: int = 0) -> MemoryItem:
        raw_meta = results["metadatas"]
        if raw_meta and isinstance(raw_meta[0], list):
            # query() returns nested lists
            meta = raw_meta[doc_idx][idx]
            doc_id = results["ids"][doc_idx][idx]
            content = results["documents"][doc_idx][idx]
        elif raw_meta:
            # get() returns flat lists
            meta = raw_meta[idx]
            doc_id = results["ids"][idx]
            content = results["documents"][idx]
        else:
            meta = {}
            doc_id = results["ids"][idx]
            content = results["documents"][idx]
        return MemoryItem(
            id=doc_id,
            content=content,
            tags=json.loads(meta.get("tags", "[]")),
            importance=meta.get("importance", 0.5),
            created_at=meta.get("created_at", time.time()),
            accessed_at=meta.get("accessed_at", time.time()),
            access_count=meta.get("access_count", 0),
        )
