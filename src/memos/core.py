"""Core MemOS client — the main entry point."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from ._compounding_facade import CompoundingFacade
from ._constants import (
    DEFAULT_ANALYTICS_RETENTION_DAYS,
    DEFAULT_CACHE_MAX_SIZE,
    DEFAULT_DECAY_RATE,
    DEFAULT_DEDUP_THRESHOLD,
    DEFAULT_EMBED_TIMEOUT,
    DEFAULT_MAX_MEMORIES,
    DEFAULT_MAX_VERSIONS_PER_ITEM,
    DEFAULT_SEMANTIC_WEIGHT,
    DEFAULT_VECTOR_SIZE,
)
from ._dedup_facade import DedupFacade
from ._feedback_facade import FeedbackFacade
from ._ingest_facade import IngestFacade
from ._io_facade import IOFacade
from ._kg_facade import KGFacade
from ._maintenance_facade import MaintenanceFacade
from ._memory_facade import MemoryCrudFacade
from ._namespace_facade import NamespaceFacade, acl_sidecar_path
from ._runtime_facade import RuntimeFacade
from ._sharing_facade import SharingFacade
from ._tag_facade import TagFacade
from ._versioning_facade import VersioningFacade
from .analytics import RecallAnalytics
from .cache.embedding_cache import EmbeddingCache
from .crypto import MemoryCrypto
from .decay.engine import DecayEngine
from .dedup import DedupEngine
from .events import EventBus
from .models import MemoryItem, MemoryStats, RecallResult
from .namespaces.acl import NamespaceACL
from .retrieval.engine import RetrievalEngine
from .sharing.engine import SharingEngine
from .storage.base import StorageBackend
from .storage.encrypted_backend import EncryptedStorageBackend
from .storage.json_backend import JsonFileBackend
from .storage.memory_backend import InMemoryBackend
from .versioning.engine import VersioningEngine

__all__ = ["MemOS", "MemoryItem", "MemoryStats", "RecallResult", "time"]


class MemOS(
    RuntimeFacade,
    KGFacade,
    CompoundingFacade,
    IOFacade,
    VersioningFacade,
    SharingFacade,
    FeedbackFacade,
    MaintenanceFacade,
    MemoryCrudFacade,
    DedupFacade,
    IngestFacade,
    TagFacade,
    NamespaceFacade,
):
    """Memory Operating System for LLM Agents.

    Usage:
        mem = MemOS(backend="memory")
        mem.learn("User prefers concise responses", tags=["preference"])
        results = mem.recall("how should I respond?")
        mem.prune(threshold=0.3)
    """

    def __init__(
        self,
        backend: str = "memory",
        *,
        persist_path: Optional[str] = None,
        embed_host: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
        chroma_host: str = "localhost",
        chroma_port: int = 8000,
        sanitize: bool = True,
        decay_rate: float = DEFAULT_DECAY_RATE,
        max_memories: int = DEFAULT_MAX_MEMORIES,
        encryption_key: Optional[str] = None,
        **kwargs,
    ) -> None:
        self._backend_name = backend
        acl_persist_path = kwargs.get("acl_path")
        if acl_persist_path:
            acl_persist_path = os.path.expanduser(acl_persist_path)
        # Storage
        if backend == "chroma":
            from .storage.chroma_backend import ChromaBackend

            # Only enable client-side Ollama embeddings when MEMOS_EMBED_HOST is
            # explicitly configured. When unset, Chroma uses its built-in ONNX
            # embedder (backward compatible with existing collections).
            _chroma_embed_host = os.environ.get("MEMOS_EMBED_HOST", "")
            store: StorageBackend = ChromaBackend(
                host=chroma_host,
                port=chroma_port,
                embed_host=_chroma_embed_host,
                embed_model=embed_model,
            )
        elif backend == "qdrant":
            from .storage.qdrant_backend import QdrantBackend

            store = QdrantBackend(
                host=kwargs.get("qdrant_host", "localhost"),
                port=kwargs.get("qdrant_port", 6333),
                api_key=kwargs.get("qdrant_api_key"),
                path=kwargs.get("qdrant_path"),
                embed_host=embed_host,
                embed_model=embed_model,
                vector_size=kwargs.get("vector_size", DEFAULT_VECTOR_SIZE),
            )
        elif backend == "pinecone":
            from .storage.pinecone_backend import PineconeBackend

            store = PineconeBackend(
                api_key=kwargs.get("pinecone_api_key", ""),
                environment=kwargs.get("pinecone_environment"),
                index_name=kwargs.get("pinecone_index_name", "memos"),
                embed_host=embed_host,
                embed_model=embed_model,
                vector_size=kwargs.get("vector_size", DEFAULT_VECTOR_SIZE),
                cloud=kwargs.get("pinecone_cloud", "aws"),
                region=kwargs.get("pinecone_region", "us-east-1"),
                serverless=kwargs.get("pinecone_serverless", True),
            )
        elif backend == "json":
            p = os.path.expanduser(persist_path or ".memos/store.json")
            acl_persist_path = acl_persist_path or acl_sidecar_path(p)
            store = JsonFileBackend(path=p)
        elif backend == "local":
            # Local-first: JSON storage + built-in sentence-transformers embeddings
            # No external services needed for semantic recall.
            p = os.path.expanduser(persist_path or ".memos/store.json")
            acl_persist_path = acl_persist_path or acl_sidecar_path(p)
            store = JsonFileBackend(path=p)
        else:
            if persist_path:
                p = os.path.expanduser(persist_path)
                acl_persist_path = acl_persist_path or acl_sidecar_path(p)
                store = JsonFileBackend(path=p)
            else:
                store = InMemoryBackend()

        # Encryption wrapper
        if encryption_key:
            crypto = MemoryCrypto.from_passphrase(encryption_key)
            self._store = EncryptedStorageBackend(store, crypto)
        else:
            self._store = store

        # Retrieval
        retrieval_embedder = None
        retrieval_model = embed_model
        _use_local = backend == "local" or embed_model == "local"
        if _use_local:
            local_model = kwargs.get("local_model") or "all-MiniLM-L6-v2"
            from .embeddings import LocalEmbedder

            retrieval_embedder = LocalEmbedder(
                model=local_model,
                device=kwargs.get("local_device"),
                normalize=kwargs.get("local_normalize", True),
            )
            retrieval_model = local_model

        self._retrieval = RetrievalEngine(
            store=self._store,
            embed_host=embed_host,
            embed_model=retrieval_model,
            semantic_weight=kwargs.get("semantic_weight", DEFAULT_SEMANTIC_WEIGHT),
            embedder=retrieval_embedder,
            embed_timeout=kwargs.get("embed_timeout", DEFAULT_EMBED_TIMEOUT),
        )

        # Decay
        self._decay = DecayEngine(
            rate=decay_rate,
            max_memories=max_memories,
        )

        # Sanitizer
        self._sanitize = sanitize

        # Namespace (multi-agent isolation)
        self._namespace: str = ""
        self._agent_id: str = ""

        # Namespace ACL (access control)
        self._acl = NamespaceACL()
        self._persist_path: str | None = getattr(store, "_path", None) and str(getattr(store, "_path"))
        self._acl_path: str | None = acl_persist_path
        self._acl.set_on_change(self._save_acl_policies)
        self._load_acl_policies()

        # Event bus (real-time subscriptions)
        self._events = EventBus()

        # Versioning (time-travel)
        self._versioning = VersioningEngine(
            max_versions_per_item=kwargs.get("max_versions_per_item", DEFAULT_MAX_VERSIONS_PER_ITEM),
            persistent_path=kwargs.get("versioning_path"),
        )

        # Embedding cache (persistent disk-backed)
        # Enabled by default — avoids re-calling Ollama for the same text across
        # requests and restarts. Stored in ~/.memos/embeddings.db (persistent volume).
        cache_enabled = kwargs.get("cache_enabled", True)
        if cache_enabled:
            self._embedding_cache = EmbeddingCache(
                path=kwargs.get("cache_path", "~/.memos/embeddings.db"),
                max_size=kwargs.get("cache_max_size", DEFAULT_CACHE_MAX_SIZE),
                ttl_seconds=kwargs.get("cache_ttl", 0),
            )
            self._retrieval.set_cache(self._embedding_cache)
        else:
            self._embedding_cache = None

        # Sharing engine (multi-agent memory exchange)
        self._sharing = SharingEngine()

        # Recall analytics (query patterns, latency, success rate)
        self._analytics = RecallAnalytics(
            path=kwargs.get("analytics_path"),
            enabled=kwargs.get("analytics_enabled", True),
            retention_days=kwargs.get("analytics_retention_days", DEFAULT_ANALYTICS_RETENTION_DAYS),
        )

        # Dedup engine (prevent duplicate memories at write time)
        self._dedup_enabled: bool = kwargs.get("dedup_enabled", True)
        self._dedup_threshold: float = kwargs.get("dedup_threshold", DEFAULT_DEDUP_THRESHOLD)
        self._dedup_engine: Optional[DedupEngine] = None
        # Feedback is stored in memory item metadata["_feedback"] for persistence

        # Compounding ingest (P8) — auto-update wiki pages on every learn()
        self._living_wiki: Optional[Any] = None
        self._wiki_auto_update: bool = False
        self._kg_instance: Any | None = None
        self._kg_bridge_instance: Any | None = None
