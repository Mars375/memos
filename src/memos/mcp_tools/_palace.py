"""Palace tools: diary_write, diary_read, palace_diary_append, palace_diary_read, palace_list_agents."""

from __future__ import annotations

from typing import Any

from ._registry import _error, _text, register_tool

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_DIARY_WRITE = {
    "name": "diary_write",
    "description": "Write a diary entry for an agent. Entries are timestamped and stored in the memory palace.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "agent": {"type": "string", "description": "Agent identifier (e.g. 'hermes')"},
            "content": {"type": "string", "description": "Diary entry content"},
        },
        "required": ["agent", "content"],
    },
}

_DIARY_READ = {
    "name": "diary_read",
    "description": "Read diary entries for an agent, newest first.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "agent": {"type": "string", "description": "Agent identifier"},
            "limit": {"type": "integer", "default": 20, "description": "Maximum entries to return"},
        },
        "required": ["agent"],
    },
}

_PALACE_DIARY_APPEND = {
    "name": "palace_diary_append",
    "description": "Append a diary entry for an agent with optional tags. The 'agent-diary' tag is automatically added.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string", "description": "Agent identifier (e.g. 'hermes')"},
            "entry": {"type": "string", "description": "Diary entry content"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional extra tags"},
        },
        "required": ["agent_name", "entry"],
    },
}

_PALACE_DIARY_READ = {
    "name": "palace_diary_read",
    "description": "Read diary entries for an agent, newest first. Each entry includes id, entry text, tags, and created_at timestamp.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string", "description": "Agent identifier"},
            "limit": {"type": "integer", "default": 20, "description": "Maximum entries to return"},
        },
        "required": ["agent_name"],
    },
}

_PALACE_LIST_AGENTS = {
    "name": "palace_list_agents",
    "description": "List all registered agents and their activity. Returns name, wing_id, diary_count, last_activity.",
    "inputSchema": {"type": "object", "properties": {}, "required": []},
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_diary_write(args: dict, memos: Any) -> dict:
    agent = args.get("agent", "").strip()
    content = args.get("content", "").strip()
    if not agent or not content:
        return _error("agent and content are required")
    palace = getattr(memos, "_palace", None)
    if palace is None:
        return _error("Palace index not available")
    entry_id = palace.append_diary(agent, content)
    return _text(f"Diary entry saved [{entry_id}] for agent '{agent}'")


def _handle_diary_read(args: dict, memos: Any) -> dict:
    agent = args.get("agent", "").strip()
    if not agent:
        return _error("agent is required")
    palace = getattr(memos, "_palace", None)
    if palace is None:
        return _error("Palace index not available")
    limit = int(args.get("limit", 20))
    entries = palace.read_diary(agent, limit=limit)
    if not entries:
        return _text(f"No diary entries found for agent '{agent}'")
    lines = [f"Diary entries for '{agent}' ({len(entries)}):"]
    for e in entries:
        tag_str = f" [{', '.join(e['tags'])}]" if e.get("tags") else ""
        lines.append(f"  [{e['id']}] {e['entry']}{tag_str}")
    return _text("\n".join(lines))


def _handle_palace_diary_append(args: dict, memos: Any) -> dict:
    agent_name = args.get("agent_name", "").strip()
    entry = args.get("entry", "").strip()
    tags = args.get("tags")
    if not agent_name or not entry:
        return _error("agent_name and entry are required")
    palace = getattr(memos, "_palace", None)
    if palace is None:
        return _error("Palace index not available")
    entry_id = palace.append_diary(agent_name, entry, tags=tags)
    return _text(f"Diary entry appended [{entry_id}] for agent '{agent_name}'")


def _handle_palace_diary_read(args: dict, memos: Any) -> dict:
    agent_name = args.get("agent_name", "").strip()
    if not agent_name:
        return _error("agent_name is required")
    palace = getattr(memos, "_palace", None)
    if palace is None:
        return _error("Palace index not available")
    limit = int(args.get("limit", 20))
    entries = palace.read_diary(agent_name, limit=limit)
    if not entries:
        return _text(f"No diary entries found for agent '{agent_name}'")
    lines = [f"Diary entries for '{agent_name}' ({len(entries)}):"]
    for e in entries:
        tag_str = f" [{', '.join(e['tags'])}]" if e.get("tags") else ""
        lines.append(f"  [{e['id']}] {e['entry']}{tag_str}")
    return _text("\n".join(lines))


def _handle_palace_list_agents(args: dict, memos: Any) -> dict:
    palace = getattr(memos, "_palace", None)
    if palace is None:
        return _error("Palace index not available")
    agents = palace.list_agent_wings()
    if not agents:
        return _text("No agents found in palace.")
    lines = [f"Found {len(agents)} agent(s):"]
    for a in agents:
        activity = f", last_activity={a['last_activity']}" if a.get("last_activity") else ""
        lines.append(f"  {a['name']}: wing_id={a['wing_id']}, diary_count={a['diary_count']}{activity}")
    return _text("\n".join(lines))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_tool("diary_write", _DIARY_WRITE, _handle_diary_write)
register_tool("diary_read", _DIARY_READ, _handle_diary_read)
register_tool("palace_diary_append", _PALACE_DIARY_APPEND, _handle_palace_diary_append)
register_tool("palace_diary_read", _PALACE_DIARY_READ, _handle_palace_diary_read)
register_tool("palace_list_agents", _PALACE_LIST_AGENTS, _handle_palace_list_agents)
