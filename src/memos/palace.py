"""Hierarchical Palace — Wings/Rooms scoped memory organisation (P6).

Provides a 2-level hierarchy:
  Wing  — top-level domain (person, project, agent, workspace …)
  Room  — thematic category inside a wing (auth, deployment, api …)

A memory ID can be assigned to a wing + optional room. Recall can be scoped
to reduce semantic noise.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from .models import RecallResult, generate_id

if TYPE_CHECKING:
    from .core import MemOS

# ---------------------------------------------------------------------------
# Default database location
# ---------------------------------------------------------------------------

_DEFAULT_DB = str(Path.home() / ".memos" / "palace.db")


# ---------------------------------------------------------------------------
# PalaceIndex
# ---------------------------------------------------------------------------


class PalaceIndex:
    """SQLite-backed index of Wings, Rooms and memory assignments.

    Args:
        db_path: Path to the SQLite database file.  Use ``":memory:"`` for an
                 in-memory (test-friendly) instance.
    """

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

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

            CREATE INDEX IF NOT EXISTS idx_assignments_wing  ON assignments(wing_id);
            CREATE INDEX IF NOT EXISTS idx_assignments_room  ON assignments(room_id);
            CREATE INDEX IF NOT EXISTS idx_rooms_wing        ON rooms(wing_id);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Wings
    # ------------------------------------------------------------------

    def create_wing(self, name: str, description: str = "") -> str:
        """Create a new wing and return its ID.

        If a wing with *name* already exists, the existing ID is returned
        without raising an error (idempotent).
        """
        name = name.strip()
        if not name:
            raise ValueError("Wing name cannot be empty")
        existing = self.get_wing(name)
        if existing:
            return existing["id"]
        wing_id = generate_id(f"wing:{name}:{time.time()}")
        self._conn.execute(
            "INSERT INTO wings (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (wing_id, name, description, time.time()),
        )
        self._conn.commit()
        return wing_id

    def get_wing(self, name: str) -> Optional[dict]:
        """Return wing dict by name, or ``None`` if not found."""
        row = self._conn.execute(
            "SELECT id, name, description, created_at FROM wings WHERE name = ?",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_wings(self) -> List[dict]:
        """Return all wings with memory and room counts."""
        rows = self._conn.execute(
            """
            SELECT w.id, w.name, w.description, w.created_at,
                   COUNT(DISTINCT a.memory_id) AS memory_count,
                   COUNT(DISTINCT r.id)        AS room_count
            FROM wings w
            LEFT JOIN assignments a ON a.wing_id = w.id
            LEFT JOIN rooms r       ON r.wing_id = w.id
            GROUP BY w.id
            ORDER BY w.name
            """
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------

    def create_room(
        self, wing_name: str, room_name: str, description: str = ""
    ) -> str:
        """Create a room inside *wing_name* and return the room ID."""
        room_name = room_name.strip()
        if not room_name:
            raise ValueError("Room name cannot be empty")
        wing = self.get_wing(wing_name)
        if wing is None:
            raise KeyError(f"Wing not found: {wing_name!r}")
        # Idempotent: if it already exists, return its id
        existing = self._conn.execute(
            "SELECT id FROM rooms WHERE wing_id = ? AND name = ?",
            (wing["id"], room_name),
        ).fetchone()
        if existing:
            return existing["id"]
        room_id = generate_id(f"room:{wing['id']}:{room_name}:{time.time()}")
        self._conn.execute(
            "INSERT INTO rooms (id, wing_id, name, description, created_at) VALUES (?, ?, ?, ?, ?)",
            (room_id, wing["id"], room_name, description, time.time()),
        )
        self._conn.commit()
        return room_id

    def list_rooms(self, wing_name: Optional[str] = None) -> List[dict]:
        """List rooms, optionally filtered by wing name."""
        if wing_name is not None:
            wing = self.get_wing(wing_name)
            if wing is None:
                raise KeyError(f"Wing not found: {wing_name!r}")
            rows = self._conn.execute(
                """
                SELECT r.id, r.wing_id, w.name AS wing_name, r.name, r.description,
                       r.created_at,
                       COUNT(DISTINCT a.memory_id) AS memory_count
                FROM rooms r
                JOIN wings w ON w.id = r.wing_id
                LEFT JOIN assignments a ON a.room_id = r.id
                WHERE r.wing_id = ?
                GROUP BY r.id
                ORDER BY r.name
                """,
                (wing["id"],),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT r.id, r.wing_id, w.name AS wing_name, r.name, r.description,
                       r.created_at,
                       COUNT(DISTINCT a.memory_id) AS memory_count
                FROM rooms r
                JOIN wings w ON w.id = r.wing_id
                LEFT JOIN assignments a ON a.room_id = r.id
                GROUP BY r.id
                ORDER BY w.name, r.name
                """
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Assignments
    # ------------------------------------------------------------------

    def assign(
        self, memory_id: str, wing_name: str, room_name: Optional[str] = None
    ) -> None:
        """Assign *memory_id* to a wing (and optionally a room)."""
        wing = self.get_wing(wing_name)
        if wing is None:
            raise KeyError(f"Wing not found: {wing_name!r}")
        room_id: Optional[str] = None
        if room_name is not None:
            row = self._conn.execute(
                "SELECT id FROM rooms WHERE wing_id = ? AND name = ?",
                (wing["id"], room_name),
            ).fetchone()
            if row is None:
                raise KeyError(
                    f"Room {room_name!r} not found in wing {wing_name!r}"
                )
            room_id = row["id"]
        self._conn.execute(
            """
            INSERT INTO assignments (memory_id, wing_id, room_id, assigned_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                wing_id     = excluded.wing_id,
                room_id     = excluded.room_id,
                assigned_at = excluded.assigned_at
            """,
            (memory_id, wing["id"], room_id, time.time()),
        )
        self._conn.commit()

    def unassign(self, memory_id: str) -> None:
        """Remove the palace assignment for *memory_id*."""
        self._conn.execute(
            "DELETE FROM assignments WHERE memory_id = ?", (memory_id,)
        )
        self._conn.commit()

    def get_assignment(self, memory_id: str) -> Optional[dict]:
        """Return assignment dict for *memory_id*, or ``None``."""
        row = self._conn.execute(
            """
            SELECT a.memory_id, a.wing_id, w.name AS wing_name,
                   a.room_id, r.name AS room_name, a.assigned_at
            FROM assignments a
            JOIN wings w ON w.id = a.wing_id
            LEFT JOIN rooms r ON r.id = a.room_id
            WHERE a.memory_id = ?
            """,
            (memory_id,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # List memories
    # ------------------------------------------------------------------

    def list_memories(
        self,
        wing_name: Optional[str] = None,
        room_name: Optional[str] = None,
    ) -> List[str]:
        """Return memory IDs within the given scope.

        - No wing/room: returns all assigned memory IDs.
        - Wing only: all memories in that wing (any room).
        - Wing + room: memories in that specific room.
        """
        if wing_name is None and room_name is None:
            rows = self._conn.execute(
                "SELECT memory_id FROM assignments ORDER BY assigned_at"
            ).fetchall()
            return [r["memory_id"] for r in rows]

        wing = self.get_wing(wing_name) if wing_name else None
        if wing_name and wing is None:
            raise KeyError(f"Wing not found: {wing_name!r}")

        if room_name is None:
            rows = self._conn.execute(
                "SELECT memory_id FROM assignments WHERE wing_id = ? ORDER BY assigned_at",
                (wing["id"],),
            ).fetchall()
            return [r["memory_id"] for r in rows]

        room_row = self._conn.execute(
            "SELECT id FROM rooms WHERE wing_id = ? AND name = ?",
            (wing["id"], room_name),
        ).fetchone()
        if room_row is None:
            raise KeyError(f"Room {room_name!r} not found in wing {wing_name!r}")
        rows = self._conn.execute(
            "SELECT memory_id FROM assignments WHERE room_id = ? ORDER BY assigned_at",
            (room_row["id"],),
        ).fetchall()
        return [r["memory_id"] for r in rows]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return aggregate statistics."""
        total_wings = self._conn.execute(
            "SELECT COUNT(*) FROM wings"
        ).fetchone()[0]
        total_rooms = self._conn.execute(
            "SELECT COUNT(*) FROM rooms"
        ).fetchone()[0]
        assigned_memories = self._conn.execute(
            "SELECT COUNT(*) FROM assignments"
        ).fetchone()[0]
        return {
            "total_wings": total_wings,
            "total_rooms": total_rooms,
            "assigned_memories": assigned_memories,
        }

    # ------------------------------------------------------------------
    # Auto-assign (heuristic)
    # ------------------------------------------------------------------

    def auto_assign(
        self, memory_id: str, content: str, tags: List[str]
    ) -> Optional[str]:
        """Heuristically assign *memory_id* to the best-matching wing/room.

        Algorithm:
        1. Score each wing by keyword overlap between (content + tags) and the
           wing name + its room names.
        2. If a wing scores > 0, pick the best-scoring wing.
        3. Within that wing, score rooms the same way and pick the best if > 0.
        4. Perform the assignment and return the wing name (or ``None`` if no
           match was found).
        """
        text = " ".join([content.lower()] + [t.lower() for t in tags])
        words = set(text.split())

        wings = self.list_wings()
        if not wings:
            return None

        def _score(candidate: str) -> int:
            cand_words = set(candidate.lower().replace("-", " ").replace("_", " ").split())
            return len(words & cand_words)

        best_wing = None
        best_wing_score = 0
        for w in wings:
            score = _score(w["name"])
            # Also check room names for this wing to boost wing score
            rooms = self._get_room_names_for_wing(w["id"])
            for rn in rooms:
                score += _score(rn)
            if score > best_wing_score:
                best_wing_score = score
                best_wing = w

        if best_wing is None or best_wing_score == 0:
            return None

        # Find the best room within this wing
        rooms = self._conn.execute(
            "SELECT id, name FROM rooms WHERE wing_id = ?", (best_wing["id"],)
        ).fetchall()
        best_room_name: Optional[str] = None
        best_room_score = 0
        for r in rooms:
            score = _score(r["name"])
            if score > best_room_score:
                best_room_score = score
                best_room_name = r["name"]

        self.assign(memory_id, best_wing["name"], best_room_name)
        return best_wing["name"]

    def _get_room_names_for_wing(self, wing_id: str) -> List[str]:
        rows = self._conn.execute(
            "SELECT name FROM rooms WHERE wing_id = ?", (wing_id,)
        ).fetchall()
        return [r["name"] for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> "PalaceIndex":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# PalaceRecall
# ---------------------------------------------------------------------------


class PalaceRecall:
    """Scoped recall that filters results to a wing/room scope."""

    def __init__(self, palace: PalaceIndex) -> None:
        self._palace = palace

    def palace_recall(
        self,
        memos: "MemOS",
        query: str,
        wing_name: Optional[str] = None,
        room_name: Optional[str] = None,
        top: int = 10,
    ) -> List[RecallResult]:
        """Recall memories scoped to *wing_name* / *room_name*.

        If the scope is empty or no matches survive the filter, falls back to
        an unscoped ``memos.recall()`` call.

        Args:
            memos:     MemOS instance to recall from.
            query:     Recall query string.
            wing_name: Limit to this wing (optional).
            room_name: Further limit to this room (optional, requires wing_name).
            top:       Maximum results to return.

        Returns:
            Filtered (and possibly extended via fallback) list of RecallResult.
        """
        scoped_ids: Optional[set[str]] = None

        if wing_name is not None:
            try:
                ids = self._palace.list_memories(
                    wing_name=wing_name, room_name=room_name
                )
                scoped_ids = set(ids)
            except KeyError:
                # Unknown wing/room — treat as no scope
                scoped_ids = None

        # Fetch a broader set so filtering still yields *top* results
        fetch_top = top * 5 if scoped_ids is not None else top
        all_results = memos.recall(query=query, top=fetch_top)

        if scoped_ids is not None and scoped_ids:
            filtered = [r for r in all_results if r.item.id in scoped_ids]
            if filtered:
                return filtered[:top]
            # Scope exists but nothing matched — fall back to global recall
        elif scoped_ids is not None and not scoped_ids:
            # Scope is empty — fall back
            pass

        # Fallback: return unfiltered global results
        if fetch_top != top:
            return memos.recall(query=query, top=top)
        return all_results[:top]
