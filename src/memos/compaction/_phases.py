"""Compaction pipeline phase implementations."""

from __future__ import annotations

import time

from .._constants import SECONDS_PER_DAY
from ..models import MemoryItem
from ..storage.base import StorageBackend
from ._models import CompactionReport


class CompactionPhasesMixin:
    """Mutation phases for the compaction pipeline."""

    def _phase_dedup(
        self,
        store: StorageBackend,
        items: list[MemoryItem],
        report: CompactionReport,
        *,
        namespace: str = "",
    ) -> None:
        """Phase 1: Remove exact/near-duplicates."""
        if self._config.dry_run:
            groups = self._consolidation.find_duplicates(items)
            report.dedup_groups = len(groups)
            report.dedup_merged = sum(len(group.duplicates) for group in groups)
            return

        result = self._consolidation.consolidate(
            store,
            items=items,
            merge_content=False,
            dry_run=False,
            namespace=namespace,
        )
        report.dedup_groups = result.groups_found
        report.dedup_merged = result.space_freed

    def _phase_archive(
        self,
        store: StorageBackend,
        items: list[MemoryItem],
        report: CompactionReport,
        *,
        namespace: str = "",
    ) -> None:
        """Phase 2: Tag old low-relevance memories as archived."""
        candidates = self.find_archive_candidates(items)
        budget_used = report.archived + report.dedup_merged + report.stale_merged
        remaining_budget = self._config.max_compact_per_run - budget_used
        candidates = candidates[: max(0, remaining_budget)]

        if not candidates:
            return

        for item in candidates:
            if "archived" in item.tags:
                continue

            if self._config.dry_run:
                report.archived += 1
                report.archive_details.append(
                    {
                        "id": item.id,
                        "content": item.content[:100],
                        "age_days": round((time.time() - item.created_at) / SECONDS_PER_DAY, 1),
                        "original_importance": item.importance,
                    }
                )
                continue

            archived_tags = list(item.tags) + ["archived"]
            archived_meta = dict(item.metadata or {})
            archived_meta["archived_at"] = time.time()
            archived_meta["original_importance"] = item.importance

            archived_item = MemoryItem(
                id=item.id,
                content=item.content,
                tags=archived_tags,
                importance=0.0,
                created_at=item.created_at,
                accessed_at=item.accessed_at,
                access_count=item.access_count,
                metadata=archived_meta,
            )
            store.upsert(archived_item, namespace=namespace)

            report.archived += 1
            report.archive_details.append(
                {
                    "id": item.id,
                    "content": item.content[:100],
                    "age_days": round((time.time() - item.created_at) / SECONDS_PER_DAY, 1),
                    "original_importance": archived_meta["original_importance"],
                }
            )

    def _phase_stale_merge(
        self,
        store: StorageBackend,
        items: list[MemoryItem],
        report: CompactionReport,
        *,
        namespace: str = "",
    ) -> None:
        """Phase 3: Merge groups of stale, semantically related memories."""
        groups = self.find_stale_groups(items)
        budget_used = report.archived + report.dedup_merged + report.stale_merged

        for group in groups:
            if budget_used >= self._config.max_compact_per_run:
                break

            merged = self._merge_stale_group(group.memories)

            if not self._config.dry_run:
                store.upsert(merged, namespace=namespace)
                for memory in group.memories:
                    if memory.id != merged.id:
                        store.delete(memory.id, namespace=namespace)

            report.stale_groups += 1
            report.stale_merged += len(group.memories) - 1
            report.total_added += 1
            budget_used += len(group.memories) - 1

    def _phase_cluster_compact(
        self,
        store: StorageBackend,
        items: list[MemoryItem],
        report: CompactionReport,
        *,
        namespace: str = "",
    ) -> None:
        """Phase 4: Compress large tag-based clusters."""
        by_tag: dict[str, list[MemoryItem]] = {}
        for item in items:
            if "archived" in item.tags:
                continue
            for tag in item.tags:
                by_tag.setdefault(tag, []).append(item)

        budget_used = report.archived + report.dedup_merged + report.stale_merged

        for tag, tag_items in by_tag.items():
            if len(tag_items) < self._config.cluster_min_size * 2:
                continue
            if budget_used >= self._config.max_compact_per_run:
                break

            tag_items.sort(
                key=lambda memory: self._decay.adjusted_score(0.5, memory),
                reverse=True,
            )

            keep_count = max(self._config.cluster_min_size, len(tag_items) // 3)
            to_compress = tag_items[keep_count:]

            if len(to_compress) < self._config.cluster_min_size:
                continue

            summary = self._create_cluster_summary(tag, to_compress)

            if not self._config.dry_run:
                store.upsert(summary, namespace=namespace)
                for memory in to_compress:
                    if memory.id != summary.id:
                        store.delete(memory.id, namespace=namespace)

            report.clusters_compacted += 1
            report.total_removed += len(to_compress)
            report.total_added += 1
            budget_used += len(to_compress)
            report.cluster_details.append(
                {
                    "tag": tag,
                    "cluster_size": len(tag_items),
                    "kept": keep_count,
                    "compressed": len(to_compress),
                    "summary_preview": summary.content[:150],
                }
            )


__all__ = ["CompactionPhasesMixin"]
