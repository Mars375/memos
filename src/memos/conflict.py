"""Memory Conflict Resolution — detect and resolve conflicts between MemOS instances.

When two agents each maintain their own MemOS store and synchronise,
conflicts can arise when the same memory has been modified differently
on each side. This module detects those conflicts and provides
configurable resolution strategies.

Usage::

    from memos.conflict import ConflictDetector, ResolutionStrategy

    detector = ConflictDetector()
    conflicts = detector.detect(local_memos, remote_envelope)
    resolved = detector.resolve(conflicts, strategy=ResolutionStrategy.MERGE)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .core import MemOS
from .models import MemoryItem
from .sharing.models import MemoryEnvelope


class ConflictType(Enum):
    """Type of conflict detected."""

    CONTENT_CHANGED = "content_changed"
    TAGS_CHANGED = "tags_changed"
    IMPORTANCE_CHANGED = "importance_changed"
    METADATA_CHANGED = "metadata_changed"
    DELETED_MODIFIED = "deleted_modified"


class ResolutionStrategy(Enum):
    """Strategy for resolving conflicts."""

    LOCAL_WINS = "local_wins"
    REMOTE_WINS = "remote_wins"
    MERGE = "merge"
    MANUAL = "manual"


@dataclass
class Conflict:
    """A single detected conflict between local and remote memory versions."""

    memory_id: str
    conflict_types: list[ConflictType] = field(default_factory=list)
    local_version: Optional[dict[str, Any]] = None
    remote_version: Optional[dict[str, Any]] = None
    resolution: Optional[ResolutionStrategy] = None
    resolved_version: Optional[dict[str, Any]] = None

    # Diff details
    local_content: str = ""
    remote_content: str = ""
    local_tags: list[str] = field(default_factory=list)
    remote_tags: list[str] = field(default_factory=list)
    local_importance: float = 0.0
    remote_importance: float = 0.0
    local_metadata: dict[str, Any] = field(default_factory=dict)
    remote_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "conflict_types": [ct.value for ct in self.conflict_types],
            "local_content": self.local_content,
            "remote_content": self.remote_content,
            "local_tags": self.local_tags,
            "remote_tags": self.remote_tags,
            "local_importance": self.local_importance,
            "remote_importance": self.remote_importance,
            "local_metadata": self.local_metadata,
            "remote_metadata": self.remote_metadata,
            "resolution": self.resolution.value if self.resolution else None,
        }


@dataclass
class SyncReport:
    """Summary report from a sync check or apply operation."""

    total_remote: int = 0
    new_memories: int = 0
    unchanged: int = 0
    conflicts: list[Conflict] = field(default_factory=list)
    applied: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    _remote_envelope: Optional[MemoryEnvelope] = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_remote": self.total_remote,
            "new_memories": self.new_memories,
            "unchanged": self.unchanged,
            "conflict_count": len(self.conflicts),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "applied": self.applied,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class ConflictDetector:
    """Detects and resolves conflicts between local and remote memory stores.

    Conflict detection compares memories by ID:
    - If a remote memory ID doesn't exist locally → new memory (no conflict)
    - If both exist with identical content/tags/importance → unchanged
    - If both exist but differ → Conflict with specific ConflictType(s)

    Resolution strategies:
    - LOCAL_WINS: keep local version, discard remote changes
    - REMOTE_WINS: overwrite local with remote version
    - MERGE: union of tags, most recent content, max importance
    - MANUAL: report only, don't resolve (caller decides)
    """

    def __init__(self, content_similarity_threshold: float = 0.9) -> None:
        """Initialise the conflict detector.

        Args:
            content_similarity_threshold: Ratio below which content is
                considered a real change (0.0-1.0). Default 0.9 means
                a >=10% content difference counts as changed.
        """
        self.content_similarity_threshold = content_similarity_threshold

    # -- Detection --------------------------------------------------------

    def detect(
        self,
        local: MemOS,
        remote_envelope: MemoryEnvelope,
    ) -> SyncReport:
        """Detect conflicts between a local MemOS instance and a remote envelope.

        Args:
            local: The local MemOS instance.
            remote_envelope: Envelope containing remote memories.

        Returns:
            SyncReport with conflicts and statistics.
        """
        report = SyncReport(
            total_remote=len(remote_envelope.memories),
            _remote_envelope=remote_envelope,
        )

        for remote_dict in remote_envelope.memories:
            remote_id = remote_dict.get("id", "")
            if not remote_id:
                report.errors.append(f"Remote memory missing ID: {str(remote_dict)[:80]}")
                continue

            remote_item = self._dict_to_item(remote_dict)
            local_item = local._store.get(remote_id, namespace=local._namespace)

            if local_item is None:
                report.new_memories += 1
                continue

            conflict = self._compare(local_item, remote_item)
            if conflict is not None:
                report.conflicts.append(conflict)
            else:
                report.unchanged += 1

        return report

    def detect_from_dicts(
        self,
        local_items: list[MemoryItem],
        remote_dicts: list[dict[str, Any]],
    ) -> SyncReport:
        """Detect conflicts given lists of local items and remote dicts.

        Alternative entry point that doesn't require a live MemOS instance.

        Args:
            local_items: Local memory items.
            remote_dicts: Remote memories as dicts (from envelope).

        Returns:
            SyncReport with conflicts and statistics.
        """
        report = SyncReport(total_remote=len(remote_dicts))
        local_by_id: dict[str, MemoryItem] = {item.id: item for item in local_items}

        for remote_dict in remote_dicts:
            remote_id = remote_dict.get("id", "")
            if not remote_id:
                report.errors.append(f"Remote memory missing ID: {str(remote_dict)[:80]}")
                continue

            remote_item = self._dict_to_item(remote_dict)
            local_item = local_by_id.get(remote_id)

            if local_item is None:
                report.new_memories += 1
                continue

            conflict = self._compare(local_item, remote_item)
            if conflict is not None:
                report.conflicts.append(conflict)
            else:
                report.unchanged += 1

        return report

    # -- Resolution --------------------------------------------------------

    def resolve(
        self,
        conflicts: list[Conflict],
        strategy: ResolutionStrategy,
    ) -> list[Conflict]:
        """Apply a resolution strategy to a list of conflicts.

        For MERGE strategy:
        - Tags: union of local + remote tags
        - Content: whichever was modified most recently
        - Importance: max of local and remote
        - Metadata: merged dict (remote keys override local for same key)

        Args:
            conflicts: List of detected conflicts.
            strategy: Resolution strategy to apply.

        Returns:
            The same conflict list with resolution and resolved_version set.
        """
        for conflict in conflicts:
            conflict.resolution = strategy

            if strategy == ResolutionStrategy.LOCAL_WINS:
                conflict.resolved_version = dict(conflict.local_version or {})

            elif strategy == ResolutionStrategy.REMOTE_WINS:
                conflict.resolved_version = dict(conflict.remote_version or {})

            elif strategy == ResolutionStrategy.MERGE:
                conflict.resolved_version = self._merge(conflict)

            elif strategy == ResolutionStrategy.MANUAL:
                conflict.resolved_version = None  # Caller decides

        return conflicts

    def apply(
        self,
        local: MemOS,
        report: SyncReport,
        strategy: ResolutionStrategy = ResolutionStrategy.MERGE,
    ) -> SyncReport:
        """Apply resolved sync to the local MemOS instance.

        For each conflict: resolve according to strategy and upsert.
        For new memories (no conflict): learn them into the local store.

        Args:
            local: Local MemOS instance.
            report: SyncReport from detect(), containing envelope data.
            strategy: Resolution strategy.

        Returns:
            Updated SyncReport with applied/skipped counts.
        """
        # Resolve conflicts first
        self.resolve(report.conflicts, strategy)

        # Apply conflict resolutions
        for conflict in report.conflicts:
            if conflict.resolved_version is None:
                report.skipped += 1
                continue

            try:
                resolved = self._dict_to_item(conflict.resolved_version)
                local._store.upsert(resolved, namespace=local._namespace)
                report.applied += 1
            except Exception as exc:
                report.errors.append(f"Failed to apply resolution for {conflict.memory_id}: {exc}")

        # Apply new memories (no conflict)
        if report._remote_envelope is not None:
            conflict_ids = {c.memory_id for c in report.conflicts}
            for remote_dict in report._remote_envelope.memories:
                rid = remote_dict.get("id", "")
                if rid and rid not in conflict_ids:
                    # Check it's truly new
                    existing = local._store.get(rid, namespace=local._namespace)
                    if existing is None:
                        try:
                            item = self._dict_to_item(remote_dict)
                            local._store.upsert(item, namespace=local._namespace)
                            report.applied += 1
                        except Exception as exc:
                            report.errors.append(f"Failed to import new memory {rid}: {exc}")
                    # else unchanged, already counted

        return report

    # -- Private helpers ----------------------------------------------------

    def _compare(self, local: MemoryItem, remote: MemoryItem) -> Optional[Conflict]:
        """Compare two memory items and return a Conflict if they differ."""
        conflict_types: list[ConflictType] = []

        # Content comparison
        local_content = (local.content or "").strip()
        remote_content = (remote.content or "").strip()
        content_changed = not self._content_similar(local_content, remote_content)

        # Tags comparison
        local_tags = sorted(local.tags or [])
        remote_tags = sorted(remote.tags or [])
        tags_changed = local_tags != remote_tags

        # Importance comparison (allow small floating-point tolerance)
        importance_changed = abs(local.importance - remote.importance) > 0.01

        # Metadata comparison
        local_meta = local.metadata or {}
        remote_meta = remote.metadata or {}
        metadata_changed = local_meta != remote_meta

        if content_changed:
            conflict_types.append(ConflictType.CONTENT_CHANGED)
        if tags_changed:
            conflict_types.append(ConflictType.TAGS_CHANGED)
        if importance_changed:
            conflict_types.append(ConflictType.IMPORTANCE_CHANGED)
        if metadata_changed:
            conflict_types.append(ConflictType.METADATA_CHANGED)

        if not conflict_types:
            return None  # Identical

        return Conflict(
            memory_id=local.id,
            conflict_types=conflict_types,
            local_version=self._item_to_simple_dict(local),
            remote_version=self._item_to_simple_dict(remote),
            local_content=local_content,
            remote_content=remote_content,
            local_tags=list(local_tags),
            remote_tags=list(remote_tags),
            local_importance=local.importance,
            remote_importance=remote.importance,
            local_metadata=dict(local_meta),
            remote_metadata=dict(remote_meta),
        )

    def _content_similar(self, a: str, b: str) -> bool:
        """Check if two strings are similar enough to be considered unchanged."""
        if a == b:
            return True
        if not a or not b:
            return False

        longer = max(len(a), len(b))
        shorter = min(len(a), len(b))
        length_ratio = shorter / longer

        if length_ratio < self.content_similarity_threshold:
            return False

        common = sum(1 for ca, cb in zip(a, b) if ca == cb)
        char_ratio = common / longer

        return char_ratio >= self.content_similarity_threshold

    @staticmethod
    def _merge(conflict: Conflict) -> dict[str, Any]:
        """Merge local and remote versions intelligently."""
        local_v = conflict.local_version or {}
        remote_v = conflict.remote_version or {}

        # Content: most recent wins
        local_time = local_v.get("accessed_at") or local_v.get("created_at") or 0
        remote_time = remote_v.get("accessed_at") or remote_v.get("created_at") or 0
        content = remote_v.get("content", "") if remote_time >= local_time else local_v.get("content", "")

        # Tags: union
        local_tags = set(local_v.get("tags", []))
        remote_tags = set(remote_v.get("tags", []))
        merged_tags = sorted(local_tags | remote_tags)

        # Importance: max
        merged_importance = max(
            local_v.get("importance", 0.0),
            remote_v.get("importance", 0.0),
        )

        # Metadata: merge (remote overrides local for same keys)
        merged_metadata = dict(local_v.get("metadata", {}))
        merged_metadata.update(remote_v.get("metadata", {}))

        return {
            "id": conflict.memory_id,
            "content": content,
            "tags": merged_tags,
            "importance": merged_importance,
            "metadata": merged_metadata,
            "created_at": min(
                local_v.get("created_at", float("inf")),
                remote_v.get("created_at", float("inf")),
            ),
            "accessed_at": max(local_time, remote_time),
            "access_count": max(
                local_v.get("access_count", 0),
                remote_v.get("access_count", 0),
            ),
            "relevance_score": max(
                local_v.get("relevance_score", 0.0),
                remote_v.get("relevance_score", 0.0),
            ),
            "ttl": local_v.get("ttl") or remote_v.get("ttl"),
        }

    @staticmethod
    def _dict_to_item(d: dict[str, Any]) -> MemoryItem:
        """Convert a dict to a MemoryItem."""
        return MemoryItem(
            id=d.get("id", ""),
            content=d.get("content", ""),
            tags=d.get("tags", []),
            importance=d.get("importance", 0.5),
            created_at=d.get("created_at", time.time()),
            accessed_at=d.get("accessed_at", time.time()),
            access_count=d.get("access_count", 0),
            relevance_score=d.get("relevance_score", 0.0),
            metadata=d.get("metadata", {}),
            ttl=d.get("ttl"),
        )

    @staticmethod
    def _item_to_simple_dict(item: MemoryItem) -> dict[str, Any]:
        """Convert a MemoryItem to a plain dict."""
        return {
            "id": item.id,
            "content": item.content,
            "tags": list(item.tags),
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
            "relevance_score": item.relevance_score,
            "metadata": dict(item.metadata) if item.metadata else {},
            "ttl": item.ttl,
        }
