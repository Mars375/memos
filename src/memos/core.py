"""Core MemOS client — the main entry point."""

from __future__ import annotations

import time
from typing import Any, Optional

from .models import MemoryItem, RecallResult, MemoryStats, FeedbackEntry, FeedbackStats, generate_id
from .retrieval.engine import RetrievalEngine
from .storage.base import StorageBackend
from .storage.chroma_backend import ChromaBackend
from .storage.memory_backend import InMemoryBackend
from .storage.json_backend import JsonFileBackend
from .storage.qdrant_backend import QdrantBackend
from .storage.pinecone_backend import PineconeBackend
from .decay.engine import DecayEngine
from .sanitizer import MemorySanitizer
from .crypto import MemoryCrypto
from .storage.encrypted_backend import EncryptedStorageBackend
from .events import EventBus
from .versioning.engine import VersioningEngine
from .versioning.models import MemoryVersion, VersionDiff
from .namespaces.acl import NamespaceACL, Role
from .cache.embedding_cache import EmbeddingCache
from .analytics import RecallAnalytics
from .tagger import AutoTagger
from .sharing.engine import SharingEngine
from .sharing.models import ShareRequest, ShareStatus, SharePermission, ShareScope, MemoryEnvelope
from .migration import MigrationEngine, MigrationReport, _create_backend
from .query import MemoryQuery, QueryEngine


