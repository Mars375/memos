"""Core MemOS client — the main entry point."""

from __future__ import annotations

import time
from typing import Any, Optional

from .models import MemoryItem, RecallResult, MemoryStats, generate_id
from .retrieval.engine import RetrievalEngine
from .storage.base import StorageBackend
from .storage.chroma_backend import ChromaBackend
from .storage.memory_backend import InMemoryBackend
from .storage.qdrant_backend import QdrantBackend
from .storage.pinecone_backend import PineconeBackend
from .decay.engine import DecayEngine
from .sanitizer import MemorySanitizer
from .crypto import MemoryCrypto
from .storage.encrypted_backend import EncryptedStorageBackend
from .events import EventBus
from .versioning.engine import VersioningEngine
from .versioning.models import MemoryVersion, VersionDiff


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
        # Storage
        if backend == "chroma":
            store: StorageBackend = ChromaBackend(
                host=chroma_host, port=chroma_port
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

        # Event bus (real-time subscriptions)
        self._events = EventBus()

        # Versioning (time-travel)
        self._versioning = VersioningEngine(
            max_versions_per_item=kwargs.get("max_versions_per_item", 100),
        )

    @property
    def namespace(self) -> str:
        return self._namespace

    @namespace.setter
    def namespace(self, value: str) -> None:
        self._namespace = value or ""

    @property
    def events(self) -> EventBus:
        """Access the event bus for subscriptions."""
        return self._events

    def learn(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        importance: float = 0.5,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryItem:
        """Store a new memory."""
        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty")

        if self._sanitize:
            issues = MemorySanitizer.check(content)
            if issues:
                raise ValueError(f"Memory failed sanitization: {issues}")

        item = MemoryItem(
            id=generate_id(content),
            content=content.strip(),
            tags=tags or [],
            importance=max(0.0, min(1.0, importance)),
            metadata=metadata or {},
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
            self._events.emit_sync("batch_learned", {
                "count": len(valid_items),
                "skipped": result["skipped"],
                "errors": len(result["errors"]),
            }, namespace=self._namespace)

        return result

    def recall(
        self,
        query: str,
        top: int = 5,
        filter_tags: Optional[list[str]] = None,
        min_score: float = 0.0,
    ) -> list[RecallResult]:
        """Retrieve memories relevant to a query."""
        # Try retrieval engine for hybrid search (supports Qdrant native)
        engine_results = self._retrieval.search(
            query, top=top, filter_tags=filter_tags,
            namespace=self._namespace,
        )

        if engine_results:
            # Touch recalled items and emit events
            for r in engine_results[:top]:
                r.item.touch()
                self._store.upsert(r.item, namespace=self._namespace)
                self._events.emit_sync("recalled", {
                    "id": r.item.id,
                    "query": query,
                    "score": r.score,
                }, namespace=self._namespace)

            # Apply decay
            adjusted = []
            for r in engine_results[:top]:
                decayed = self._decay.adjusted_score(r.score, r.item)
                if decayed >= min_score:
                    r.score = decayed
                    adjusted.append(r)
            return sorted(adjusted, key=lambda x: x.score, reverse=True)[:top]

        # Fallback: basic keyword search
        all_items = self._store.list_all(namespace=self._namespace)

        if filter_tags:
            tag_set = set(t.lower() for t in filter_tags)
            all_items = [
                item for item in all_items
                if tag_set & set(t.lower() for t in item.tags)
            ]

        if not all_items:
            return []

        results = []
        for item in all_items:
            kw_score = self._retrieval._bm25(query, item.content)
            if kw_score > 0:
                results.append(RecallResult(
                    item=item,
                    score=kw_score,
                    match_reason="keyword",
                ))

        results.sort(key=lambda r: r.score, reverse=True)

        # Touch recalled items
        for r in results[:top]:
            r.item.touch()
            self._store.upsert(r.item, namespace=self._namespace)

            # Emit recall event for each touched item
            self._events.emit_sync("recalled", {
                "id": r.item.id,
                "query": query,
                "score": r.score,
            }, namespace=self._namespace)

        # Apply decay
        adjusted = []
        for r in results[:top]:
            decayed = self._decay.adjusted_score(r.score, r.item)
            if decayed >= min_score:
                r.score = decayed
                adjusted.append(r)

        return sorted(adjusted, key=lambda x: x.score, reverse=True)[:top]


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
            for item in candidates:
                self._store.delete(item.id, namespace=self._namespace)

            # Emit pruned event
            if candidates:
                self._events.emit_sync("pruned", {
                    "count": len(candidates),
                    "ids": [c.id for c in candidates],
                    "threshold": threshold,
                    "max_age_days": max_age_days,
                }, namespace=self._namespace)

        return candidates

    def forget(self, content_or_id: str) -> bool:
        """Delete a specific memory by content or ID."""
        if self._store.delete(content_or_id, namespace=self._namespace):
            self._events.emit_sync("forgotten", {"id": content_or_id}, namespace=self._namespace)
            return True
        content_id = generate_id(content_or_id)
        if self._store.delete(content_id, namespace=self._namespace):
            self._events.emit_sync("forgotten", {"id": content_id}, namespace=self._namespace)
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
            top_tags=top_tags,
        )

    def search(self, q: str, limit: int = 20) -> list[MemoryItem]:
        """Simple keyword search across all memories."""
        return self._store.search(q, limit=limit, namespace=self._namespace)

    def list_namespaces(self) -> list[str]:
        """List all non-default namespaces."""
        return self._store.list_namespaces()

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

