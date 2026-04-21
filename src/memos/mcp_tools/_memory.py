"""Memory CRUD tools: search, save, forget, stats, decay, reinforce, wake_up, context_for."""

from __future__ import annotations

from typing import Any

from ..utils import parse_date as _parse_date
from ._registry import _error, _text, register_tool

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_MEMORY_SEARCH = {
    "name": "memory_search",
    "description": "Search memories semantically with structured filters.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "default": 5, "description": "Number of results"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Include tags (ANY match)"},
            "require_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags that must all be present",
            },
            "exclude_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags that must not be present",
            },
            "min_importance": {"type": "number", "description": "Minimum importance filter"},
            "max_importance": {"type": "number", "description": "Maximum importance filter"},
            "created_after": {"type": "string", "description": "Only memories created after this ISO date"},
            "created_before": {"type": "string", "description": "Only memories created before this ISO date"},
            "retrieval_mode": {"type": "string", "enum": ["semantic", "keyword", "hybrid"], "default": "semantic"},
        },
        "required": ["query"],
    },
}

_MEMORY_SAVE = {
    "name": "memory_save",
    "description": "Save a new memory. Use for facts, decisions, preferences, procedures.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Memory content"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"},
            "importance": {"type": "number", "default": 0.5, "description": "Importance 0.0-1.0"},
        },
        "required": ["content"],
    },
}

_MEMORY_FORGET = {
    "name": "memory_forget",
    "description": "Delete a memory by ID or by tag (removes all memories with that tag).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Memory ID to delete"},
            "tag": {"type": "string", "description": "Delete all memories with this tag"},
        },
    },
}

_MEMORY_STATS = {
    "name": "memory_stats",
    "description": "Return statistics about the memory store.",
    "inputSchema": {"type": "object", "properties": {}},
}

_MEMORY_DECAY = {
    "name": "memory_decay",
    "description": "Apply importance decay to memories. Dry-run by default. Use apply=true to persist changes.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "apply": {"type": "boolean", "default": False, "description": "Apply decay (default: dry-run)"},
            "min_age_days": {"type": "number", "description": "Minimum age in days to be eligible for decay"},
            "floor": {"type": "number", "description": "Minimum importance after decay (default: 0.1)"},
        },
    },
}

_MEMORY_REINFORCE = {
    "name": "memory_reinforce",
    "description": "Boost a memory's importance. Use to reinforce frequently recalled or critical memories.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "Memory ID to reinforce"},
            "strength": {"type": "number", "default": 0.05, "description": "Boost amount"},
        },
        "required": ["memory_id"],
    },
}

_MEMORY_WAKE_UP = {
    "name": "memory_wake_up",
    "description": (
        "Return L0 (identity) + L1 (top memories by importance) as a single string "
        "ready to inject into an agent system prompt. Use at session start."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "max_chars": {
                "type": "integer",
                "default": 2000,
                "description": "Maximum character count of the returned string",
            },
            "l1_top": {
                "type": "integer",
                "default": 15,
                "description": "Number of top-importance memories to include",
            },
            "include_stats": {
                "type": "boolean",
                "default": True,
                "description": "Include a STATS section with total/tag counts",
            },
        },
    },
}

_MEMORY_CONTEXT_FOR = {
    "name": "memory_context_for",
    "description": (
        "Return optimised context (identity + semantic results) for a specific query. "
        "Combines L0 identity with L3 full-search results."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The query to retrieve context for"},
            "max_chars": {
                "type": "integer",
                "default": 1500,
                "description": "Maximum character count of the returned string",
            },
            "top": {
                "type": "integer",
                "default": 10,
                "description": "Number of semantic results to include",
            },
        },
        "required": ["query"],
    },
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_memory_search(args: dict, memos: Any) -> dict:
    query = args.get("query", "")
    top_k = int(args.get("top_k", 5))
    tags = args.get("tags") or []
    require_tags = args.get("require_tags") or []
    exclude_tags = args.get("exclude_tags") or []
    results = memos.recall(
        query,
        top=top_k,
        filter_tags=tags,
        filter_after=_parse_date(args.get("created_after")),
        filter_before=_parse_date(args.get("created_before")),
        retrieval_mode=args.get("retrieval_mode", "semantic"),
        tag_filter={"require": require_tags, "exclude": exclude_tags} if (require_tags or exclude_tags) else None,
        min_importance=args.get("min_importance"),
        max_importance=args.get("max_importance"),
    )
    if not results:
        return _text("No memories found.")
    lines = []
    for r in results:
        tag_str = f"[{', '.join(r.item.tags)}]" if r.item.tags else ""
        lines.append(f"[{r.score:.3f}] {r.item.content} {tag_str} (importance={r.item.importance:.2f})")
    return _text("\n".join(lines))


