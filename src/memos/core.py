"""Core MemOS client — the main entry point."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from ._constants import (
    DEFAULT_ANALYTICS_RETENTION_DAYS,
    DEFAULT_CACHE_MAX_SIZE,
    DEFAULT_DECAY_RATE,
    DEFAULT_DEDUP_THRESHOLD,
    DEFAULT_EMBED_TIMEOUT,
    DEFAULT_IMPORTANCE,
    DEFAULT_MAX_CHUNK_SIZE,
    DEFAULT_MAX_MEMORIES,
    DEFAULT_MAX_VERSIONS_PER_ITEM,
    DEFAULT_SEMANTIC_WEIGHT,
    DEFAULT_VECTOR_SIZE,
    IMPORTANCE_EQUALITY_TOLERANCE,
    SECONDS_PER_DAY,
    STATS_DECAY_THRESHOLD,
)
from ._feedback_facade import FeedbackFacade
from ._io_facade import IOFacade
from ._maintenance_facade import MaintenanceFacade
from ._sharing_facade import SharingFacade
from ._versioning_facade import VersioningFacade
from .analytics import RecallAnalytics
from .cache.embedding_cache import EmbeddingCache
from .crypto import MemoryCrypto
from .decay.engine import DecayEngine
from .dedup import DedupCheckResult, DedupEngine, DedupScanResult
from .events import EventBus
from .ingest.engine import IngestResult
from .models import MemoryItem, MemoryStats, RecallResult, generate_id
from .namespaces.acl import NamespaceACL, Role
from .query import MemoryQuery, QueryEngine
from .retrieval.engine import RetrievalEngine
from .sanitizer import MemorySanitizer
from .sharing.engine import SharingEngine
from .storage.base import StorageBackend
from .storage.encrypted_backend import EncryptedStorageBackend
from .storage.json_backend import JsonFileBackend
from .storage.memory_backend import InMemoryBackend
from .tagger import AutoTagger
from .versioning.engine import VersioningEngine

logger = logging.getLogger(__name__)


class MemOS(IOFacade, VersioningFacade, SharingFacade, FeedbackFacade, MaintenanceFacade):
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
            p = persist_path or ".memos/store.json"
            store = JsonFileBackend(path=p)
        elif backend == "local":
            # Local-first: JSON storage + built-in sentence-transformers embeddings
            # No external services needed for semantic recall.
            p = persist_path or ".memos/store.json"
            store = JsonFileBackend(path=p)
        else:
            if persist_path:
                store = JsonFileBackend(path=persist_path)
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

        # Namespace ACL (access control)
        self._acl = NamespaceACL()

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
        self._compounding_ingest: bool = False
        self._compounding_wiki: Optional[Any] = None
        self._living_wiki: Optional[Any] = None
        self._wiki_auto_update: bool = False
        self._kg_instance: Any | None = None
        self._kg_bridge_instance: Any | None = None

    def enable_compounding_ingest(self, wiki_dir: Optional[str] = None) -> None:
        """Enable compounding ingest: auto-update wiki pages on every ``learn()`` call.

        When enabled, each new memory triggers a lightweight
        :meth:`~memos.wiki_living.LivingWikiEngine.update_for_item` call
        that creates or updates entity pages for the memory's entities and tags.

        Parameters
        ----------
        wiki_dir:
            Optional path to the wiki directory.  Defaults to ``~/.memos/wiki``.
        """
        from .wiki_living import LivingWikiEngine

        self._compounding_wiki = LivingWikiEngine(self, wiki_dir=wiki_dir)
        self._living_wiki = self._compounding_wiki
        self._compounding_ingest = True
        self._wiki_auto_update = True

    def disable_compounding_ingest(self) -> None:
        """Disable compounding ingest."""
        self._compounding_ingest = False
        self._compounding_wiki = None
        self._living_wiki = None
        self._wiki_auto_update = False

    @property
    def compounding_ingest(self) -> bool:
        """Whether compounding ingest is currently enabled."""
        return self._compounding_ingest

    @property
    def wiki_auto_update(self) -> bool:
        """Whether wiki auto-update is enabled on every learn() call."""
        return self._wiki_auto_update

    @wiki_auto_update.setter
    def wiki_auto_update(self, value: bool) -> None:
        """Enable or disable wiki auto-update."""
        self._wiki_auto_update = value

    @property
    def living_wiki(self) -> Any:
        """The LivingWikiEngine instance, or None if not initialized."""
        return self._living_wiki

    @property
    def namespace(self) -> str:
        return self._namespace

    @namespace.setter
    def namespace(self, value: str) -> None:
        self._namespace = value or ""

    @property
    def acl(self) -> NamespaceACL:
        """Access the namespace ACL for managing access control."""
        return self._acl

    @property
    def kg(self) -> Any | None:
        """Public knowledge-graph handle, if one has been initialized."""
        return self._kg_instance

    @kg.setter
    def kg(self, value: Any | None) -> None:
        self._kg_instance = value

    @property
    def _kg(self) -> Any | None:
        """Backward-compatible alias for older integrations."""
        return self._kg_instance

    @_kg.setter
    def _kg(self, value: Any | None) -> None:
        self._kg_instance = value

    @property
    def kg_bridge(self) -> Any | None:
        """Public KG bridge handle, if one has been initialized."""
        return self._kg_bridge_instance

    @kg_bridge.setter
    def kg_bridge(self, value: Any | None) -> None:
        self._kg_bridge_instance = value

    @property
    def _kg_bridge(self) -> Any | None:
        """Backward-compatible alias for older integrations."""
        return self._kg_bridge_instance

    @_kg_bridge.setter
    def _kg_bridge(self, value: Any | None) -> None:
        self._kg_bridge_instance = value

    def get_or_create_kg(self) -> Any:
        """Return the shared KG instance, creating it lazily when first needed."""
        if self._kg_instance is None:
            from .knowledge_graph import KnowledgeGraph

            self._kg_instance = KnowledgeGraph()
        return self._kg_instance

    def get_or_create_kg_bridge(self, kg: Any | None = None) -> Any:
        """Return the shared KG bridge, rebinding it if the KG instance changed."""
        target_kg = kg or self.get_or_create_kg()
        if self._kg_bridge_instance is None or getattr(self._kg_bridge_instance, "kg", None) is not target_kg:
            from .kg_bridge import KGBridge

            self._kg_bridge_instance = KGBridge(self, target_kg)
        return self._kg_bridge_instance

    # ── ACL Guard ──────────────────────────────────────────

    def _check_acl(self, permission: str) -> None:
        """Check ACL permission for the current agent on the current namespace.

        Only enforces if agent_id is set via set_agent_id().
        Empty namespace bypasses ACL checks.
        """
        if not self._namespace or not hasattr(self, "_agent_id") or not self._agent_id:
            return
        self._acl.check(self._agent_id, self._namespace, permission)

    def set_agent_id(self, agent_id: str) -> None:
        """Set the agent identity for ACL checks.

        When set, all operations on namespaced memories will enforce
        the ACL permissions for this agent.

        Args:
            agent_id: Unique identifier for the agent.
        """
        self._agent_id: str = agent_id

    @property
    def events(self) -> EventBus:
        """Access the event bus for subscriptions."""
        return self._events

    @property
    def analytics(self) -> RecallAnalytics:
        """Access recall analytics."""
        return self._analytics

    def subscribe(
        self,
        callback,
        *,
        event_types: list[str] | None = None,
        namespaces: list[str] | None = None,
        tags: list[str] | None = None,
        label: str = "",
    ) -> str:
        """Subscribe to memory events with optional filters."""
        return self._events.subscribe_filtered(
            callback,
            event_types=event_types,
            namespaces=namespaces,
            tags=tags,
            label=label,
        )

    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from memory events by subscription ID."""
        return self._events.unsubscribe_subscription(subscription_id)

    def list_subscriptions(self) -> list[dict[str, Any]]:
        """List active event subscriptions."""
        return self._events.list_subscriptions()

    def learn(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        importance: float = DEFAULT_IMPORTANCE,
        metadata: Optional[dict[str, Any]] = None,
        ttl: Optional[float] = None,
        allow_duplicate: bool = False,
    ) -> MemoryItem:
        """Store a new memory.

        Args:
            content: Memory text content.
            tags: Optional list of tags.
            importance: Importance score 0.0-1.0.
            metadata: Optional metadata dict.
            ttl: Time-to-live in seconds.
            allow_duplicate: If True, bypass dedup check and insert even if duplicate.
        """
        self._check_acl("write")

        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty")

        if self._sanitize:
            issues = MemorySanitizer.check(content)
            if issues:
                raise ValueError(f"Memory failed sanitization: {issues}")

        # Dedup check — skip if duplicate found and allow_duplicate=False
        # Only block true duplicates: same content AND same tags/importance.
        # If tags or importance differ, treat as an intentional update (versioning).
        if self._dedup_enabled and not allow_duplicate:
            dedup_result = self.dedup_check(content)
            if dedup_result.is_duplicate and dedup_result.match:
                existing = dedup_result.match
                final_tags_check = list(tags) if tags else []
                same_tags = set(existing.tags) == set(final_tags_check)
                same_importance = abs(existing.importance - importance) < IMPORTANCE_EQUALITY_TOLERANCE
                if same_tags and same_importance:
                    logger.info(
                        "Skipping duplicate memory (reason=%s, similarity=%.3f, original=%s)",
                        dedup_result.reason,
                        dedup_result.similarity,
                        existing.id,
                    )
                    return existing

        # Auto-tag with type tags (decision, preference, milestone, etc.)
        final_tags = list(tags) if tags else []
        if not isinstance(final_tags, list):
            final_tags = []
        auto_tags = AutoTagger().auto_tag(content.strip(), existing_tags=final_tags)
        if auto_tags:
            final_tags.extend(auto_tags)

        item = MemoryItem(
            id=generate_id(content),
            content=content.strip(),
            tags=final_tags,
            importance=max(0.0, min(1.0, importance)),
            metadata=metadata or {},
            ttl=ttl,
        )

        self._store.upsert(item, namespace=self._namespace)

        # Register in dedup index
        if self._dedup_enabled and self._dedup_engine:
            self._dedup_engine.register(item)
        self._retrieval.index(item)
        self._versioning.record_version(item, source="learn")

        # Emit event
        self._events.emit_sync(
            "learned",
            {
                "id": item.id,
                "content": item.content[:200],
                "tags": item.tags,
                "importance": item.importance,
                "ttl": item.ttl,
            },
            namespace=self._namespace,
        )

        # Auto-update wiki if living wiki is initialized
        if self._wiki_auto_update and self._living_wiki is not None:
            try:
                self._living_wiki.update_for_item(item)
            except Exception:
                logger.warning("Wiki update failed during learn()", exc_info=True)
                pass  # Wiki update failure should not block learn()

        return item

    # ── Dedup ──────────────────────────────────────────

    @property
    def dedup_enabled(self) -> bool:
        """Whether dedup checking is enabled."""
        return self._dedup_enabled

    def dedup_set_enabled(self, enabled: bool = True, threshold: float = DEFAULT_DEDUP_THRESHOLD) -> None:
        """Enable or disable dedup checking at write time.

        Args:
            enabled: Enable dedup on learn().
            threshold: Similarity threshold (0.0-1.0) for near-duplicate detection.
        """
        self._dedup_enabled = enabled
        self._dedup_threshold = threshold
        if enabled:
            self._dedup_engine = DedupEngine(
                self._store,
                threshold=threshold,
                namespace=self._namespace or None,
            )
        else:
            self._dedup_engine = None

    def dedup_check(self, content: str, *, threshold: Optional[float] = None) -> "DedupCheckResult":
        """Check if content would be a duplicate.

        Args:
            content: Content to check.
            threshold: Override threshold for this check.

        Returns:
            DedupCheckResult with is_duplicate, match, reason, similarity.
        """
        if self._dedup_engine is None:
            self._dedup_engine = DedupEngine(
                self._store,
                threshold=threshold or self._dedup_threshold,
                namespace=self._namespace or None,
            )
        return self._dedup_engine.check(content, threshold=threshold)

    def dedup_scan(self, *, fix: bool = False, threshold: Optional[float] = None) -> "DedupScanResult":
        """Scan all memories for duplicates.

        Args:
            fix: If True, remove found duplicates.
            threshold: Override threshold for this scan.

        Returns:
            DedupScanResult with counts and details.
        """
        if self._dedup_engine is None:
            self._dedup_engine = DedupEngine(
                self._store,
                threshold=threshold or self._dedup_threshold,
                namespace=self._namespace or None,
            )
        result = self._dedup_engine.scan(fix=fix, threshold=threshold)
        if fix:
            self._dedup_engine.invalidate_cache()
        return result

    def batch_learn(
        self,
        items: list[dict[str, Any]],
        *,
        continue_on_error: bool = True,
    ) -> dict[str, Any]:
        """Store multiple memories in one call.

        Each item dict should have: content (required), tags, importance, metadata.
        Returns a summary with counts of learned, skipped, and errors.

        Args:
            items: List of dicts with memory data.
            continue_on_error: If True, skip invalid items. If False, raise on first error.

        Returns:
            dict with learned, skipped, errors counts and details.
        """
        self._check_acl("write")
        result = {
            "learned": 0,
            "skipped": 0,
            "errors": [],
            "items": [],
        }

        # Prepare valid items for batch upsert
        valid_items: list[MemoryItem] = []

        for entry in items:
            content = entry.get("content", "").strip()
            if not content:
                result["skipped"] += 1
                if not continue_on_error:
                    raise ValueError("Empty content in batch_learn item")
                continue

            # Sanitize
            if self._sanitize:
                issues = MemorySanitizer.check(content)
                if issues:
                    result["errors"].append(
                        {
                            "content": content[:100],
                            "reason": f"Sanitization failed: {issues}",
                        }
                    )
                    if not continue_on_error:
                        raise ValueError(f"Memory failed sanitization: {issues}")
                    continue

            item = MemoryItem(
                id=generate_id(content),
                content=content,
                tags=entry.get("tags", []),
                importance=max(0.0, min(1.0, entry.get("importance", DEFAULT_IMPORTANCE))),
                metadata=entry.get("metadata", {}),
            )
            valid_items.append(item)

        # Use batch upsert for backends that support it
        if hasattr(self._store, "upsert_batch") and len(valid_items) > 1:
            # Pinecone and similar backends have optimized batch upsert
            try:
                self._store.upsert_batch(valid_items, namespace=self._namespace)
            except AttributeError:
                # Fallback to individual upserts
                for item in valid_items:
                    self._store.upsert(item, namespace=self._namespace)
        else:
            for item in valid_items:
                self._store.upsert(item, namespace=self._namespace)

        # Index all valid items
        for item in valid_items:
            self._retrieval.index(item)
            result["items"].append(
                {
                    "id": item.id,
                    "content": item.content[:100],
                    "tags": item.tags,
                }
            )

        result["learned"] = len(valid_items)

        # Record versions for batch-learned items
        for item in valid_items:
            self._versioning.record_version(item, source="batch_learn")

        # Emit batch event
        if valid_items:
            tag_union = sorted({tag for item in valid_items for tag in item.tags})
            self._events.emit_sync(
                "batch_learned",
                {
                    "count": len(valid_items),
                    "skipped": result["skipped"],
                    "errors": len(result["errors"]),
                    "tags": tag_union,
                },
                namespace=self._namespace,
            )

        return result

    def recall(
        self,
        query: str,
        top: int = 5,
        filter_tags: Optional[list[str]] = None,
        min_score: float = 0.0,
        filter_after: Optional[float] = None,
        filter_before: Optional[float] = None,
        retrieval_mode: str = "semantic",
        tag_filter: Optional[dict[str, Any]] = None,
        min_importance: Optional[float] = None,
        max_importance: Optional[float] = None,
    ) -> list[RecallResult]:
        """Retrieve memories relevant to a query."""
        self._check_acl("read")
        started = time.perf_counter()
        final_results: list[RecallResult] = []

        def _coerce_tags(values: Any) -> list[str]:
            if not values:
                return []
            if isinstance(values, str):
                return [values]
            return [str(value) for value in values if value]

        include_tags = _coerce_tags(filter_tags)
        require_tags: list[str] = []
        exclude_tags: list[str] = []
        if tag_filter:
            include_tags.extend(_coerce_tags(tag_filter.get("include")))
            require_tags.extend(_coerce_tags(tag_filter.get("require")))
            exclude_tags.extend(_coerce_tags(tag_filter.get("exclude")))
            if str(tag_filter.get("mode") or "").upper() == "AND" and include_tags:
                require_tags.extend(include_tags)
                include_tags = []

        try:
            query_engine = QueryEngine(
                self._retrieval,
                namespace=self._namespace,
                decay=self._decay,
            )
            final_results = query_engine.execute(
                MemoryQuery(
                    query=query,
                    top_k=top,
                    retrieval_mode=retrieval_mode,
                    include_tags=include_tags,
                    require_tags=require_tags,
                    exclude_tags=exclude_tags,
                    min_importance=min_importance,
                    max_importance=max_importance,
                    created_after=filter_after,
                    created_before=filter_before,
                    min_score=min_score,
                ),
                self._store,
            )
            for result in final_results:
                result.item.touch()
                self._store.upsert(result.item, namespace=self._namespace)
                self._events.emit_sync(
                    "recalled",
                    {
                        "id": result.item.id,
                        "query": query,
                        "score": result.score,
                        "tags": result.item.tags,
                    },
                    namespace=self._namespace,
                )
        finally:
            try:
                self._analytics.track_recall(query, final_results, (time.perf_counter() - started) * 1000.0)
            except Exception:
                logger.warning("Analytics tracking failed during recall()", exc_info=True)

        return final_results

    def list_memories(
        self,
        *,
        tags: Optional[list[str]] = None,
        require_tags: Optional[list[str]] = None,
        exclude_tags: Optional[list[str]] = None,
        min_importance: Optional[float] = None,
        max_importance: Optional[float] = None,
        created_after: Optional[float] = None,
        created_before: Optional[float] = None,
        sort: str = "created_at",
        limit: int = 50,
    ) -> list[MemoryItem]:
        """List memories with structured filters and sorting."""
        self._check_acl("read")
        query_engine = QueryEngine(
            self._retrieval,
            namespace=self._namespace,
            decay=self._decay,
        )

        def _coerce_tags(values: Any) -> list[str]:
            if not values:
                return []
            if isinstance(values, str):
                return [values]
            return [str(value) for value in values if value]

        return query_engine.list_items(
            MemoryQuery(
                top_k=limit,
                include_tags=_coerce_tags(tags),
                require_tags=_coerce_tags(require_tags),
                exclude_tags=_coerce_tags(exclude_tags),
                min_importance=min_importance,
                max_importance=max_importance,
                created_after=created_after,
                created_before=created_before,
                sort=sort,
            ),
            self._store,
        )

    async def recall_stream(
        self,
        query: str,
        top: int = 5,
        filter_tags: list[str] | None = None,
        min_score: float = 0.0,
    ):
        """Async generator that yields recall results one at a time.

        Each result is yielded as soon as it is scored, allowing consumers
        to start processing partial results before the full search completes.
        For LLM agents, this enables progressive context building.

        Yields RecallResult objects sorted by score (best first).
        """
        # Get all candidate results
        all_results = self.recall(
            query=query,
            top=top,
            filter_tags=filter_tags,
            min_score=min_score,
        )

        # Yield them one by one — for backends with native streaming
        # this could be extended to yield as each result arrives
        for result in all_results:
            yield result
            # Allow the event loop to interleave other work
            import asyncio

            await asyncio.sleep(0)





    def forget_tag(self, tag: str) -> int:
        """Delete all memories carrying a given tag."""
        self._check_acl("delete")
        removed = 0
        for item in self._store.list_all(namespace=self._namespace):
            if tag not in item.tags:
                continue
            if self._store.delete(item.id, namespace=self._namespace):
                self._events.emit_sync(
                    "forgotten",
                    {
                        "id": item.id,
                        "content": item.content[:200],
                        "tags": item.tags,
                    },
                    namespace=self._namespace,
                )
                removed += 1
        return removed

    def forget(self, content_or_id: str) -> bool:
        """Delete a specific memory by content or ID."""
        self._check_acl("delete")
        item = self._store.get(content_or_id, namespace=self._namespace)
        if self._store.delete(content_or_id, namespace=self._namespace):
            self._events.emit_sync(
                "forgotten",
                {
                    "id": content_or_id,
                    "content": item.content[:200] if item else "",
                    "tags": item.tags if item else [],
                },
                namespace=self._namespace,
            )
            return True
        content_id = generate_id(content_or_id)
        item = self._store.get(content_id, namespace=self._namespace)
        if self._store.delete(content_id, namespace=self._namespace):
            self._events.emit_sync(
                "forgotten",
                {
                    "id": content_id,
                    "content": item.content[:200] if item else "",
                    "tags": item.tags if item else [],
                },
                namespace=self._namespace,
            )
            return True
        return False

    def stats(self, items: list[MemoryItem] | None = None) -> MemoryStats:
        """Get memory store statistics."""
        items = items if items is not None else self._store.list_all(namespace=self._namespace)
        if not items:
            return MemoryStats()

        now = time.time()
        scores = [self._decay.adjusted_score(DEFAULT_IMPORTANCE, item) for item in items]
        tags: dict[str, int] = {}
        for item in items:
            for tag in item.tags:
                tags[tag] = tags.get(tag, 0) + 1

        top_tags = sorted(tags, key=tags.get, reverse=True)[:10]
        decay_candidate_items = self._decay.find_prune_candidates(items, threshold=STATS_DECAY_THRESHOLD)
        decay_candidates = len(decay_candidate_items)
        expired_items = [i for i in items if i.is_expired]

        total_chars = sum(len(i.content) for i in items)
        prunable_chars = sum(len(i.content) for i in decay_candidate_items)
        expired_chars = sum(len(i.content) for i in expired_items)

        return MemoryStats(
            total_memories=len(items),
            total_tags=len(tags),
            avg_relevance=sum(scores) / len(scores),
            avg_importance=sum(i.importance for i in items) / len(items),
            oldest_memory_days=(now - min(i.created_at for i in items)) / SECONDS_PER_DAY,
            newest_memory_days=(now - max(i.created_at for i in items)) / SECONDS_PER_DAY,
            decay_candidates=decay_candidates,
            expired_memories=len(expired_items),
            top_tags=top_tags,
            total_chars=total_chars,
            total_tokens=total_chars // 4,
            prunable_tokens=prunable_chars // 4,
            expired_tokens=expired_chars // 4,
        )

    def list_tags(self, sort: str = "count", limit: int = 0) -> list[tuple[str, int]]:
        """List all tags with their memory counts.

        Args:
            sort: "count" (descending) or "name" (alphabetical).
            limit: Max tags to return. 0 = all.

        Returns:
            List of (tag, count) tuples.
        """
        self._check_acl("read")
        items = self._store.list_all(namespace=self._namespace)
        tag_counts: dict[str, int] = {}
        for item in items:
            for tag in item.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        if sort == "name":
            result = sorted(tag_counts.items(), key=lambda x: x[0])
        else:
            result = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

        if limit > 0:
            result = result[:limit]
        return result

    def rename_tag(self, old_tag: str, new_tag: str) -> int:
        """Rename a tag across all memories.

        Args:
            old_tag: Tag name to replace.
            new_tag: New tag name.

        Returns:
            Number of memories updated.
        """
        self._check_acl("write")
        updated = 0
        old_lower = old_tag.lower()
        for item in self._store.list_all(namespace=self._namespace):
            tags_lower = [t.lower() for t in item.tags]
            if old_lower not in tags_lower:
                continue
            new_tags = [new_tag if t.lower() == old_lower else t for t in item.tags]
            item.tags = new_tags
            item.accessed_at = time.time()
            self._store.upsert(item, namespace=self._namespace)
            self._events.emit_sync(
                "tag_renamed",
                {
                    "id": item.id,
                    "old_tag": old_tag,
                    "new_tag": new_tag,
                },
                namespace=self._namespace,
            )
            updated += 1
        return updated

    def delete_tag(self, tag: str) -> int:
        """Delete a tag from all memories without removing the memories.

        Args:
            tag: Tag name to remove.

        Returns:
            Number of memories updated.
        """
        self._check_acl("write")
        updated = 0
        tag_lower = tag.lower()
        for item in self._store.list_all(namespace=self._namespace):
            tags_lower = [t.lower() for t in item.tags]
            if tag_lower not in tags_lower:
                continue
            new_tags = [t for t in item.tags if t.lower() != tag_lower]
            item.tags = new_tags
            item.accessed_at = time.time()
            self._store.upsert(item, namespace=self._namespace)
            self._events.emit_sync(
                "tag_deleted",
                {
                    "id": item.id,
                    "tag": tag,
                },
                namespace=self._namespace,
            )
            updated += 1
        return updated

    def search(self, q: str, limit: int = 20) -> list[MemoryItem]:
        """Simple keyword search across all memories."""
        self._check_acl("read")
        return self._store.search(q, limit=limit, namespace=self._namespace)

    def get(self, item_id: str) -> Optional["MemoryItem"]:
        """Retrieve a single memory item by ID.

        Args:
            item_id: The unique identifier of the memory item.

        Returns:
            The MemoryItem if found, or None.
        """
        self._check_acl("read")
        return self._store.get(item_id, namespace=self._namespace)

    def list_namespaces(self) -> list[str]:
        """List all non-default namespaces."""
        return self._store.list_namespaces()

    # ── Namespace ACL Management ───────────────────────────

    def grant_namespace_access(
        self,
        agent_id: str,
        namespace: str,
        role: str | Role,
        *,
        granted_by: str = "",
        expires_at: Optional[float] = None,
    ) -> dict[str, Any]:
        """Grant an agent access to a namespace.

        Args:
            agent_id: Unique identifier for the agent.
            namespace: Target namespace.
            role: Access role ("owner", "writer", "reader", "denied").
            granted_by: ID of the agent performing the grant.
            expires_at: Optional Unix timestamp when access expires.

        Returns:
            The created policy as a dict.
        """
        if isinstance(role, str):
            role = Role(role)
        policy = self._acl.grant(
            agent_id,
            namespace,
            role,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        self._events.emit_sync(
            "acl_granted",
            {
                "agent_id": agent_id,
                "namespace": namespace,
                "role": role.value,
            },
            namespace=namespace,
        )
        return policy.to_dict()

    def revoke_namespace_access(
        self,
        agent_id: str,
        namespace: str,
    ) -> bool:
        """Revoke an agent's access to a namespace.

        Returns True if a policy was revoked, False if none existed.
        """
        removed = self._acl.revoke(agent_id, namespace)
        if removed:
            self._events.emit_sync(
                "acl_revoked",
                {
                    "agent_id": agent_id,
                    "namespace": namespace,
                },
                namespace=namespace,
            )
            return True
        return False

    def list_namespace_policies(
        self,
        namespace: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List ACL policies, optionally filtered by namespace."""
        return [p.to_dict() for p in self._acl.list_policies(namespace=namespace)]

    def namespace_acl_stats(self) -> dict[str, Any]:
        """Get namespace ACL statistics."""
        return self._acl.stats()



    def ingest(
        self,
        path: str,
        *,
        tags: list[str] | None = None,
        importance: float = DEFAULT_IMPORTANCE,
        max_chunk: int = DEFAULT_MAX_CHUNK_SIZE,
        dry_run: bool = False,
    ) -> "IngestResult":
        """Parse and store memories from a file (markdown, JSON, txt)."""
        from .ingest.engine import ingest_file

        result = ingest_file(path, tags=tags, importance=importance, max_chunk=max_chunk)

        if not dry_run:
            for chunk in result.chunks:
                try:
                    self.learn(
                        chunk["content"],
                        tags=chunk.get("tags", []),
                        importance=chunk.get("importance", importance),
                        metadata=chunk.get("metadata", {}),
                    )
                except Exception as e:
                    result.errors.append(f"Failed to store chunk: {e}")

        return result

    def ingest_url(
        self,
        url: str,
        *,
        tags: list[str] | None = None,
        importance: float = DEFAULT_IMPORTANCE,
        max_chunk: int = DEFAULT_MAX_CHUNK_SIZE,
        dry_run: bool = False,
        skip_sanitization: bool = False,
    ) -> "IngestResult":
        """Fetch a URL, extract its contents, and store it as memories."""
        from .ingest.url import URLIngestor

        result = URLIngestor().ingest(
            url,
            tags=tags,
            importance=importance,
            max_chunk=max_chunk,
        )

        if not dry_run:
            for chunk in result.chunks:
                if skip_sanitization:
                    # Bypass sanitizer: store as a MemoryItem directly
                    try:
                        item = MemoryItem(
                            id=generate_id(chunk["content"]),
                            content=chunk["content"],
                            tags=chunk.get("tags", []),
                            importance=chunk.get("importance", importance),
                            metadata=chunk.get("metadata", {}),
                        )
                        self._store.upsert(item, namespace=self._namespace)
                        continue
                    except Exception as e:
                        result.errors.append(f"Failed to store chunk (skip_sanitization): {e}")
                        continue
                try:
                    self.learn(
                        chunk["content"],
                        tags=chunk.get("tags", []),
                        importance=chunk.get("importance", importance),
                        metadata=chunk.get("metadata", {}),
                    )
                except Exception as e:
                    result.errors.append(f"Failed to store chunk: {e}")

        return result












