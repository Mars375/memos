"""Versioning and time-travel facade for MemOS."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import MemoryItem, RecallResult

if TYPE_CHECKING:
    from .versioning.engine import VersioningEngine
    from .versioning.models import MemoryVersion, VersionDiff


class VersioningFacade:
    """Mixin exposing versioning/time-travel APIs on MemOS."""

    _versioning: "VersioningEngine"
    _namespace: str
    _store: Any
    _retrieval: Any
    _events: Any

    def _check_acl(self, permission: str) -> None:
        """ACL guard — resolved at runtime on the MemOS composite."""

    @property
    def versioning(self) -> "VersioningEngine":
        """Access the versioning engine for time-travel queries."""
        return self._versioning

    def history(self, item_id: str) -> list["MemoryVersion"]:
        """Get the full version history of a memory item."""
        self._check_acl("read")
        return self._versioning.history(item_id)

    def get_version(self, item_id: str, version_number: int) -> "MemoryVersion | None":
        """Get a specific version of a memory item."""
        self._check_acl("read")
        return self._versioning.get_version(item_id, version_number)

    def diff(self, item_id: str, version_a: int, version_b: int) -> "VersionDiff | None":
        """Compare two versions of the same memory."""
        self._check_acl("read")
        return self._versioning.diff(item_id, version_a, version_b)

    def diff_latest(self, item_id: str) -> "VersionDiff | None":
        """Get the diff between the last two versions of a memory."""
        self._check_acl("read")
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
        """Time-travel recall: retrieve memories as they were at a given time."""
        self._check_acl("read")
        current_results = self.recall(
            query,
            top=top,
            filter_tags=filter_tags,
            min_score=min_score,
        )

        time_travel_results: list[RecallResult] = []
        for r in current_results:
            version = self._versioning.version_at(r.item.id, timestamp)
            if version is not None:
                old_item = version.to_memory_item()
                time_travel_results.append(
                    RecallResult(
                        item=old_item,
                        score=r.score,
                        match_reason=r.match_reason,
                    )
                )

        if time_travel_results:
            self._events.emit_sync(
                "time_traveled",
                {
                    "query": query,
                    "timestamp": timestamp,
                    "results": len(time_travel_results),
                },
                namespace=self._namespace,
            )

        return sorted(time_travel_results, key=lambda x: x.score, reverse=True)[:top]

    def snapshot_at(self, timestamp: float) -> list["MemoryVersion"]:
        """Get the state of all memories at a given timestamp."""
        self._check_acl("read")
        return self._versioning.snapshot_at(timestamp)

    def rollback(self, item_id: str, version_number: int) -> "MemoryItem | None":
        """Roll back a memory item to a specific version."""
        self._check_acl("write")
        item = self._versioning.rollback(
            self._store,
            item_id,
            version_number,
            namespace=self._namespace,
        )
        if item is not None:
            self._retrieval.index(item)
            self._events.emit_sync(
                "rolled_back",
                {
                    "id": item_id,
                    "to_version": version_number,
                },
                namespace=self._namespace,
            )
        return item

    def versioning_stats(self) -> dict[str, Any]:
        """Get versioning statistics."""
        self._check_acl("read")
        return self._versioning.stats()

    def versioning_gc(self, max_age_days: float = 90.0, keep_latest: int = 3) -> int:
        """Garbage collect old versions."""
        self._check_acl("delete")
        return self._versioning.gc(max_age_days=max_age_days, keep_latest=keep_latest)
