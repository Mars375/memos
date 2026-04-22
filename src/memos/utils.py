from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional


def coerce_tags(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        return [values]
    return [str(value) for value in values if value]


def parse_date(value: str | float | None) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip()
    if not value:
        return None
    if len(value) >= 2 and value[-1] in "smhdw" and value[:-1].replace(".", "").isdigit():
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return time.time() - float(value[:-1]) * units[value[-1]]
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Cannot parse date: {value!r}")


def validate_safe_path(user_path: str, *, base_dir: str | None = None) -> str:
    """Validate a user-supplied filesystem path is safe (no traversal).

    Rejects paths containing ``..`` segments.  If *base_dir* is given, the
    resolved path must also stay within that base directory.

    Returns the resolved absolute path string.

    Raises:
        ValueError: If the path contains traversal components or escapes base_dir.
    """
    from pathlib import Path

    if ".." in Path(user_path).parts:
        raise ValueError(f"Path traversal rejected: {user_path!r}")

    resolved = Path(user_path).resolve()

    if base_dir is not None:
        base = Path(base_dir).resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            raise ValueError(f"Path escapes base directory: {user_path!r} (base={base})")

    return str(resolved)


def get_or_create_kg(memos: Any) -> Any:
    """Return a KG instance, delegating to ``memos.get_or_create_kg`` when available."""
    if hasattr(memos, "get_or_create_kg"):
        return memos.get_or_create_kg()

    from .knowledge_graph import KnowledgeGraph

    kg_instance = getattr(memos, "kg", None)
    if kg_instance is None:
        kg_instance = KnowledgeGraph()
        memos.kg = kg_instance
    return kg_instance


def get_or_create_kg_bridge(memos: Any, kg_instance: Any) -> Any:
    """Return a KGBridge, delegating to ``memos.get_or_create_kg_bridge`` when available."""
    if hasattr(memos, "get_or_create_kg_bridge"):
        return memos.get_or_create_kg_bridge(kg_instance)

    from .kg_bridge import KGBridge

    bridge = getattr(memos, "kg_bridge", None)
    if bridge is None or getattr(bridge, "kg", None) is not kg_instance:
        bridge = KGBridge(memos, kg_instance)
        memos.kg_bridge = bridge
    return bridge
