"""Persistent version store — abstract base + SQLite implementation.

Provides a pluggable architecture for storing memory version snapshots
persistently. The default SQLite implementation is zero-dependency
(Python stdlib), works on ARM64, and is thread-safe.

Usage::

    from memos.versioning.persistent_store import SqliteVersionStore

    store = SqliteVersionStore("/data/memos/versions.db")
    version = store.record(item, source="learn")
    history = store.list_versions(item.id)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ..models import MemoryItem
from .models import MemoryVersion


class PersistentVersionStore(ABC):
    """Abstract interface for persistent version storage.

    All implementations must be thread-safe and support the same
    query patterns as the in-memory VersionStore.
    """

    @abstractmethod
    def record(self, item: MemoryItem, *, source: str = "upsert") -> MemoryVersion:
        """Record a new version snapshot."""

    @abstractmethod
    def get_version(self, item_id: str, version_number: int) -> Optional[MemoryVersion]:
        """Get a specific version of a memory item."""

    @abstractmethod
    def latest_version(self, item_id: str) -> Optional[MemoryVersion]:
        """Get the latest version of a memory item."""

    @abstractmethod
    def list_versions(self, item_id: str) -> list[MemoryVersion]:
        """List all versions of a memory item, oldest first."""

    @abstractmethod
    def version_count(self, item_id: str) -> int:
        """Number of versions recorded for an item."""

    @abstractmethod
    def version_at(self, item_id: str, timestamp: float) -> Optional[MemoryVersion]:
        """Find the version active at a given timestamp."""

    @abstractmethod
    def all_at(self, timestamp: float) -> list[MemoryVersion]:
        """Get the state of all memories at a given timestamp."""

    @abstractmethod
    def delete_versions(self, item_id: str) -> int:
        """Delete all versions for an item. Returns count deleted."""

    @abstractmethod
    def gc(self, max_age_days: float = 90.0, keep_latest: int = 3) -> int:
        """Garbage collect old versions."""

    @abstractmethod
    def stats(self) -> dict:
        """Return versioning statistics."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all versions."""


