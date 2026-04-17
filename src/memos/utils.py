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


def get_or_create_kg(memos: Any) -> Any:
    if hasattr(memos, "get_or_create_kg"):
        return memos.get_or_create_kg()

    from .knowledge_graph import KnowledgeGraph

    kg_instance = getattr(memos, "kg", None) or getattr(memos, "_kg", None)
    if kg_instance is None:
        kg_instance = KnowledgeGraph()
        if hasattr(memos, "kg"):
            memos.kg = kg_instance
        else:
            memos._kg = kg_instance
    return kg_instance
