"""Diary and agent-wing operations for the memory palace."""

from __future__ import annotations

import json
import time
import uuid
from typing import List, Optional


class PalaceDiaryMixin:
    """Diary entries and agent wing helpers for PalaceIndex."""

    _AGENT_DEFAULT_ROOMS = ("diary", "context", "learnings")

    def write_diary(self, agent: str, content: str, tags: Optional[List[str]] = None) -> str:
        """Write a diary entry for *agent* and return the entry ID."""
        return self.append_diary(agent, content, tags=tags)

    def append_diary(self, agent_name: str, entry: str, tags: Optional[List[str]] = None) -> str:
        """Write a diary entry for *agent_name* and return the entry ID."""
        agent_name = agent_name.strip()
        if not agent_name:
            raise ValueError("Agent name cannot be empty")
        entry = entry.strip()
        if not entry:
            raise ValueError("Entry content cannot be empty")

        all_tags = ["agent-diary"]
        if tags:
            all_tags.extend(tags)
        tags_json = json.dumps(all_tags)

        entry_id = f"diary-{agent_name}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        self._conn.execute(
            "INSERT INTO diary_entries (id, agent, content, tags, timestamp) VALUES (?, ?, ?, ?, ?)",
            (entry_id, agent_name, entry, tags_json, time.time()),
        )
        self._conn.commit()
        return entry_id

    def read_diary(self, agent: str, limit: int = 20) -> List[dict]:
        """Read diary entries for *agent*, newest first."""
        agent = agent.strip()
        if not agent:
            raise ValueError("Agent name cannot be empty")
        rows = self._conn.execute(
            "SELECT id, agent, content, tags, timestamp FROM diary_entries WHERE agent = ? ORDER BY timestamp DESC LIMIT ?",
            (agent, limit),
        ).fetchall()
        results: List[dict] = []
        for row in rows:
            raw_tags = row["tags"] or "[]"
            try:
                parsed_tags = json.loads(raw_tags)
                if not isinstance(parsed_tags, list):
                    parsed_tags = []
            except (json.JSONDecodeError, TypeError):
                parsed_tags = []
            results.append(
                {
                    "id": row["id"],
                    "agent_name": row["agent"],
                    "entry": row["content"],
                    "tags": parsed_tags,
                    "created_at": row["timestamp"],
                }
            )
        return results

    def list_agents(self) -> List[dict]:
        """Discover all agents with ``agent:`` wings and their diary entry counts."""
        wings = self.list_wings()
        agent_wings = [wing for wing in wings if wing["name"].startswith("agent:")]
        results: List[dict] = []
        for wing in agent_wings:
            agent_name = wing["name"][len("agent:") :]
            diary_count = self._conn.execute(
                "SELECT COUNT(*) FROM diary_entries WHERE agent = ?",
                (agent_name,),
            ).fetchone()[0]
            results.append(
                {
                    "name": agent_name,
                    "wing": wing,
                    "diary_entries": diary_count,
                    "stats": {
                        "memory_count": wing.get("memory_count", 0),
                        "room_count": wing.get("room_count", 0),
                    },
                }
            )
        return results

    def ensure_agent_wing(self, agent_name: str, description: str = "") -> dict:
        """Auto-provision a wing for *agent_name* with default rooms."""
        agent_name = agent_name.strip()
        if not agent_name:
            raise ValueError("Agent name cannot be empty")
        wing_name = f"agent:{agent_name}"
        self.create_wing(wing_name, description=description)
        for room_name in self._AGENT_DEFAULT_ROOMS:
            self.create_room(wing_name, room_name)
        return self.get_wing(wing_name)  # type: ignore[return-value]

    def list_agent_wings(self) -> List[dict]:
        """Return all agent wings (those prefixed with ``agent:``)."""
        rows = self._conn.execute(
            "SELECT id, name, description, created_at FROM wings WHERE name LIKE 'agent:%'"
        ).fetchall()
        results: List[dict] = []
        for wing in rows:
            wing_id = wing["id"]
            agent_name = wing["name"][len("agent:") :]
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


__all__ = ["PalaceDiaryMixin"]