class SqliteVersionStore(PersistentVersionStore):
    """SQLite-backed persistent version store.

    Zero external dependencies (uses Python stdlib sqlite3).
    Thread-safe via connection-per-thread with WAL mode.

    Args:
        path: Path to the SQLite database file. Parent dirs created if needed.
        max_versions_per_item: Max versions to keep per item before auto-GC.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_versions_per_item: int = 100,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_versions = max_versions_per_item
        self._lock = threading.Lock()

        # Initialize schema
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS versions (
                    item_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    version_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 0.5,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT 'upsert',
                    PRIMARY KEY (item_id, version_number)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_versions_item_created
                ON versions (item_id, created_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_versions_created
                ON versions (created_at)
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection (thread-safe pattern)."""
        conn = sqlite3.connect(str(self._path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_version(self, row: sqlite3.Row) -> MemoryVersion:
        """Convert a database row to a MemoryVersion."""
        return MemoryVersion(
            version_id=row["version_id"],
            item_id=row["item_id"],
            version_number=row["version_number"],
            content=row["content"],
            tags=json.loads(row["tags_json"]),
            importance=row["importance"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
            source=row["source"],
        )

    def _item_to_row_values(self, item: MemoryItem, version_number: int, source: str, now: float) -> tuple:
        """Convert an item + version info to row values for INSERT."""
        return (
            item.id,
            version_number,
            f"{item.id}#{version_number}",
            item.content,
            json.dumps(item.tags),
            item.importance,
            json.dumps(item.metadata),
            now,
            source,
        )

    # ── Record ──────────────────────────────────────────────

    def record(self, item: MemoryItem, *, source: str = "upsert") -> MemoryVersion:
        """Record a new version snapshot for a memory item."""
        with self._lock:
            with self._connect() as conn:
                # Get current version count
                row = conn.execute(
                    "SELECT MAX(version_number) as max_v FROM versions WHERE item_id = ?",
                    (item.id,),
                ).fetchone()
                version_number = (row["max_v"] or 0) + 1
                now = time.time()

                values = self._item_to_row_values(item, version_number, source, now)
                conn.execute(
                    """INSERT INTO versions
                       (item_id, version_number, version_id, content,
                        tags_json, importance, metadata_json, created_at, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                conn.commit()

                # Auto-GC if too many versions
                count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM versions WHERE item_id = ?",
                    (item.id,),
                ).fetchone()["cnt"]
                if count > self._max_versions:
                    excess = count - self._max_versions
                    conn.execute(
                        """DELETE FROM versions
                           WHERE item_id = ? AND version_number IN (
                               SELECT version_number FROM versions
                               WHERE item_id = ?
                               ORDER BY version_number ASC
                               LIMIT ?
                           )""",
                        (item.id, item.id, excess),
                    )
                    conn.commit()

                return MemoryVersion(
                    version_id=f"{item.id}#{version_number}",
                    item_id=item.id,
                    version_number=version_number,
                    content=item.content,
                    tags=list(item.tags),
                    importance=item.importance,
                    metadata=dict(item.metadata),
                    created_at=now,
                    source=source,
                )

    # ── Query ───────────────────────────────────────────────

    def get_version(self, item_id: str, version_number: int) -> Optional[MemoryVersion]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM versions WHERE item_id = ? AND version_number = ?",
                (item_id, version_number),
            ).fetchone()
            return self._row_to_version(row) if row else None

    def latest_version(self, item_id: str) -> Optional[MemoryVersion]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM versions WHERE item_id = ? ORDER BY version_number DESC LIMIT 1",
                (item_id,),
            ).fetchone()
            return self._row_to_version(row) if row else None

    def list_versions(self, item_id: str) -> list[MemoryVersion]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM versions WHERE item_id = ? ORDER BY version_number ASC",
                (item_id,),
            ).fetchall()
            return [self._row_to_version(r) for r in rows]

    def version_count(self, item_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM versions WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            return row["cnt"]

    # ── Time-travel ─────────────────────────────────────────

    def version_at(self, item_id: str, timestamp: float) -> Optional[MemoryVersion]:
        """Find the version that was active at the given timestamp."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM versions
                   WHERE item_id = ? AND created_at <= ?
                   ORDER BY version_number DESC LIMIT 1""",
                (item_id, timestamp),
            ).fetchone()
            return self._row_to_version(row) if row else None

    def all_at(self, timestamp: float) -> list[MemoryVersion]:
        """Get the state of all memories at a given timestamp."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT v.* FROM versions v
                   INNER JOIN (
                       SELECT item_id, MAX(version_number) as max_v
                       FROM versions
                       WHERE created_at <= ?
                       GROUP BY item_id
                   ) latest ON v.item_id = latest.item_id
                           AND v.version_number = latest.max_v""",
                (timestamp,),
            ).fetchall()
            return [self._row_to_version(r) for r in rows]

    # ── Maintenance ─────────────────────────────────────────

    def delete_versions(self, item_id: str) -> int:
        with self._lock:
            with self._connect() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM versions WHERE item_id = ?",
                    (item_id,),
                ).fetchone()["cnt"]
                conn.execute("DELETE FROM versions WHERE item_id = ?", (item_id,))
                conn.commit()
                return count

    def gc(self, max_age_days: float = 90.0, keep_latest: int = 3) -> int:
        cutoff = time.time() - (max_age_days * 86400)
        with self._lock:
            with self._connect() as conn:
                items = conn.execute(
                    """SELECT item_id, COUNT(*) as cnt
                       FROM versions
                       GROUP BY item_id
                       HAVING cnt > ?""",
                    (keep_latest,),
                ).fetchall()

                removed = 0
                for item_row in items:
                    item_id = item_row["item_id"]
                    result = conn.execute(
                        """DELETE FROM versions
                           WHERE item_id = ?
                             AND version_number NOT IN (
                               SELECT version_number FROM versions
                               WHERE item_id = ?
                               ORDER BY version_number DESC
                               LIMIT ?
                             )
                             AND created_at < ?""",
                        (item_id, item_id, keep_latest, cutoff),
                    )
                    removed += result.rowcount

                conn.commit()
                return removed

    def stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM versions").fetchone()["cnt"]
            items = conn.execute("SELECT COUNT(DISTINCT item_id) as cnt FROM versions").fetchone()["cnt"]
            avg = total / items if items else 0
            return {
                "total_items": items,
                "total_versions": total,
                "avg_versions_per_item": round(avg, 2),
                "max_versions_per_item": self._max_versions,
                "backend": "sqlite",
                "path": str(self._path),
            }

    def clear(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM versions")
                conn.commit()
