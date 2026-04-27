"""Wing, room, assignment, and auto-assignment operations."""

from __future__ import annotations

import time
from typing import List, Optional

from .models import generate_id


class PalaceHierarchyMixin:
    """Hierarchy operations for PalaceIndex."""

    def create_wing(self, name: str, description: str = "") -> str:
        """Create a new wing and return its ID."""
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
        return dict(row) if row is not None else None

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
        return [dict(row) for row in rows]

    def create_room(self, wing_name: str, room_name: str, description: str = "") -> str:
        """Create a room inside *wing_name* and return the room ID."""
        room_name = room_name.strip()
        if not room_name:
            raise ValueError("Room name cannot be empty")
        wing = self.get_wing(wing_name)
        if wing is None:
            raise KeyError(f"Wing not found: {wing_name!r}")
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
        return [dict(row) for row in rows]

    def assign(self, memory_id: str, wing_name: str, room_name: Optional[str] = None) -> None:
        """Assign *memory_id* to a wing and optionally a room."""
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
                raise KeyError(f"Room {room_name!r} not found in wing {wing_name!r}")
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
        self._conn.execute("DELETE FROM assignments WHERE memory_id = ?", (memory_id,))
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

    def list_memories(
        self,
        wing_name: Optional[str] = None,
        room_name: Optional[str] = None,
    ) -> List[str]:
        """Return memory IDs within the given scope."""
        if wing_name is None and room_name is None:
            rows = self._conn.execute("SELECT memory_id FROM assignments ORDER BY assigned_at").fetchall()
            return [row["memory_id"] for row in rows]

        wing = self.get_wing(wing_name) if wing_name else None
        if wing_name and wing is None:
            raise KeyError(f"Wing not found: {wing_name!r}")

        if room_name is None:
            rows = self._conn.execute(
                "SELECT memory_id FROM assignments WHERE wing_id = ? ORDER BY assigned_at",
                (wing["id"],),
            ).fetchall()
            return [row["memory_id"] for row in rows]

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
        return [row["memory_id"] for row in rows]

    def stats(self) -> dict:
        """Return aggregate statistics."""
        total_wings = self._conn.execute("SELECT COUNT(*) FROM wings").fetchone()[0]
        total_rooms = self._conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        assigned_memories = self._conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
        return {
            "total_wings": total_wings,
            "total_rooms": total_rooms,
            "assigned_memories": assigned_memories,
        }

    def auto_assign(self, memory_id: str, content: str, tags: List[str]) -> Optional[str]:
        """Heuristically assign *memory_id* to the best-matching wing/room."""
        text = " ".join([content.lower()] + [tag.lower() for tag in tags])
        words = set(text.split())
        wings = self.list_wings()
        if not wings:
            return None

        def _score(candidate: str) -> int:
            candidate_words = set(candidate.lower().replace("-", " ").replace("_", " ").split())
            return len(words & candidate_words)

        best_wing = None
        best_wing_score = 0
        for wing in wings:
            score = _score(wing["name"])
            for room_name in self._get_room_names_for_wing(wing["id"]):
                score += _score(room_name)
            if score > best_wing_score:
                best_wing_score = score
                best_wing = wing

        if best_wing is None or best_wing_score == 0:
            return None

        rooms = self._conn.execute("SELECT id, name FROM rooms WHERE wing_id = ?", (best_wing["id"],)).fetchall()
        best_room_name: Optional[str] = None
        best_room_score = 0
        for room in rooms:
            score = _score(room["name"])
            if score > best_room_score:
                best_room_score = score
                best_room_name = room["name"]

        self.assign(memory_id, best_wing["name"], best_room_name)
        return best_wing["name"]

    def _get_room_names_for_wing(self, wing_id: str) -> List[str]:
        rows = self._conn.execute("SELECT name FROM rooms WHERE wing_id = ?", (wing_id,)).fetchall()
        return [row["name"] for row in rows]


__all__ = ["PalaceHierarchyMixin"]
