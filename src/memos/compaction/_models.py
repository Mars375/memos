"""Compaction configuration and report models."""

from __future__ import annotations

from dataclasses import dataclass, field

from .._constants import (
    DEFAULT_ARCHIVE_AGE_DAYS,
    DEFAULT_ARCHIVE_IMPORTANCE_FLOOR,
    DEFAULT_CLUSTER_MAX_SIZE,
    DEFAULT_CLUSTER_MIN_SIZE,
    DEFAULT_MAX_COMPACT_PER_RUN,
    DEFAULT_MERGE_SIMILARITY_THRESHOLD,
    DEFAULT_STALE_SCORE_THRESHOLD,
)
from ..models import MemoryItem


@dataclass
class CompactionConfig:
    """Configuration for memory compaction."""

    archive_age_days: float = DEFAULT_ARCHIVE_AGE_DAYS
    archive_importance_floor: float = DEFAULT_ARCHIVE_IMPORTANCE_FLOOR
    stale_score_threshold: float = DEFAULT_STALE_SCORE_THRESHOLD
    merge_similarity_threshold: float = DEFAULT_MERGE_SIMILARITY_THRESHOLD
    cluster_min_size: int = DEFAULT_CLUSTER_MIN_SIZE
    cluster_max_size: int = DEFAULT_CLUSTER_MAX_SIZE
    dry_run: bool = False
    max_compact_per_run: int = DEFAULT_MAX_COMPACT_PER_RUN


@dataclass
class ClusterInfo:
    """A group of related memories identified for compaction."""

    memories: list[MemoryItem]
    avg_importance: float
    avg_age_days: float
    avg_score: float
    tag: str = ""


@dataclass
class CompactionReport:
    """Result of a compaction run."""

    archived: int = 0
    archive_details: list[dict] = field(default_factory=list)
    stale_merged: int = 0
    stale_groups: int = 0
    clusters_compacted: int = 0
    cluster_details: list[dict] = field(default_factory=list)
    dedup_groups: int = 0
    dedup_merged: int = 0
    total_removed: int = 0
    total_added: int = 0
    net_delta: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Return a compact serializable report."""
        return {
            "archived": self.archived,
            "stale_merged": self.stale_merged,
            "stale_groups": self.stale_groups,
            "clusters_compacted": self.clusters_compacted,
            "dedup_groups": self.dedup_groups,
            "dedup_merged": self.dedup_merged,
            "total_removed": self.total_removed,
            "total_added": self.total_added,
            "net_delta": self.net_delta,
            "duration_seconds": round(self.duration_seconds, 3),
            "archive_details": self.archive_details[:10],
            "cluster_details": self.cluster_details[:10],
        }


__all__ = ["ClusterInfo", "CompactionConfig", "CompactionReport"]
