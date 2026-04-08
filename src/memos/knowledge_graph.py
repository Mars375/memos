"""Temporal Knowledge Graph — SQLite-backed triple store with valid_from/valid_to.

Standalone module: no dependency on MemOS core.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def _short_id() -> str:
    """Generate an 8-char UUID fragment."""
    return uuid.uuid4().hex[:8]


def _parse_date(value: str | float | None) -> Optional[float]:
    """Parse a date value to a Unix timestamp float.

    Accepts:
    - None → None
    - float/int → passed through as-is (epoch)
    - ISO 8601 string (e.g. "2024-01-15T10:00:00Z")
    - Relative strings: "1h", "2d", "1w" (relative to *now*, in the past)
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip()
    # Relative: 1h, 2d, 1w, 30m, 45s
    if len(value) >= 2 and value[-1] in "smhdw" and value[:-1].replace(".", "").isdigit():
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return time.time() - float(value[:-1]) * units[value[-1]]
    # ISO 8601
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    # Try float cast last
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Cannot parse date: {value!r}")


class KnowledgeGraph:
    """Temporal knowledge graph stored in SQLite.

    Entities are nodes; triples are directed edges (subject, predicate, object)
    with optional temporal bounds (valid_from, valid_to) and confidence.

    Default DB path: ~/.memos/kg.db
    Pass db_path=":memory:" for in-memory (useful for tests).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".memos" / "kg.db"
        db_path = Path(db_path) if db_path != ":memory:" else db_path
        if db_path != ":memory:" and isinstance(db_path, Path):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                type        TEXT NOT NULL DEFAULT 'thing',
                properties  TEXT NOT NULL DEFAULT '{}',
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS triples (
                id              TEXT PRIMARY KEY,
                subject         TEXT NOT NULL,
                predicate       TEXT NOT NULL,
                object          TEXT NOT NULL,
                valid_from      REAL,
                valid_to        REAL,
                confidence      REAL NOT NULL DEFAULT 1.0,
                source          TEXT,
                created_at      REAL NOT NULL,
                invalidated_at  REAL
            );

            CREATE INDEX IF NOT EXISTS idx_triples_subject   ON triples(subject);
            CREATE INDEX IF NOT EXISTS idx_triples_object    ON triples(object);
            CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate);
            CREATE INDEX IF NOT EXISTS idx_triples_subj_pred ON triples(subject, predicate);
            CREATE INDEX IF NOT EXISTS idx_triples_valid_from ON triples(valid_from);
            CREATE INDEX IF NOT EXISTS idx_triples_valid_to   ON triples(valid_to);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        valid_from: str | float | None = None,
        valid_to: str | float | None = None,
        confidence: float = 1.0,
        source: str | None = None,
    ) -> str:
        """Add a triple to the knowledge graph.

        Returns the ID of the new triple.
        """
        fact_id = _short_id()
        now = time.time()
        vf = _parse_date(valid_from)
        vt = _parse_date(valid_to)
        self._conn.execute(
            """
            INSERT INTO triples
                (id, subject, predicate, object, valid_from, valid_to,
                 confidence, source, created_at, invalidated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (fact_id, subject, predicate, str(object), vf, vt, confidence, source, now),
        )
        # Auto-upsert subject and object into the entities table so that
        # stats()["total_entities"] and search_entities() reflect reality.
        for entity_name in {subject, str(object)}:
            existing = self._conn.execute(
                "SELECT id FROM entities WHERE name=?", (entity_name,)
            ).fetchone()
            if existing is None:
                self._conn.execute(
                    """
                    INSERT INTO entities (id, name, type, properties, created_at)
                    VALUES (?, ?, 'auto', '{}', ?)
                    """,
                    (_short_id(), entity_name, now),
                )
        self._conn.commit()
        return fact_id

    def query(
        self,
        entity: str,
        time: float | str | None = None,
        direction: str = "both",
    ) -> List[dict]:
        """Return all active facts linked to *entity* at a given point in time.

        direction: 'subject' | 'object' | 'both'
        time: epoch float, ISO string, or None (= now)
        """
        t = _parse_date(time) if time is not None else _current_time()
        rows: list[sqlite3.Row] = []
        if direction in ("subject", "both"):
            cur = self._conn.execute(
                "SELECT * FROM triples WHERE subject=? AND invalidated_at IS NULL"
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to >= ?)",
                (entity, t, t),
            )
            rows.extend(cur.fetchall())
        if direction in ("object", "both"):
            cur = self._conn.execute(
                "SELECT * FROM triples WHERE object=? AND invalidated_at IS NULL"
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to >= ?)",
                (entity, t, t),
            )
            rows.extend(cur.fetchall())
        seen_ids: set[str] = set()
        deduped: list[dict] = []
        for r in rows:
            d = _row_to_dict(r)
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                deduped.append(d)
        return deduped

    def query_predicate(
        self,
        predicate: str,
        time: float | str | None = None,
    ) -> List[dict]:
        """Return all active triples with the given predicate at time T."""
        t = _parse_date(time) if time is not None else _current_time()
        cur = self._conn.execute(
            "SELECT * FROM triples WHERE predicate=? AND invalidated_at IS NULL"
            " AND (valid_from IS NULL OR valid_from <= ?)"
            " AND (valid_to IS NULL OR valid_to >= ?)",
            (predicate, t, t),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def timeline(self, entity: str) -> List[dict]:
        """Return all facts (active and invalidated) about *entity*, chronologically."""
        cur = self._conn.execute(
            """
            SELECT * FROM triples
            WHERE subject=? OR object=?
            ORDER BY COALESCE(valid_from, created_at) ASC
            """,
            (entity, entity),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def invalidate(self, fact_id: str, reason: str | None = None) -> bool:
        """Mark a triple as invalidated. Returns True if found and updated."""
        now = _current_time()
        cur = self._conn.execute(
            "UPDATE triples SET invalidated_at=? WHERE id=? AND invalidated_at IS NULL",
            (now, fact_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def search_entities(self, query: str) -> List[dict]:
        """Full-text search on entity names (case-insensitive substring match)."""
        cur = self._conn.execute(
            "SELECT * FROM entities WHERE LOWER(name) LIKE LOWER(?)",
            (f"%{query}%",),
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "type": r["type"],
                "properties": json.loads(r["properties"]),
                "created_at": r["created_at"],
            }
            for r in cur.fetchall()
        ]

    def stats(self) -> dict:
        """Return aggregate statistics."""
        total_facts = self._conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0]
        active_facts = self._conn.execute(
            "SELECT COUNT(*) FROM triples WHERE invalidated_at IS NULL"
        ).fetchone()[0]
        invalidated_facts = total_facts - active_facts
        total_entities = self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        return {
            "total_facts": total_facts,
            "total_entities": total_entities,
            "active_facts": active_facts,
            "invalidated_facts": invalidated_facts,
        }

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> KnowledgeGraph:
        return self

    def __exit__(self, *_) -> None:
        self.close()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _current_time() -> float:
    return time.time()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "subject": row["subject"],
        "predicate": row["predicate"],
        "object": row["object"],
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
        "confidence": row["confidence"],
        "source": row["source"],
        "created_at": row["created_at"],
        "invalidated_at": row["invalidated_at"],
    }
