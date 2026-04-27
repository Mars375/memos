"""SQLite base and schema setup for the memory palace."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DEFAULT_DB = str(Path.home() / ".memos" / "palace.db")


class PalaceSQLiteBase:
    """SQLite connection owner for PalaceIndex."""

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS wings (
                id          TEXT PRIMARY KEY,
                name        TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id          TEXT PRIMARY KEY,
                wing_id     TEXT NOT NULL REFERENCES wings(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at  REAL NOT NULL,
                UNIQUE(wing_id, name)
            );

            CREATE TABLE IF NOT EXISTS assignments (
                memory_id   TEXT PRIMARY KEY,
                wing_id     TEXT NOT NULL REFERENCES wings(id) ON DELETE CASCADE,
                room_id     TEXT REFERENCES rooms(id) ON DELETE SET NULL,
                assigned_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS diary_entries (
                id        TEXT PRIMARY KEY,
                agent     TEXT NOT NULL,
                content   TEXT NOT NULL,
                tags      TEXT DEFAULT '',
                timestamp REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_assignments_wing  ON assignments(wing_id);
            CREATE INDEX IF NOT EXISTS idx_assignments_room  ON assignments(room_id);
            CREATE INDEX IF NOT EXISTS idx_rooms_wing        ON rooms(wing_id);
            CREATE INDEX IF NOT EXISTS idx_diary_agent       ON diary_entries(agent);
            """
        )
        self._conn.commit()
        try:
            self._conn.execute("ALTER TABLE diary_entries ADD COLUMN tags TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> "PalaceSQLiteBase":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


__all__ = ["PalaceSQLiteBase"]
