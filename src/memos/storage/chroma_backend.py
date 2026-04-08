"""ChromaDB storage backend — for production use."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

from .base import StorageBackend
from ..models import MemoryItem


class _CachedOllamaEF:
    """Chroma-compatible EmbeddingFunction that calls Ollama with a SQLite cache.

    Avoids re-embedding the same text across calls (critical on ARM64 where
    Ollama/ONNX is ~15s per embedding with no GPU).
    """

    def __init__(self, embed_host: str, embed_model: str, cache_path: str) -> None:
        self._embed_host = embed_host.rstrip("/")
        self._embed_model = embed_model
        self._cache_path = cache_path
        self._mem: dict[str, list[float]] = {}  # L1 in-process cache

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(f"{self._embed_model}::{text}".encode()).hexdigest()

    def _db(self):
        import sqlite3
        import pathlib
        pathlib.Path(self._cache_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._cache_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emb_cache (
                key TEXT PRIMARY KEY,
                vec TEXT NOT NULL,
                ts REAL NOT NULL
            )
        """)
        conn.commit()
        return conn

    def _lookup(self, text: str) -> Optional[list[float]]:
        key = self._cache_key(text)
        if key in self._mem:
            return self._mem[key]
        try:
            with self._db() as conn:
                row = conn.execute("SELECT vec FROM emb_cache WHERE key=?", (key,)).fetchone()
                if row:
                    vec = json.loads(row[0])
                    self._mem[key] = vec
                    return vec
        except Exception:
            pass
        return None

    def _store(self, text: str, vec: list[float]) -> None:
        key = self._cache_key(text)
        self._mem[key] = vec
        try:
            with self._db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO emb_cache (key, vec, ts) VALUES (?,?,?)",
                    (key, json.dumps(vec), time.time()),
                )
                conn.commit()
        except Exception:
            pass

    def _call_ollama(self, text: str) -> list[float]:
        import urllib.request
        payload = json.dumps({"model": self._embed_model, "input": text}).encode()
        req = urllib.request.Request(
            f"{self._embed_host}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise RuntimeError(f"Ollama returned no embeddings for model {self._embed_model!r}")
        return embeddings[0]

    def name(self) -> str:  # required by chromadb EmbeddingFunction protocol
        return f"memos-ollama-{self._embed_model}"

    def _embed_batch(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        results = []
        for text in input:
            cached = self._lookup(text)
            if cached is not None:
                results.append(cached)
                continue
            vec = self._call_ollama(text)
            self._store(text, vec)
            results.append(vec)
        return results

    # chromadb ≥ 0.6 API: separate embed_documents / embed_query methods
    def embed_documents(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self._embed_batch(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self._embed_batch(input)

    # Legacy / compat: some versions call __call__ directly
    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self._embed_batch(input)


class ChromaBackend(StorageBackend):
    """ChromaDB-backed storage. Requires chromadb>=0.4.

    When ``embed_host`` is provided (e.g. ``http://localhost:11434``), embeddings
    are computed client-side via Ollama and cached in a SQLite file
    (``~/.memos/chroma_emb_cache.db``). This avoids the ~15s per-query penalty
    on ARM64 machines (Raspberry Pi 5, etc.) where Chroma's built-in ONNX
    embedder runs without hardware acceleration.

    .. note::
        Switching ``embed_host`` on an existing collection changes the embedding
        dimensions (nomic-embed-text → 768 vs all-MiniLM-L6-v2 → 384). You must
        delete the Chroma volume and re-ingest data when enabling this option for
        the first time.
    """

    COLLECTION_PREFIX = "memos"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        embed_host: str = "",
        embed_model: str = "nomic-embed-text",
        embed_cache: str = "~/.memos/chroma_emb_cache.db",
    ) -> None:
        self._client = None
        self._collections: dict[str, object] = {}
        self._host = host
        self._port = port
        self._embed_host = embed_host.strip()
        self._embed_model = embed_model
        self._embed_cache = embed_cache
        self._ef: Optional[_CachedOllamaEF] = None

    def _get_ef(self) -> Optional[_CachedOllamaEF]:
        """Return a cached embedding function if embed_host is configured."""
        if not self._embed_host:
            return None
        if self._ef is None:
            import os
            cache_path = os.path.expanduser(self._embed_cache)
            self._ef = _CachedOllamaEF(self._embed_host, self._embed_model, cache_path)
        return self._ef

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
            kwargs: dict = {"name": name, "metadata": {"hnsw:space": "cosine"}}
            ef = self._get_ef()
            if ef is not None:
                kwargs["embedding_function"] = ef
            self._collections[namespace] = self._client.get_or_create_collection(**kwargs)
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
