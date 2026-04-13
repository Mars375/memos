"""MinerCache — SQLite-backed incremental mining cache (P19).

Tracks which files have been mined and their SHA-256 fingerprint.
When the same file is mined again with an identical hash, it is skipped.

Usage:
    from memos.ingest.cache import MinerCache
    cache = MinerCache()                   # default: ~/.memos/mine-cache.db
    cache = MinerCache(":memory:")         # in-memory, useful for tests
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class MinerCache:
    """Persistent cache for incremental file mining.

    Schema (mine_cache):
        path         TEXT PRIMARY KEY  — absolute resolved file path
        sha256       TEXT NOT NULL     — 64-char SHA-256 hex of file bytes
        mined_at     REAL NOT NULL     — Unix timestamp of last mine
        memory_ids   TEXT NOT NULL     — JSON list of MemoryItem IDs created
        chunk_hashes TEXT NOT NULL     — JSON list of chunk content hashes (for --diff)
    """

    _CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS mine_cache (
        path         TEXT PRIMARY KEY,
        sha256       TEXT NOT NULL,
        mined_at     REAL NOT NULL,
        memory_ids   TEXT NOT NULL DEFAULT '[]',
        chunk_hashes TEXT NOT NULL DEFAULT '[]'
    )
    """

    def __init__(self, db_path: str | Path = "~/.memos/mine-cache.db") -> None:
        if str(db_path) == ":memory:":
            self._db_path: Path | None = None
            self._conn = sqlite3.connect(":memory:")
        else:
            self._db_path = Path(db_path).expanduser().resolve()
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute(self._CREATE_SQL)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def is_fresh(self, path: str | Path, sha256: str) -> bool:
        """Return True if *path* was already mined with this exact *sha256*."""
        row = self._conn.execute("SELECT sha256 FROM mine_cache WHERE path=?", (str(path),)).fetchone()
        return row is not None and row[0] == sha256

    def get_chunk_hashes(self, path: str | Path) -> set[str]:
        """Return the set of chunk hashes previously stored for *path*."""
        row = self._conn.execute("SELECT chunk_hashes FROM mine_cache WHERE path=?", (str(path),)).fetchone()
        if row is None:
            return set()
        return set(json.loads(row[0]))

    def record(
        self,
        path: str | Path,
        sha256: str,
        memory_ids: list[str] | None = None,
        chunk_hashes: list[str] | None = None,
    ) -> None:
        """Upsert a cache entry for *path*."""
        self._conn.execute(
            "INSERT INTO mine_cache (path, sha256, mined_at, memory_ids, chunk_hashes) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "  sha256=excluded.sha256, "
            "  mined_at=excluded.mined_at, "
            "  memory_ids=excluded.memory_ids, "
            "  chunk_hashes=excluded.chunk_hashes",
            (
                str(path),
                sha256,
                time.time(),
                json.dumps(memory_ids or []),
                json.dumps(chunk_hashes or []),
            ),
        )
        self._conn.commit()

    def get(self, path: str | Path) -> dict | None:
        """Return the full cache entry for *path*, or None if not cached."""
        row = self._conn.execute(
            "SELECT path, sha256, mined_at, memory_ids, chunk_hashes FROM mine_cache WHERE path=?",
            (str(path),),
        ).fetchone()
        if row is None:
            return None
        return {
            "path": row[0],
            "sha256": row[1],
            "mined_at": row[2],
            "memory_ids": json.loads(row[3]),
            "chunk_hashes": json.loads(row[4]),
        }

    def remove(self, path: str | Path) -> bool:
        """Delete the cache entry for *path*. Returns True if it existed."""
        cur = self._conn.execute("DELETE FROM mine_cache WHERE path=?", (str(path),))
        self._conn.commit()
        return cur.rowcount > 0

    def list_all(self) -> list[dict]:
        """Return all cache entries ordered by most-recently mined first."""
        rows = self._conn.execute(
            "SELECT path, sha256, mined_at, memory_ids, chunk_hashes FROM mine_cache ORDER BY mined_at DESC"
        ).fetchall()
        return [
            {
                "path": r[0],
                "sha256": r[1],
                "mined_at": r[2],
                "memory_ids": json.loads(r[3]),
                "chunk_hashes": json.loads(r[4]),
            }
            for r in rows
        ]

    def stats(self) -> dict:
        """Return summary stats about the cache."""
        row = self._conn.execute("SELECT COUNT(*), SUM(json_array_length(memory_ids)) FROM mine_cache").fetchone()
        return {
            "cached_files": row[0] or 0,
            "total_memories": row[1] or 0,
        }

    def staleness_report(self) -> list[dict]:
        """Check all cached paths against the current filesystem.

        For each cached entry, compare the file's current SHA-256 against the
        stored hash.  Returns a list of dicts (sorted by staleness severity)
        with the following keys:

        ``path``
            Absolute path string.
        ``status``
            One of ``"changed"``, ``"missing"``, or ``"fresh"``.
        ``mined_at``
            Unix timestamp of the last mine.
        ``memory_count``
            Number of memories created from this file.
        """
        import hashlib as _hashlib

        entries = self.list_all()
        results: list[dict] = []

        for entry in entries:
            p = Path(entry["path"])
            if not p.exists():
                status = "missing"
            else:
                try:
                    current_hash = _hashlib.sha256(p.read_bytes()).hexdigest()
                    status = "fresh" if current_hash == entry["sha256"] else "changed"
                except OSError:
                    status = "missing"

            results.append(
                {
                    "path": entry["path"],
                    "status": status,
                    "mined_at": entry["mined_at"],
                    "memory_count": len(entry["memory_ids"]),
                }
            )

        # Sort: changed first, then missing, then fresh
        order = {"changed": 0, "missing": 1, "fresh": 2}
        results.sort(key=lambda r: (order[r["status"]], -r["mined_at"]))
        return results

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MinerCache":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
