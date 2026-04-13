"""Version store — in-memory storage for memory version snapshots.

Each time a memory item is upserted, the VersionStore records a snapshot.
This enables time-travel queries: "what did this memory look like at time T?"
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from ..models import MemoryItem
from .models import MemoryVersion


class VersionStore:
    """Thread-safe in-memory version store.

    Stores version snapshots indexed by item_id. Each item has a monotonically
    increasing version counter. Supports:
      - Recording a new version on upsert
      - Retrieving a specific version
      - Listing all versions of an item
      - Time-travel: finding the version active at a given timestamp
      - Garbage collection of old versions
    """

    def __init__(self, max_versions_per_item: int = 100) -> None:
        self._versions: dict[str, list[MemoryVersion]] = {}
        self._max_versions = max_versions_per_item
        self._lock = threading.RLock()

    # ── Record ──────────────────────────────────────────────

    def record(
        self,
        item: MemoryItem,
        *,
        source: str = "upsert",
    ) -> MemoryVersion:
        """Record a new version snapshot for a memory item.

        Returns the created MemoryVersion.
        """
        with self._lock:
            versions = self._versions.setdefault(item.id, [])
            version_number = len(versions) + 1
            version = MemoryVersion.from_item(item, version_number, source=source)
            versions.append(version)

            # Garbage collect if too many versions
            if len(versions) > self._max_versions:
                self._versions[item.id] = versions[-self._max_versions :]

            return version

    # ── Query ───────────────────────────────────────────────

    def get_version(self, item_id: str, version_number: int) -> Optional[MemoryVersion]:
        """Get a specific version of a memory item."""
        with self._lock:
            versions = self._versions.get(item_id, [])
            for v in versions:
                if v.version_number == version_number:
                    return v
        return None

    def latest_version(self, item_id: str) -> Optional[MemoryVersion]:
        """Get the latest version of a memory item."""
        with self._lock:
            versions = self._versions.get(item_id, [])
            return versions[-1] if versions else None
        return None

    def list_versions(self, item_id: str) -> list[MemoryVersion]:
        """List all versions of a memory item, oldest first."""
        with self._lock:
            return list(self._versions.get(item_id, []))

    def version_count(self, item_id: str) -> int:
        """Number of versions recorded for an item."""
        with self._lock:
            return len(self._versions.get(item_id, []))

    # ── Time-travel ─────────────────────────────────────────

    def version_at(self, item_id: str, timestamp: float) -> Optional[MemoryVersion]:
        """Find the version of an item that was active at a given timestamp.

        Returns the latest version whose created_at is <= timestamp.
        Returns None if no version existed at that time.
        """
        with self._lock:
            versions = self._versions.get(item_id, [])
            if not versions:
                return None

            # Binary search for efficiency
            result = None
            for v in versions:
                if v.created_at <= timestamp:
                    result = v
                else:
                    break
            return result

    def all_at(self, timestamp: float) -> list[MemoryVersion]:
        """Get the state of all memories at a given timestamp.

        For each item_id, returns the version that was active at that time.
        Items that didn't exist yet are excluded.
        """
        with self._lock:
            result: list[MemoryVersion] = []
            for item_id in self._versions:
                v = self.version_at(item_id, timestamp)
                if v is not None:
                    result.append(v)
            return result

    # ── Maintenance ─────────────────────────────────────────

    def delete_versions(self, item_id: str) -> int:
        """Delete all versions for an item. Returns count deleted."""
        with self._lock:
            versions = self._versions.pop(item_id, [])
            return len(versions)

    def gc(self, max_age_days: float = 90.0, keep_latest: int = 3) -> int:
        """Garbage collect old versions.

        Removes versions older than max_age_days, but always keeps
        at least `keep_latest` most recent versions per item.

        Returns total versions removed.
        """
        cutoff = time.time() - (max_age_days * 86400)
        removed = 0

        with self._lock:
            for item_id in list(self._versions.keys()):
                versions = self._versions[item_id]
                if len(versions) <= keep_latest:
                    continue

                # Always keep the latest `keep_latest` versions
                latest = versions[-keep_latest:]
                # From the remaining older ones, keep those still within cutoff
                older = versions[:-keep_latest]
                kept_older = [v for v in older if v.created_at >= cutoff]
                removed += len(older) - len(kept_older)

                self._versions[item_id] = kept_older + latest

        return removed

    def stats(self) -> dict:
        """Return versioning statistics."""
        with self._lock:
            total_versions = sum(len(v) for v in self._versions.values())
            total_items = len(self._versions)
            avg_versions = total_versions / total_items if total_items else 0
            return {
                "total_items": total_items,
                "total_versions": total_versions,
                "avg_versions_per_item": round(avg_versions, 2),
                "max_versions_per_item": self._max_versions,
            }

    def clear(self) -> None:
        """Remove all versions (useful for testing)."""
        with self._lock:
            self._versions.clear()
