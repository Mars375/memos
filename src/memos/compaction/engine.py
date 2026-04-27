"""Compaction engine compatibility facade."""

from __future__ import annotations

import time
from typing import Optional

from .._constants import DEFAULT_DECAY_RATE, DEFAULT_MAX_MEMORIES
from ..consolidation.engine import ConsolidationEngine
from ..decay.engine import DecayEngine
from ..storage.base import StorageBackend
from ._discovery import CompactionDiscoveryMixin
from ._helpers import CompactionHelperMixin
from ._models import ClusterInfo, CompactionConfig, CompactionReport
from ._phases import CompactionPhasesMixin


class CompactionEngine(
    CompactionDiscoveryMixin,
    CompactionPhasesMixin,
    CompactionHelperMixin,
):
    """Full lifecycle compaction for memory stores.

    Pipeline:
    1. Dedup — find and merge exact/near-duplicates (via ConsolidationEngine)
    2. Archive — move very old, low-relevance memories to archive tag
    3. Stale merge — group and merge memories with low decay scores
    4. Cluster compact — compress large clusters of related memories
    """

    def __init__(
        self,
        config: Optional[CompactionConfig] = None,
        *,
        decay_rate: float = DEFAULT_DECAY_RATE,
        max_memories: int = DEFAULT_MAX_MEMORIES,
    ) -> None:
        self._config = config or CompactionConfig()
        self._decay = DecayEngine(rate=decay_rate, max_memories=max_memories)
        self._consolidation = ConsolidationEngine(
            similarity_threshold=self._config.merge_similarity_threshold,
        )

    def compact(self, store: StorageBackend, *, namespace: str = "") -> CompactionReport:
        """Run the full compaction pipeline."""
        start = time.time()
        report = CompactionReport()
        items = store.list_all(namespace=namespace)

        if len(items) < 2:
            report.duration_seconds = time.time() - start
            return report

        self._phase_dedup(store, items, report, namespace=namespace)

        if not self._config.dry_run and (report.dedup_groups > 0 or report.dedup_merged > 0):
            items = store.list_all(namespace=namespace)
        self._phase_archive(store, items, report, namespace=namespace)

        if not self._config.dry_run and report.archived > 0:
            items = store.list_all(namespace=namespace)
        self._phase_stale_merge(store, items, report, namespace=namespace)

        if not self._config.dry_run and (report.stale_groups > 0 or report.stale_merged > 0):
            items = store.list_all(namespace=namespace)
        self._phase_cluster_compact(store, items, report, namespace=namespace)

        report.total_removed = report.archived + report.dedup_merged + report.stale_merged
        report.net_delta = report.total_added - report.total_removed
        report.duration_seconds = time.time() - start

        return report


__all__ = [
    "ClusterInfo",
    "CompactionConfig",
    "CompactionEngine",
    "CompactionReport",
]
