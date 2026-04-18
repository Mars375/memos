"""Maintenance facade for MemOS — prune, consolidate, compact, compress, cache."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._constants import (
    DEFAULT_ARCHIVE_AGE_DAYS,
    DEFAULT_ARCHIVE_IMPORTANCE_FLOOR,
    DEFAULT_CLUSTER_MIN_SIZE,
    DEFAULT_CONSOLIDATION_THRESHOLD,
    DEFAULT_MAX_COMPACT_PER_RUN,
    DEFAULT_MERGE_SIMILARITY_THRESHOLD,
    DEFAULT_PRUNE_MAX_AGE_DAYS,
    DEFAULT_PRUNE_THRESHOLD,
    DEFAULT_STALE_SCORE_THRESHOLD,
)
from .models import MemoryItem

if TYPE_CHECKING:
    from .compression import CompressionResult
    from .consolidation.async_engine import AsyncConsolidationHandle
    from .consolidation.engine import ConsolidationResult


class MaintenanceFacade:
    """Mixin exposing maintenance APIs on MemOS.

    Covers pruning, consolidation, compaction, compression, and cache
    management operations.
    """

    _store: Any
    _namespace: str
    _decay: Any
    _events: Any
    _embedding_cache: Any
    _retrieval: Any

    # ── Pruning ────────────────────────────────────────────

    def prune(
        self,
        threshold: float = DEFAULT_PRUNE_THRESHOLD,
        max_age_days: float = DEFAULT_PRUNE_MAX_AGE_DAYS,
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
                self._events.emit_sync(
                    "pruned",
                    {
                        "count": len(candidates),
                        "ids": [c.id for c in candidates],
                        "threshold": threshold,
                        "max_age_days": max_age_days,
                        "tags": tag_union,
                    },
                    namespace=self._namespace,
                )

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
                self._events.emit_sync(
                    "expired_pruned",
                    {
                        "count": len(expired),
                        "ids": [i.id for i in expired],
                    },
                    namespace=self._namespace,
                )

        return expired

    # ── Consolidation ──────────────────────────────────────

    def consolidate(
        self,
        *,
        similarity_threshold: float = DEFAULT_CONSOLIDATION_THRESHOLD,
        merge_content: bool = False,
        dry_run: bool = False,
    ) -> "ConsolidationResult":
        """Find and merge semantically similar memories."""
        from .consolidation.engine import ConsolidationEngine

        engine = ConsolidationEngine(similarity_threshold=similarity_threshold)
        result = engine.consolidate(self._store, merge_content=merge_content, dry_run=dry_run)

        if not dry_run and result.memories_merged > 0:
            self._events.emit_sync(
                "consolidated",
                {
                    "groups_found": result.groups_found,
                    "memories_merged": result.memories_merged,
                },
                namespace=self._namespace,
            )

        return result

    # ── Async consolidation ───────────────────────────────────

    async def consolidate_async(
        self,
        *,
        similarity_threshold: float = DEFAULT_CONSOLIDATION_THRESHOLD,
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
        archive_age_days: float = DEFAULT_ARCHIVE_AGE_DAYS,
        archive_importance_floor: float = DEFAULT_ARCHIVE_IMPORTANCE_FLOOR,
        stale_score_threshold: float = DEFAULT_STALE_SCORE_THRESHOLD,
        merge_similarity_threshold: float = DEFAULT_MERGE_SIMILARITY_THRESHOLD,
        cluster_min_size: int = DEFAULT_CLUSTER_MIN_SIZE,
        dry_run: bool = False,
        max_compact_per_run: int = DEFAULT_MAX_COMPACT_PER_RUN,
    ) -> dict[str, Any]:
        """Run memory compaction: dedup + archive + merge stale + compress clusters.

        Safe to run periodically (e.g., daily cron). Use dry_run=True to preview.

        Returns:
            dict with detailed compaction report.
        """
        from .compaction.engine import CompactionConfig, CompactionEngine

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
            self._events.emit_sync(
                "compacted",
                {
                    "total_removed": report.total_removed,
                    "archived": report.archived,
                    "dedup_merged": report.dedup_merged,
                    "stale_merged": report.stale_merged,
                    "clusters_compacted": report.clusters_compacted,
                },
                namespace=self._namespace,
            )

        return report.to_dict()

    # ── Embedding cache ──────────────────────────────────────

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

    # ── Compression ──────────────────────────────────────────

    def compress(
        self,
        *,
        threshold: float = 0.1,
        dry_run: bool = False,
    ) -> "CompressionResult":
        """Compress very low-importance memories into aggregate summaries."""
        from .compression import MemoryCompressor

        compressor = MemoryCompressor()
        items = self._store.list_all(namespace=self._namespace)
        result = compressor.compress(items, threshold=threshold)

        if not dry_run:
            for item_id in result.deleted_ids:
                self._store.delete(item_id, namespace=self._namespace)
            for summary in result.summaries:
                self._store.upsert(summary, namespace=self._namespace)
                self._retrieval.index(summary)

            if result.summary_count:
                self._events.emit_sync(
                    "compressed",
                    {
                        "compressed_count": result.compressed_count,
                        "summary_count": result.summary_count,
                        "freed_bytes": result.freed_bytes,
                        "threshold": threshold,
                    },
                    namespace=self._namespace,
                )

        return result
