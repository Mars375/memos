"""Tool registration framework for MCP tools."""

from __future__ import annotations

from typing import Any, Callable

# ---------------------------------------------------------------------------
# Internal registries
# ---------------------------------------------------------------------------

_TOOL_SCHEMAS: dict[str, dict] = {}
_TOOL_HANDLERS: dict[str, Callable] = {}

# ---------------------------------------------------------------------------
# Public helpers shared across tool modules
# ---------------------------------------------------------------------------


def _text(content: str) -> dict:
    """Wrap a plain-text result in MCP content format."""
    return {"content": [{"type": "text", "text": content}]}


def _error(msg: str) -> dict:
    """Wrap an error in MCP content format."""
    return {"content": [{"type": "text", "text": f"Error: {msg}"}], "isError": True}


def _get_kg(memos: Any) -> Any:
    """Resolve or create a KnowledgeGraph instance from *memos*."""
    if hasattr(memos, "get_or_create_kg"):
        return memos.get_or_create_kg()

    from ..knowledge_graph import KnowledgeGraph

    kg_instance = getattr(memos, "kg", None) or getattr(memos, "_kg", None)
    if kg_instance is None:
        kg_instance = KnowledgeGraph()
        if hasattr(memos, "kg"):
            memos.kg = kg_instance
        else:
            memos._kg = kg_instance
    return kg_instance


def _get_kg_bridge(memos: Any, kg_instance: Any) -> Any:
    """Resolve or create a KGBridge instance from *memos* and *kg_instance*."""
    if hasattr(memos, "get_or_create_kg_bridge"):
        return memos.get_or_create_kg_bridge(kg_instance)

    from ..kg_bridge import KGBridge

    bridge = getattr(memos, "kg_bridge", None) or getattr(memos, "_kg_bridge", None)
    if bridge is None or getattr(bridge, "kg", None) is not kg_instance:
        bridge = KGBridge(memos, kg_instance)
        if hasattr(memos, "kg_bridge"):
            memos.kg_bridge = bridge
        else:
            memos._kg_bridge = bridge
    return bridge


# ---------------------------------------------------------------------------
# Registration API
# ---------------------------------------------------------------------------


def register_tool(name: str, schema: dict, handler: Callable) -> None:
    """Register a tool schema and its handler function."""
    _TOOL_SCHEMAS[name] = schema
    _TOOL_HANDLERS[name] = handler


def get_all_schemas() -> list[dict]:
    """Return all registered tool schemas."""
    return list(_TOOL_SCHEMAS.values())


def dispatch(tool_name: str, arguments: dict, memos: Any) -> dict:
    """Dispatch a tool call to the registered handler.

    Mirrors the original ``_dispatch_inner`` signature and behaviour,
    including the catch-all exception wrapper.
    """
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return _error(f"Unknown tool: {tool_name}")
    try:
        return handler(arguments, memos)
    except Exception as exc:
        return _error(str(exc))
