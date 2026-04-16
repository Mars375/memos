"""Hierarchical Palace — Wings/Rooms scoped memory organisation (P6).

Provides a 2-level hierarchy:
  Wing  — top-level domain (person, project, agent, workspace …)
  Room  — thematic category inside a wing (auth, deployment, api …)

A memory ID can be assigned to a wing + optional room. Recall can be scoped
to reduce semantic noise.
"""

from __future__ import annotations

import json
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
        # Migration: add 'tags' column if it was not present in older schemas
        try:
            self._conn.execute("ALTER TABLE diary_entries ADD COLUMN tags TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

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

    def create_room(self, wing_name: str, room_name: str, description: str = "") -> str:
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

    def assign(self, memory_id: str, wing_name: str, room_name: Optional[str] = None) -> None:
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
            rows = self._conn.execute("SELECT memory_id FROM assignments ORDER BY assigned_at").fetchall()
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
        total_wings = self._conn.execute("SELECT COUNT(*) FROM wings").fetchone()[0]
        total_rooms = self._conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        assigned_memories = self._conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
        return {
            "total_wings": total_wings,
            "total_rooms": total_rooms,
            "assigned_memories": assigned_memories,
        }

    # ------------------------------------------------------------------
    # Auto-assign (heuristic)
    # ------------------------------------------------------------------

    def auto_assign(self, memory_id: str, content: str, tags: List[str]) -> Optional[str]:
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
        rooms = self._conn.execute("SELECT id, name FROM rooms WHERE wing_id = ?", (best_wing["id"],)).fetchall()
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
        rows = self._conn.execute("SELECT name FROM rooms WHERE wing_id = ?", (wing_id,)).fetchall()
        return [r["name"] for r in rows]

    # ------------------------------------------------------------------
    # Diary entries
    # ------------------------------------------------------------------

    def write_diary(self, agent: str, content: str, tags: Optional[List[str]] = None) -> str:
        """Write a diary entry for *agent* and return the entry ID.

        Args:
            agent:   Agent identifier (e.g. "hermes").
            content: Diary entry content.
            tags:    Optional list of tags.

        Returns:
            The generated entry ID.
        """
        return self.append_diary(agent, content, tags=tags)

    def append_diary(self, agent_name: str, entry: str, tags: Optional[List[str]] = None) -> str:
        """Write a diary entry for *agent_name* and return the entry ID.

        Args:
            agent_name: Agent identifier (e.g. "hermes").
            entry:      Diary entry content.
            tags:       Optional extra tags (``"agent-diary"`` is always prepended).

        Returns:
            The generated entry ID.
        """
        agent_name = agent_name.strip()
        if not agent_name:
            raise ValueError("Agent name cannot be empty")
        entry = entry.strip()
        if not entry:
            raise ValueError("Entry content cannot be empty")
        import uuid as _uuid

        all_tags = ["agent-diary"]
        if tags:
            all_tags.extend(tags)
        tags_json = json.dumps(all_tags)

        entry_id = f"diary-{agent_name}-{int(time.time())}-{_uuid.uuid4().hex[:8]}"
        self._conn.execute(
            "INSERT INTO diary_entries (id, agent, content, tags, timestamp) VALUES (?, ?, ?, ?, ?)",
            (entry_id, agent_name, entry, tags_json, time.time()),
        )
        self._conn.commit()
        return entry_id

    def read_diary(self, agent: str, limit: int = 20) -> List[dict]:
        """Read diary entries for *agent*, newest first.

        Args:
            agent: Agent identifier.
            limit: Maximum entries to return.

        Returns:
            List of dicts with keys {id, agent_name, entry, tags, created_at}.
        """
        agent = agent.strip()
        if not agent:
            raise ValueError("Agent name cannot be empty")
        rows = self._conn.execute(
            "SELECT id, agent, content, tags, timestamp FROM diary_entries WHERE agent = ? ORDER BY timestamp DESC LIMIT ?",
            (agent, limit),
        ).fetchall()
        results: List[dict] = []
        for r in rows:
            raw_tags = r["tags"] or "[]"
            try:
                parsed_tags = json.loads(raw_tags)
                if not isinstance(parsed_tags, list):
                    parsed_tags = []
            except (json.JSONDecodeError, TypeError):
                parsed_tags = []
            results.append(
                {
                    "id": r["id"],
                    "agent_name": r["agent"],
                    "entry": r["content"],
                    "tags": parsed_tags,
                    "created_at": r["timestamp"],
                }
            )
        return results

    # ------------------------------------------------------------------
    # Agent discovery
    # ------------------------------------------------------------------

    def list_agents(self) -> List[dict]:
        """Discover all agents with ``agent-`` wings and their diary entry counts.

        Returns:
            List of dicts: ``{name, wing, diary_entries, stats}``.
            *name* is the agent identifier (wing name minus ``agent-`` prefix).
            *wing* is the full wing dict.
            *diary_entries* is the count of diary entries for that agent.
            *stats* is a dict with ``memory_count`` and ``room_count`` from the wing.
        """
        wings = self.list_wings()
        agent_wings = [w for w in wings if w["name"].startswith("agent-")]
        results: List[dict] = []
        for w in agent_wings:
            agent_name = w["name"][len("agent-") :]
            diary_count = self._conn.execute(
                "SELECT COUNT(*) FROM diary_entries WHERE agent = ?",
                (agent_name,),
            ).fetchone()[0]
            results.append(
                {
                    "name": agent_name,
                    "wing": w,
                    "diary_entries": diary_count,
                    "stats": {
                        "memory_count": w.get("memory_count", 0),
                        "room_count": w.get("room_count", 0),
                    },
                }
            )
        return results

    # ------------------------------------------------------------------
    # Agent wing auto-provisioning
    # ------------------------------------------------------------------

    _AGENT_DEFAULT_ROOMS = ("diary", "context", "learnings")

    def ensure_agent_wing(self, agent_name: str, description: str = "") -> dict:
        """Auto-provision a wing for *agent_name* with default rooms.

        Creates a wing named ``agent:<name>`` (if it does not already exist)
        and ensures the three default rooms — *diary*, *context*, *learnings* —
        exist inside it.  Fully idempotent: calling twice produces the same
        result.

        Args:
            agent_name:  Agent identifier (e.g. ``"hermes"``).
            description: Optional human-readable description for the wing.

        Returns:
            The wing dict (same format as :meth:`get_wing`).

        Raises:
            ValueError: If *agent_name* is empty or whitespace-only.
        """
        agent_name = agent_name.strip()
        if not agent_name:
            raise ValueError("Agent name cannot be empty")
        wing_name = f"agent:{agent_name}"
        self.create_wing(wing_name, description=description)
        for room_name in self._AGENT_DEFAULT_ROOMS:
            self.create_room(wing_name, room_name)
        return self.get_wing(wing_name)  # type: ignore[return-value]

    def list_agent_wings(self) -> List[dict]:
        """Return all agent wings (those prefixed with ``agent:``).

        Each entry includes:

        - ``name`` — agent identifier (wing name minus the ``agent:`` prefix)
        - ``wing_id`` — the wing's unique ID
        - ``diary_count`` — number of memories assigned to the *diary* room
        - ``last_activity`` — most recent assignment timestamp in that wing
          (``None`` if no assignments exist)
        """
        rows = self._conn.execute(
            "SELECT id, name, description, created_at FROM wings WHERE name LIKE 'agent:%'"
        ).fetchall()
        results: List[dict] = []
        for w in rows:
            wing_id = w["id"]
            agent_name = w["name"][len("agent:") :]
            # Find the diary room id for this wing
            diary_room_row = self._conn.execute(
                "SELECT id FROM rooms WHERE wing_id = ? AND name = 'diary'",
                (wing_id,),
            ).fetchone()
            diary_count = 0
            if diary_room_row:
                diary_count = self._conn.execute(
                    "SELECT COUNT(*) FROM assignments WHERE room_id = ?",
                    (diary_room_row["id"],),
                ).fetchone()[0]
            # Most recent assignment timestamp
            last_activity_row = self._conn.execute(
                "SELECT MAX(assigned_at) FROM assignments WHERE wing_id = ?",
                (wing_id,),
            ).fetchone()
            last_activity = last_activity_row[0] if last_activity_row else None
            results.append(
                {
                    "name": agent_name,
                    "wing_id": wing_id,
                    "diary_count": diary_count,
                    "last_activity": last_activity,
                }
            )
        return results

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
                ids = self._palace.list_memories(wing_name=wing_name, room_name=room_name)
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