class MemOS:
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
        decay_rate: float = 0.01,
        max_memories: int = 10_000,
        encryption_key: Optional[str] = None,
        **kwargs,
    ) -> None:
        self._backend_name = backend
        # Storage
        if backend == "chroma":
            import os as _os
            # Only enable client-side Ollama embeddings when MEMOS_EMBED_HOST is
            # explicitly configured. When unset, Chroma uses its built-in ONNX
            # embedder (backward compatible with existing collections).
            _chroma_embed_host = _os.environ.get("MEMOS_EMBED_HOST", "")
            store: StorageBackend = ChromaBackend(
                host=chroma_host,
                port=chroma_port,
                embed_host=_chroma_embed_host,
                embed_model=embed_model,
            )
        elif backend == "qdrant":
            store = QdrantBackend(
                host=kwargs.get("qdrant_host", "localhost"),
                port=kwargs.get("qdrant_port", 6333),
                api_key=kwargs.get("qdrant_api_key"),
                path=kwargs.get("qdrant_path"),
                embed_host=embed_host,
                embed_model=embed_model,
                vector_size=kwargs.get("vector_size", 768),
            )
        elif backend == "pinecone":
            store = PineconeBackend(
                api_key=kwargs.get("pinecone_api_key", ""),
                environment=kwargs.get("pinecone_environment"),
                index_name=kwargs.get("pinecone_index_name", "memos"),
                embed_host=embed_host,
                embed_model=embed_model,
                vector_size=kwargs.get("vector_size", 768),
                cloud=kwargs.get("pinecone_cloud", "aws"),
                region=kwargs.get("pinecone_region", "us-east-1"),
                serverless=kwargs.get("pinecone_serverless", True),
            )
        elif backend == "json":
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
        self._retrieval = RetrievalEngine(
            store=self._store,
            embed_host=embed_host,
            embed_model=embed_model,
            semantic_weight=kwargs.get("semantic_weight", 0.6),
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
            max_versions_per_item=kwargs.get("max_versions_per_item", 100),
            persistent_path=kwargs.get("versioning_path"),
        )

        # Embedding cache (persistent disk-backed)
        # Enabled by default — avoids re-calling Ollama for the same text across
        # requests and restarts. Stored in ~/.memos/embeddings.db (persistent volume).
        cache_enabled = kwargs.get("cache_enabled", True)
        if cache_enabled:
            self._embedding_cache = EmbeddingCache(
                path=kwargs.get("cache_path", "~/.memos/embeddings.db"),
                max_size=kwargs.get("cache_max_size", 50_000),
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
            retention_days=kwargs.get("analytics_retention_days", 90),
        )

        # Feedback is stored in memory item metadata["_feedback"] for persistence

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
        importance: float = 0.5,
        metadata: Optional[dict[str, Any]] = None,
        ttl: Optional[float] = None,
    ) -> MemoryItem:
        """Store a new memory."""
        self._check_acl("write")

        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty")

        if self._sanitize:
            issues = MemorySanitizer.check(content)
            if issues:
                raise ValueError(f"Memory failed sanitization: {issues}")

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
        self._retrieval.index(item)
        self._versioning.record_version(item, source="learn")

        # Emit event
        self._events.emit_sync("learned", {
            "id": item.id,
            "content": item.content[:200],
            "tags": item.tags,
            "importance": item.importance,
            "ttl": item.ttl,
        }, namespace=self._namespace)

        return item

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
                    result["errors"].append({
                        "content": content[:100],
                        "reason": f"Sanitization failed: {issues}",
                    })
                    if not continue_on_error:
                        raise ValueError(f"Memory failed sanitization: {issues}")
                    continue

            item = MemoryItem(
                id=generate_id(content),
                content=content,
                tags=entry.get("tags", []),
                importance=max(0.0, min(1.0, entry.get("importance", 0.5))),
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
            result["items"].append({
                "id": item.id,
                "content": item.content[:100],
                "tags": item.tags,
            })

        result["learned"] = len(valid_items)

        # Record versions for batch-learned items
        for item in valid_items:
            self._versioning.record_version(item, source="batch_learn")

        # Emit batch event
        if valid_items:
            tag_union = sorted({tag for item in valid_items for tag in item.tags})
            self._events.emit_sync("batch_learned", {
                "count": len(valid_items),
                "skipped": result["skipped"],
                "errors": len(result["errors"]),
                "tags": tag_union,
            }, namespace=self._namespace)

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
                self._events.emit_sync("recalled", {
                    "id": result.item.id,
                    "query": query,
                    "score": result.score,
                    "tags": result.item.tags,
                }, namespace=self._namespace)
        finally:
            try:
                self._analytics.track_recall(query, final_results, (time.perf_counter() - started) * 1000.0)
            except Exception:
                pass

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

    def prune(
        self,
        threshold: float = 0.1,
        max_age_days: float = 90.0,
        dry_run: bool = False,
    ) -> list[MemoryItem]:
        """Remove decayed memories."""
        all_items = self._store.list_all(namespace=self._namespace)
        candidates = self._decay.find_prune_candidates(
            items=all_items,
            threshold=threshold,
            max_age_days=max_age_days,
        )

        if not dry_run:
            tag_union = sorted({tag for item in candidates for tag in item.tags})
            for item in candidates:
                self._store.delete(item.id, namespace=self._namespace)

            # Emit pruned event
            if candidates:
                self._events.emit_sync("pruned", {
                    "count": len(candidates),
                    "ids": [c.id for c in candidates],
                    "threshold": threshold,
                    "max_age_days": max_age_days,
                    "tags": tag_union,
                }, namespace=self._namespace)

        return candidates

    def prune_expired(self, *, dry_run: bool = False) -> list[MemoryItem]:
        """Remove all expired memories (past their TTL).

        Args:
            dry_run: If True, return candidates without deleting.

        Returns:
            List of expired MemoryItems that were removed.
        """
        all_items = self._store.list_all(namespace=self._namespace)
        expired = [item for item in all_items if item.is_expired]

        if not dry_run:
            for item in expired:
                self._store.delete(item.id, namespace=self._namespace)
            if expired:
                self._events.emit_sync("expired_pruned", {
                    "count": len(expired),
                    "ids": [i.id for i in expired],
                }, namespace=self._namespace)

        return expired

    def forget_tag(self, tag: str) -> int:
        """Delete all memories carrying a given tag."""
        self._check_acl("delete")
        removed = 0
        for item in self._store.list_all(namespace=self._namespace):
            if tag not in item.tags:
                continue
            if self._store.delete(item.id, namespace=self._namespace):
                self._events.emit_sync("forgotten", {
                    "id": item.id,
                    "content": item.content[:200],
                    "tags": item.tags,
                }, namespace=self._namespace)
                removed += 1
        return removed

    def forget(self, content_or_id: str) -> bool:
        """Delete a specific memory by content or ID."""
        self._check_acl("delete")
        item = self._store.get(content_or_id, namespace=self._namespace)
        if self._store.delete(content_or_id, namespace=self._namespace):
            self._events.emit_sync("forgotten", {
                "id": content_or_id,
                "content": item.content[:200] if item else "",
                "tags": item.tags if item else [],
            }, namespace=self._namespace)
            return True
        content_id = generate_id(content_or_id)
        item = self._store.get(content_id, namespace=self._namespace)
        if self._store.delete(content_id, namespace=self._namespace):
            self._events.emit_sync("forgotten", {
                "id": content_id,
                "content": item.content[:200] if item else "",
                "tags": item.tags if item else [],
            }, namespace=self._namespace)
            return True
        return False

    def stats(self) -> MemoryStats:
        """Get memory store statistics."""
        items = self._store.list_all(namespace=self._namespace)
        if not items:
            return MemoryStats()

        now = time.time()
        scores = [self._decay.adjusted_score(0.5, item) for item in items]
        tags: dict[str, int] = {}
        for item in items:
            for tag in item.tags:
                tags[tag] = tags.get(tag, 0) + 1

        top_tags = sorted(tags, key=tags.get, reverse=True)[:10]
        decay_candidates = len(
            self._decay.find_prune_candidates(items, threshold=0.2)
        )

        return MemoryStats(
            total_memories=len(items),
            total_tags=len(tags),
            avg_relevance=sum(scores) / len(scores),
            avg_importance=sum(i.importance for i in items) / len(items),
            oldest_memory_days=(now - min(i.created_at for i in items)) / 86400,
            newest_memory_days=(now - max(i.created_at for i in items)) / 86400,
            decay_candidates=decay_candidates,
            expired_memories=sum(1 for i in items if i.is_expired),
            top_tags=top_tags,
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
            self._events.emit_sync("tag_renamed", {
                "id": item.id,
                "old_tag": old_tag,
                "new_tag": new_tag,
            }, namespace=self._namespace)
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
            self._events.emit_sync("tag_deleted", {
                "id": item.id,
                "tag": tag,
            }, namespace=self._namespace)
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
            agent_id, namespace, role,
            granted_by=granted_by, expires_at=expires_at,
        )
        self._events.emit_sync("acl_granted", {
            "agent_id": agent_id,
            "namespace": namespace,
            "role": role.value,
        }, namespace=namespace)
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
            self._events.emit_sync("acl_revoked", {
                "agent_id": agent_id,
                "namespace": namespace,
            }, namespace=namespace)
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

    def consolidate(
        self,
        *,
        similarity_threshold: float = 0.75,
        merge_content: bool = False,
        dry_run: bool = False,
    ) -> "ConsolidationResult":
        """Find and merge semantically similar memories."""
        from .consolidation.engine import ConsolidationEngine
        engine = ConsolidationEngine(similarity_threshold=similarity_threshold)
        result = engine.consolidate(self._store, merge_content=merge_content, dry_run=dry_run)

        if not dry_run and result.memories_merged > 0:
            self._events.emit_sync("consolidated", {
                "groups_found": result.groups_found,
                "memories_merged": result.memories_merged,
            }, namespace=self._namespace)

        return result

    def ingest(
        self,
        path: str,
        *,
        tags: list[str] | None = None,
        importance: float = 0.5,
        max_chunk: int = 2000,
        dry_run: bool = False,
    ) -> "IngestResult":
        """Parse and store memories from a file (markdown, JSON, txt)."""
        from .ingest.engine import ingest_file, IngestResult

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
        importance: float = 0.5,
        max_chunk: int = 2000,
        dry_run: bool = False,
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

    def export_json(self, *, include_metadata: bool = True) -> dict:
        """Export all memories as a JSON-serializable dict."""
        items = self._store.list_all()
        return {
            "version": "0.2.0",
            "exported_at": time.time(),
            "total": len(items),
            "memories": [
                {
                    "id": item.id,
                    "content": item.content,
                    "tags": item.tags,
                    "importance": item.importance,
                    "created_at": item.created_at,
                    "accessed_at": item.accessed_at,
                    "access_count": item.access_count,
                    **({"metadata": item.metadata} if include_metadata else {}),
                }
                for item in items
            ],
        }

    def import_json(
        self,
        data: dict,
        *,
        merge: str = "skip",
        tags_prefix: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Import memories from a JSON dict (as produced by export_json)."""
        result = {"imported": 0, "skipped": 0, "overwritten": 0, "errors": []}
        memories = data.get("memories", [])

        for entry in memories:
            try:
                mem_id = entry.get("id", generate_id(entry["content"]))
                existing = self._store.get(mem_id)

                if existing and merge == "skip":
                    result["skipped"] += 1
                    continue

                if existing and merge == "overwrite":
                    self._store.delete(mem_id)
                    result["overwritten"] += 1

                tags = list(entry.get("tags", []))
                if tags_prefix:
                    tags.extend(tags_prefix)

                if not dry_run:
                    item = MemoryItem(
                        id=mem_id,
                        content=entry["content"].strip(),
                        tags=tags,
                        importance=max(0.0, min(1.0, entry.get("importance", 0.5))),
                        created_at=entry.get("created_at", time.time()),
                        accessed_at=entry.get("accessed_at", time.time()),
                        access_count=entry.get("access_count", 0),
                        metadata=entry.get("metadata", {}),
                    )
                    self._store.upsert(item)
                    self._retrieval.index(item)
                result["imported"] += 1
            except Exception as e:
                result["errors"].append(str(e))

        return result

    # ── Parquet export/import ─────────────────────────────────

    def export_parquet(
        self,
        path: str,
        *,
        include_metadata: bool = True,
        compression: str = "zstd",
    ) -> dict:
        """Export all memories to a Parquet file.

        Requires pyarrow: ``pip install memos[parquet]``

        Args:
            path: Output file path.
            include_metadata: Include metadata as a JSON column.
            compression: Parquet codec (zstd, snappy, gzip, none).

        Returns:
            Summary dict with total, path, size_bytes, compression.
        """
        from .parquet_io import export_parquet as _export
        items = self._store.list_all(namespace=self._namespace)
        result = _export(items, path, include_metadata=include_metadata, compression=compression)

        self._events.emit_sync("exported", {
            "format": "parquet",
            "total": result["total"],
            "path": result["path"],
            "size_bytes": result["size_bytes"],
        }, namespace=self._namespace)

        return result

    def import_parquet(
        self,
        path: str,
        *,
        merge: str = "skip",
        tags_prefix: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Import memories from a Parquet file.

        Requires pyarrow: ``pip install memos[parquet]``

        Args:
            path: Input Parquet file path.
            merge: "skip" (ignore existing), "overwrite" (replace), "duplicate" (always add).
            tags_prefix: Extra tags to add to all imported items.
            dry_run: If True, parse but don't store.

        Returns:
            dict with imported, skipped, overwritten, errors counts.
        """
        from .parquet_io import import_parquet as _import

        items = _import(path, tags_prefix=tags_prefix)
        result = {"imported": 0, "skipped": 0, "overwritten": 0, "errors": []}

        for item in items:
            try:
                existing = self._store.get(item.id, namespace=self._namespace)

                if existing and merge == "skip":
                    result["skipped"] += 1
                    continue

                if existing and merge == "overwrite":
                    self._store.delete(item.id, namespace=self._namespace)
                    result["overwritten"] += 1

                if not dry_run:
                    self._store.upsert(item, namespace=self._namespace)
                    self._retrieval.index(item)
                result["imported"] += 1
            except Exception as e:
                result["errors"].append(str(e))

        self._events.emit_sync("imported", {
            "format": "parquet",
            "imported": result["imported"],
            "skipped": result["skipped"],
        }, namespace=self._namespace)

        return result

    def migrate_to(
        self,
        dest_backend: str,
        *,
        namespaces: list[str] | None = None,
        tags_filter: list[str] | None = None,
        merge: str = "skip",
        dry_run: bool = False,
        batch_size: int = 100,
        **backend_kwargs,
    ) -> MigrationReport:
        """Migrate memories from this backend to another backend.

        Args:
            dest_backend: Target backend name.
            namespaces: Optional namespace filter.
            tags_filter: Optional tag filter.
            merge: "skip", "overwrite", or "error" for existing items.
            dry_run: If True, report without writing.
            batch_size: Progress callback interval.
            backend_kwargs: Destination backend constructor args.
        """
        dest = _create_backend(dest_backend, **backend_kwargs)
        source_namespaces = namespaces
        if source_namespaces is None and self._namespace:
            source_namespaces = [self._namespace]
        engine = MigrationEngine()
        return engine.migrate(
            self._store,
            self._backend_name,
            dest,
            dest_backend,
            namespaces=source_namespaces,
            tags_filter=tags_filter,
            merge=merge,
            dry_run=dry_run,
            batch_size=batch_size,
        )

    # ── Async consolidation ───────────────────────────────────

    async def consolidate_async(
        self,
        *,
        similarity_threshold: float = 0.75,
        merge_content: bool = False,
        dry_run: bool = False,
    ) -> "AsyncConsolidationHandle":
        """Start async consolidation in the background.

        Returns a handle that can be polled for progress and result.
        The consolidation runs in a thread pool so the event loop stays responsive.

        Usage::

            handle = await mem.consolidate_async(similarity_threshold=0.7)
            # ... do other work ...
            status = mem.consolidation_status(handle.task_id)
        """
        from .consolidation.async_engine import AsyncConsolidationEngine

        if not hasattr(self, "_async_consolidator"):
            self._async_consolidator = AsyncConsolidationEngine()
            self._async_consolidator.on_event(
                lambda etype, data: self._events.emit_sync(etype, data, namespace=self._namespace)
            )

        return await self._async_consolidator.start(
            self._store,
            similarity_threshold=similarity_threshold,
            merge_content=merge_content,
            dry_run=dry_run,
        )

    def consolidation_status(self, task_id: str) -> dict | None:
        """Get the status of an async consolidation task.

        Returns None if task_id not found, else a status dict.
        """
        if not hasattr(self, "_async_consolidator"):
            return None
        handle = self._async_consolidator.get_status(task_id)
        return handle.to_dict() if handle else None

    def consolidation_tasks(self) -> list[dict]:
        """List all async consolidation tasks."""
        if not hasattr(self, "_async_consolidator"):
            return []
        return [h.to_dict() for h in self._async_consolidator.list_tasks()]

    # ── Compaction ────────────────────────────────────────────

    def compact(
        self,
        *,
        archive_age_days: float = 90.0,
        archive_importance_floor: float = 0.3,
        stale_score_threshold: float = 0.25,
        merge_similarity_threshold: float = 0.6,
        cluster_min_size: int = 3,
        dry_run: bool = False,
        max_compact_per_run: int = 200,
    ) -> dict[str, Any]:
        """Run memory compaction: dedup + archive + merge stale + compress clusters.

        Safe to run periodically (e.g., daily cron). Use dry_run=True to preview.

        Returns:
            dict with detailed compaction report.
        """
        from .compaction.engine import CompactionEngine, CompactionConfig

        config = CompactionConfig(
            archive_age_days=archive_age_days,
            archive_importance_floor=archive_importance_floor,
            stale_score_threshold=stale_score_threshold,
            merge_similarity_threshold=merge_similarity_threshold,
            cluster_min_size=cluster_min_size,
            dry_run=dry_run,
            max_compact_per_run=max_compact_per_run,
        )
        engine = CompactionEngine(config=config)
        report = engine.compact(self._store)

        if not dry_run and report.total_removed > 0:
            self._events.emit_sync("compacted", {
                "total_removed": report.total_removed,
                "archived": report.archived,
                "dedup_merged": report.dedup_merged,
                "stale_merged": report.stale_merged,
                "clusters_compacted": report.clusters_compacted,
            }, namespace=self._namespace)

        return report.to_dict()

    def cache_stats(self) -> dict[str, Any] | None:
        """Get embedding cache statistics. Returns None if caching disabled."""
        if self._embedding_cache is None:
            return None
        return self._embedding_cache.stats().to_dict()

    def cache_clear(self) -> int:
        """Clear the embedding cache. Returns -1 if cache is disabled."""
        if self._embedding_cache is None:
            return -1
        return self._embedding_cache.clear()

    # ── Versioning & Time-Travel ────────────────────────────

    @property
    def versioning(self) -> "VersioningEngine":
        """Access the versioning engine for time-travel queries."""
        return self._versioning

    def history(self, item_id: str) -> list["MemoryVersion"]:
        """Get the full version history of a memory item.

        Returns a list of MemoryVersion snapshots, oldest first.
        Each snapshot captures content, tags, importance, metadata,
        and a timestamp of when that version was recorded.

        Args:
            item_id: The memory item ID to look up.

        Returns:
            List of MemoryVersion objects, empty if item has no history.
        """
        return self._versioning.history(item_id)

    def get_version(self, item_id: str, version_number: int) -> "MemoryVersion | None":
        """Get a specific version of a memory item.

        Args:
            item_id: The memory item ID.
            version_number: Version number (1-based).

        Returns:
            MemoryVersion or None if not found.
        """
        return self._versioning.get_version(item_id, version_number)

    def diff(
        self,
        item_id: str,
        version_a: int,
        version_b: int,
    ) -> "VersionDiff | None":
        """Compare two versions of the same memory.

        Returns a VersionDiff with changed fields, or None if
        either version doesn't exist.

        Args:
            item_id: The memory item ID.
            version_a: First version number.
            version_b: Second version number.
        """
        return self._versioning.diff(item_id, version_a, version_b)

    def diff_latest(self, item_id: str) -> "VersionDiff | None":
        """Get the diff between the last two versions of a memory.

        Returns None if fewer than 2 versions exist.
        """
        return self._versioning.diff_latest(item_id)

    def recall_at(
        self,
        query: str,
        timestamp: float,
        *,
        top: int = 5,
        filter_tags: list[str] | None = None,
        min_score: float = 0.0,
    ) -> list[RecallResult]:
        """Time-travel recall: retrieve memories as they were at a given time.

        First performs a regular recall to find relevant items, then
        reconstructs each item to its state at the given timestamp.
        Items that didn't exist at that time are excluded.

        This enables answering questions like:
        - "What did I know about X before the meeting?"
        - "What were my preferences last week?"

        Args:
            query: Search query.
            timestamp: Unix timestamp for the point in time.
            top: Maximum results to return.
            filter_tags: Optional tag filter.
            min_score: Minimum relevance score.

        Returns:
            List of RecallResult with items reconstructed to their
            state at the given timestamp.
        """
        # First get current results
        current_results = self.recall(
            query, top=top, filter_tags=filter_tags,
            min_score=min_score,
        )

        # Reconstruct each result to its state at the given time
        time_travel_results: list[RecallResult] = []
        for r in current_results:
            version = self._versioning.version_at(r.item.id, timestamp)
            if version is not None:
                old_item = version.to_memory_item()
                # Keep the retrieval score from current search
                time_travel_results.append(RecallResult(
                    item=old_item,
                    score=r.score,
                    match_reason=r.match_reason,
                ))

        # Emit time-travel event
        if time_travel_results:
            self._events.emit_sync("time_traveled", {
                "query": query,
                "timestamp": timestamp,
                "results": len(time_travel_results),
            }, namespace=self._namespace)

        return sorted(time_travel_results, key=lambda x: x.score, reverse=True)[:top]

    def snapshot_at(self, timestamp: float) -> list["MemoryVersion"]:
        """Get the state of all memories at a given timestamp.

        Returns one version snapshot per item that existed at that time.
        Useful for auditing and debugging how memory evolved.

        Args:
            timestamp: Unix timestamp for the point in time.
        """
        return self._versioning.snapshot_at(timestamp)

    def rollback(
        self,
        item_id: str,
        version_number: int,
    ) -> "MemoryItem | None":
        """Roll back a memory item to a specific version.

        Restores the item's content, tags, importance, and metadata
        from the version snapshot. Records a new version with
        source="rollback".

        Args:
            item_id: The memory item to roll back.
            version_number: Target version number to restore.

        Returns:
            The restored MemoryItem, or None if version not found.
        """
        item = self._versioning.rollback(
            self._store, item_id, version_number,
            namespace=self._namespace,
        )
        if item is not None:
            self._retrieval.index(item)
            self._events.emit_sync("rolled_back", {
                "id": item_id,
                "to_version": version_number,
            }, namespace=self._namespace)
        return item

    def versioning_stats(self) -> dict[str, Any]:
        """Get versioning statistics.

        Returns total items tracked, total versions, avg versions per item.
        """
        return self._versioning.stats()

    def versioning_gc(self, max_age_days: float = 90.0, keep_latest: int = 3) -> int:
        """Garbage collect old versions.

        Removes versions older than max_age_days, but always keeps
        at least keep_latest versions per item.
        """
        return self._versioning.gc(max_age_days=max_age_days, keep_latest=keep_latest)


    # ── Multi-Agent Sharing ──────────────────────────────────

    def sharing(self) -> SharingEngine:
        """Access the sharing engine for multi-agent memory exchange."""
        return self._sharing

    def share_with(
        self,
        target_agent: str,
        *,
        scope: ShareScope = ShareScope.ITEMS,
        scope_key: str = "",
        permission: SharePermission = SharePermission.READ,
        expires_at: Optional[float] = None,
    ) -> ShareRequest:
        """Offer to share memories with another agent.

        Args:
            target_agent: ID of the agent to share with.
            scope: What to share (items, tag, or full namespace).
            scope_key: IDs (comma-sep), tag name, or namespace name.
            permission: READ, READ_WRITE, or ADMIN.
            expires_at: Optional TTL as Unix timestamp.

        Returns:
            The ShareRequest (PENDING status until accepted).
        """
        source = getattr(self, "_agent_id", "") or "default"
        return self._sharing.offer(
            source,
            target_agent,
            scope=scope,
            scope_key=scope_key,
            permission=permission,
            expires_at=expires_at,
        )

    def accept_share(self, share_id: str) -> ShareRequest:
        """Accept a pending share addressed to this agent.

        Args:
            share_id: The share request ID.

        Returns:
            The updated ShareRequest (ACCEPTED status).
        """
        agent = getattr(self, "_agent_id", "") or "default"
        return self._sharing.accept(share_id, agent)

    def reject_share(self, share_id: str) -> ShareRequest:
        """Reject a pending share addressed to this agent."""
        agent = getattr(self, "_agent_id", "") or "default"
        return self._sharing.reject(share_id, agent)

    def revoke_share(self, share_id: str) -> ShareRequest:
        """Revoke a share previously offered by this agent."""
        agent = getattr(self, "_agent_id", "") or "default"
        return self._sharing.revoke(share_id, agent)

    def export_shared(self, share_id: str) -> MemoryEnvelope:
        """Export memories for an accepted share as a portable envelope.

        The envelope contains the matching memories and can be
        transmitted over HTTP, files, or message queues.

        Args:
            share_id: An accepted share request ID.

        Returns:
            MemoryEnvelope with matching memories and checksum.
        """
        req = self._sharing.get(share_id)
        if req is None or req.status != ShareStatus.ACCEPTED:
            raise ValueError("Share not found or not accepted")

        # Resolve matching items
        items = self._resolve_share_scope(req)
        return self._sharing.export_envelope(share_id, items)

    def import_shared(self, envelope: MemoryEnvelope) -> list[MemoryItem]:
        """Import memories from a received envelope.

        Validates the envelope checksum, then learns each memory
        into the current namespace.

        Args:
            envelope: The received MemoryEnvelope.

        Returns:
            List of newly learned MemoryItems.
        """
        mem_dicts = SharingEngine.import_envelope(envelope)
        learned = []
        for md in mem_dicts:
            tags = md.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            importance = md.get("importance", 0.5)
            item = self.learn(
                md.get("content", ""),
                tags=tags,
                importance=float(importance),
            )
            learned.append(item)
        return learned

    def list_shares(
        self, agent: Optional[str] = None, status: Optional[ShareStatus] = None
    ) -> list[ShareRequest]:
        """List shares, optionally filtered by agent and status."""
        return self._sharing.list_shares(agent=agent, status=status)

    def sharing_stats(self) -> dict[str, Any]:
        """Get sharing statistics."""
        return self._sharing.stats()

    # ── Relevance Feedback ────────────────────────────────────

    def record_feedback(
        self,
        item_id: str,
        feedback: str,
        *,
        query: str = "",
        score_at_recall: float = 0.0,
        agent_id: str = "",
    ) -> FeedbackEntry:
        """Record relevance feedback for a recalled memory item.

        Args:
            item_id: ID of the memory item.
            feedback: "relevant" or "not-relevant".
            query: The query that triggered the recall (optional).
            score_at_recall: Relevance score at recall time (optional).
            agent_id: ID of the agent providing feedback (optional).

        Returns:
            The created FeedbackEntry.

        Raises:
            ValueError: If feedback value is invalid.
        """
        if feedback not in ("relevant", "not-relevant"):
            raise ValueError(
                f"Invalid feedback: {feedback!r}. Must be 'relevant' or 'not-relevant'"
            )
        entry = FeedbackEntry(
            item_id=item_id,
            feedback=feedback,
            query=query,
            score_at_recall=score_at_recall,
            agent_id=agent_id,
        )

        # Store feedback in the item's metadata for persistence
        item = self._store.get(item_id, namespace=self._namespace)
        if item is not None:
            fb_list = item.metadata.get("_feedback", [])
            fb_list.append(entry.to_dict())
            item.metadata["_feedback"] = fb_list

            # Adjust item importance based on feedback
            delta = 0.1 if feedback == "relevant" else -0.1
            item.importance = max(0.0, min(1.0, item.importance + delta))
            self._store.upsert(item, namespace=self._namespace)

            self._events.emit_sync("feedback", {
                "item_id": item_id,
                "feedback": feedback,
                "importance": item.importance,
            }, namespace=self._namespace)

        return entry

    def get_feedback(
        self, item_id: str | None = None, limit: int = 100
    ) -> list[FeedbackEntry]:
        """Get feedback entries, optionally filtered by item_id."""
        entries: list[FeedbackEntry] = []
        if item_id:
            item = self._store.get(item_id, namespace=self._namespace)
            if item and "_feedback" in item.metadata:
                entries = [FeedbackEntry.from_dict(d) for d in item.metadata["_feedback"]]
        else:
            all_items = self._store.list_all(namespace=self._namespace)
            for item in all_items:
                if "_feedback" in item.metadata:
                    entries.extend(
                        FeedbackEntry.from_dict(d) for d in item.metadata["_feedback"]
                    )
        entries.sort(key=lambda e: e.created_at)
        return entries[-limit:]

    def feedback_stats(self) -> FeedbackStats:
        """Get aggregate feedback statistics."""
        all_entries = self.get_feedback(limit=1_000_000)
        total = len(all_entries)
        if total == 0:
            return FeedbackStats()
        relevant = sum(1 for e in all_entries if e.feedback == "relevant")
        not_relevant = total - relevant
        items_with = len({e.item_id for e in all_entries})
        avg_score = (relevant - not_relevant) / total
        return FeedbackStats(
            total_feedback=total,
            relevant_count=relevant,
            not_relevant_count=not_relevant,
            items_with_feedback=items_with,
            avg_feedback_score=avg_score,
        )

    def _resolve_share_scope(self, req: ShareRequest) -> list[MemoryItem]:
        """Resolve memory items matching a share scope."""
        if req.scope == ShareScope.ITEMS:
            ids = [i.strip() for i in req.scope_key.split(",") if i.strip()]
            results = []
            for mid in ids:
                item = self._store.get(mid, namespace=self._namespace)
                if item is not None:
                    results.append(item)
            return results
        elif req.scope == ShareScope.TAG:
            all_items = self._store.list_all(namespace=self._namespace)
            return [i for i in all_items if req.scope_key in i.tags]
        elif req.scope == ShareScope.NAMESPACE:
            return self._store.list_all(namespace=self._namespace or req.scope_key)
        return []