def _handle_memory_save(args: dict, memos: Any) -> dict:
    content = args.get("content", "").strip()
    if not content:
        return _error("content is required")
    tags = args.get("tags") or []
    importance = float(args.get("importance", 0.5))
    item = memos.learn(content, tags=tags, importance=importance)
    return _text(f"Saved [{item.id[:8]}] {content[:60]}")


def _handle_memory_forget(args: dict, memos: Any) -> dict:
    mem_id = args.get("id")
    tag = args.get("tag")
    if mem_id:
        memos.forget(mem_id)
        return _text(f"Forgotten: {mem_id}")
    elif tag:
        count = memos.forget_tag(tag)
        return _text(f"Deleted {count} memories with tag '{tag}'")
    else:
        return _error("Provide 'id' or 'tag'")


def _handle_memory_stats(args: dict, memos: Any) -> dict:
    s = memos.stats()
    return _text(
        f"Total memories: {s.total_memories}\n"
        f"Total tags: {s.total_tags}\n"
        f"Avg relevance: {s.avg_relevance:.3f}\n"
        f"Decay candidates: {s.decay_candidates}"
    )


def _handle_memory_decay(args: dict, memos: Any) -> dict:
    report = memos.decay(
        min_age_days=args.get("min_age_days"),
        floor=args.get("floor"),
        dry_run=not args.get("apply", False),
    )
    return _text(
        f"Decay ({'APPLIED' if args.get('apply') else 'DRY RUN'}): "
        f"{report.decayed}/{report.total} decayed, "
        f"avg importance: {report.avg_importance_before:.3f} -> {report.avg_importance_after:.3f}"
    )


def _handle_memory_reinforce(args: dict, memos: Any) -> dict:
    mem_id = args.get("memory_id", "")
    try:
        new_imp = memos.reinforce_memory(mem_id, strength=args.get("strength"))
    except KeyError:
        return _error(f"Memory not found: {mem_id}")
    return _text(f"Reinforced [{mem_id[:8]}] importance -> {new_imp:.3f}")


def _handle_memory_wake_up(args: dict, memos: Any) -> dict:
    from ..context import ContextStack

    cs = ContextStack(memos)
    max_chars = int(args.get("max_chars", 2000))
    l1_top = int(args.get("l1_top", 15))
    include_stats = bool(args.get("include_stats", True))
    output = cs.wake_up(max_chars=max_chars, l1_top=l1_top, include_stats=include_stats)
    return _text(output)


def _handle_memory_context_for(args: dict, memos: Any) -> dict:
    from ..context import ContextStack

    query = args.get("query", "").strip()
    if not query:
        return _error("query is required")
    cs = ContextStack(memos)
    max_chars = int(args.get("max_chars", 1500))
    top = int(args.get("top", 10))
    output = cs.context_for(query=query, max_chars=max_chars, top=top)
    return _text(output)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_tool("memory_search", _MEMORY_SEARCH, _handle_memory_search)
register_tool("memory_save", _MEMORY_SAVE, _handle_memory_save)
register_tool("memory_forget", _MEMORY_FORGET, _handle_memory_forget)
register_tool("memory_stats", _MEMORY_STATS, _handle_memory_stats)
register_tool("memory_decay", _MEMORY_DECAY, _handle_memory_decay)
register_tool("memory_reinforce", _MEMORY_REINFORCE, _handle_memory_reinforce)
register_tool("memory_wake_up", _MEMORY_WAKE_UP, _handle_memory_wake_up)
register_tool("memory_context_for", _MEMORY_CONTEXT_FOR, _handle_memory_context_for)
