"""Versioning engine — high-level API for memory versioning and time-travel.

Provides the VersioningEngine that wraps a VersionStore and offers:
  - Automatic version recording on upsert
  - Version history for a memory
  - Version diff between two versions
  - Time-travel: recall memories as they were at a given timestamp
  - Version rollback

Supports both in-memory and persistent (SQLite) version stores.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from ..models import MemoryItem
from ..storage.base import StorageBackend
from .models import MemoryVersion, VersionDiff
from .persistent_store import PersistentVersionStore, SqliteVersionStore
from .store import VersionStore


class VersioningEngine:
    """High-level versioning and time-travel API.

    Wraps a StorageBackend and a VersionStore to provide transparent
    version tracking on every write, and time-travel queries.

    Supports both in-memory (default) and persistent (SQLite) backends.

    Usage::

        # In-memory (default)
        engine = VersioningEngine()

        # Persistent SQLite
        engine = VersioningEngine(persistent_path="/data/versions.db")

        engine.record_version(item, source="learn")

        # Time-travel: what memories existed 1 hour ago?
        snapshot = engine.snapshot_at(time.time() - 3600)

        # Version history
        versions = engine.history(item_id)

        # Diff between versions
        diff = engine.diff(item_id, version_a=1, version_b=3)
    """

    def __init__(
        self,
        store: Optional[Union[VersionStore, PersistentVersionStore]] = None,
        *,
        persistent_path: Optional[str] = None,
        max_versions_per_item: int = 100,
    ) -> None:
        if store is not None:
            self._vstore = store
        elif persistent_path is not None:
            self._vstore = SqliteVersionStore(
                persistent_path,
                max_versions_per_item=max_versions_per_item,
            )
        else:
            self._vstore = VersionStore(max_versions_per_item=max_versions_per_item)

    @property
    def version_store(self) -> Union[VersionStore, PersistentVersionStore]:
        """Access the underlying version store."""
        return self._vstore

    @property
    def is_persistent(self) -> bool:
        """Whether the version store is persistent (survives restarts)."""
        return isinstance(self._vstore, PersistentVersionStore)

    # ── Recording ───────────────────────────────────────────

    def record_version(
        self,
        item: MemoryItem,
        *,
        source: str = "upsert",
    ) -> MemoryVersion:
        """Record a new version of a memory item.

        Call this after every upsert to capture the state.
        Returns the created version snapshot.
        """
        return self._vstore.record(item, source=source)

    # ── History ─────────────────────────────────────────────

    def history(self, item_id: str) -> list[MemoryVersion]:
        """Get the full version history of a memory item, oldest first."""
        return self._vstore.list_versions(item_id)

    def get_version(self, item_id: str, version_number: int) -> Optional[MemoryVersion]:
        """Get a specific version of a memory item."""
        return self._vstore.get_version(item_id, version_number)

    def latest_version(self, item_id: str) -> Optional[MemoryVersion]:
        """Get the latest (current) version of a memory item."""
        return self._vstore.latest_version(item_id)

    # ── Diff ────────────────────────────────────────────────

    def diff(
        self,
        item_id: str,
        version_a: int,
        version_b: int,
    ) -> Optional[VersionDiff]:
        """Compute the diff between two versions of the same memory.

        Returns None if either version doesn't exist.
        """
        va = self._vstore.get_version(item_id, version_a)
        vb = self._vstore.get_version(item_id, version_b)

        if va is None or vb is None:
            return None

        return VersionDiff.between(va, vb)

    def diff_latest(self, item_id: str) -> Optional[VersionDiff]:
        """Diff between the second-to-last and the latest version.

        Returns None if fewer than 2 versions exist.
        """
        versions = self._vstore.list_versions(item_id)
        if len(versions) < 2:
            return None
        return VersionDiff.between(versions[-2], versions[-1])

    # ── Time-travel ─────────────────────────────────────────

    def snapshot_at(self, timestamp: float) -> list[MemoryVersion]:
        """Get the state of all memories at a given timestamp.

        Returns a list of version snapshots, one per item that existed
        at that time, representing their state at that exact moment.
        """
        return self._vstore.all_at(timestamp)

    def version_at(self, item_id: str, timestamp: float) -> Optional[MemoryVersion]:
        """Get the version of a specific item at a given timestamp."""
        return self._vstore.version_at(item_id, timestamp)

    def recall_at(
        self,
        items: list[MemoryItem],
        timestamp: float,
    ) -> list[MemoryItem]:
        """Filter and reconstruct items to their state at a given time.

        Given a list of current memory items, returns reconstructed MemoryItems
        reflecting their state at the given timestamp. Items that didn't exist
        at that time are excluded.

        This is used to support `MemOS.recall_at()`.
        """
        result: list[MemoryItem] = []
        for item in items:
            version = self._vstore.version_at(item.id, timestamp)
            if version is not None:
                result.append(version.to_memory_item())
        return result

    # ── Rollback ────────────────────────────────────────────

    def rollback(
        self,
        storage: StorageBackend,
        item_id: str,
        version_number: int,
        *,
        namespace: str = "",
    ) -> Optional[MemoryItem]:
        """Roll back a memory item to a specific version.

        Restores the item's state from the version snapshot and upserts
        it into the storage backend. Also records a new version with
        source="rollback".

        Returns the restored MemoryItem, or None if version not found.
        """
        version = self._vstore.get_version(item_id, version_number)
        if version is None:
            return None

        # Reconstruct the item from the version
        item = version.to_memory_item()

        # Upsert into storage
        storage.upsert(item, namespace=namespace)

        # Record as a new version (rollback)
        self._vstore.record(item, source=f"rollback:v{version_number}")

        return item

    # ── Stats & Maintenance ─────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Get versioning statistics."""
        return self._vstore.stats()

    def gc(self, max_age_days: float = 90.0, keep_latest: int = 3) -> int:
        """Garbage collect old versions. Returns count of removed versions."""
        return self._vstore.gc(max_age_days=max_age_days, keep_latest=keep_latest)

    def clear(self) -> None:
        """Clear all version data."""
        self._vstore.clear()
