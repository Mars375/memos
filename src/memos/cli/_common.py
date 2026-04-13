"""MemOS CLI — shared helpers."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import resolve
from ..core import MemOS


def _get_memos(ns: argparse.Namespace) -> MemOS:
    cli_overrides = {
        "backend": getattr(ns, "backend", None),
        "chroma_host": getattr(ns, "chroma_host", None),
        "chroma_port": getattr(ns, "chroma_port", None),
        "persist_path": getattr(ns, "persist_path", None),
        "qdrant_host": getattr(ns, "qdrant_host", None),
        "qdrant_port": getattr(ns, "qdrant_port", None),
        "qdrant_api_key": getattr(ns, "qdrant_api_key", None),
        "qdrant_path": getattr(ns, "qdrant_path", None),
        "pinecone_api_key": getattr(ns, "pinecone_api_key", None),
        "pinecone_environment": getattr(ns, "pinecone_environment", None),
        "pinecone_index_name": getattr(ns, "pinecone_index_name", None),
        "pinecone_cloud": getattr(ns, "pinecone_cloud", None),
        "pinecone_region": getattr(ns, "pinecone_region", None),
        "pinecone_serverless": getattr(ns, "pinecone_serverless", None),
        "vector_size": getattr(ns, "vector_size", None),
        "embed_host": getattr(ns, "embed_host", None),
        "embed_model": getattr(ns, "embed_model", None),
        "sanitize": not getattr(ns, "no_sanitize", False) or None,
    }
    cfg = resolve({k: v for k, v in cli_overrides.items() if v is not None})
    kwargs: dict = {"backend": cfg["backend"]}
    if cfg["backend"] == "chroma":
        kwargs["chroma_host"] = cfg["chroma_host"]
        kwargs["chroma_port"] = cfg["chroma_port"]
    if cfg["backend"] == "qdrant":
        kwargs["qdrant_host"] = cfg["qdrant_host"]
        kwargs["qdrant_port"] = cfg["qdrant_port"]
        if cfg.get("qdrant_api_key"):
            kwargs["qdrant_api_key"] = cfg["qdrant_api_key"]
        if cfg.get("qdrant_path"):
            kwargs["qdrant_path"] = cfg["qdrant_path"]
        if cfg.get("vector_size"):
            kwargs["vector_size"] = cfg["vector_size"]
    if cfg["backend"] == "pinecone":
        if cfg.get("pinecone_api_key"):
            kwargs["pinecone_api_key"] = cfg["pinecone_api_key"]
        if cfg.get("pinecone_environment"):
            kwargs["pinecone_environment"] = cfg["pinecone_environment"]
        if cfg.get("pinecone_index_name"):
            kwargs["pinecone_index_name"] = cfg["pinecone_index_name"]
        if cfg.get("pinecone_cloud"):
            kwargs["pinecone_cloud"] = cfg["pinecone_cloud"]
        if cfg.get("pinecone_region"):
            kwargs["pinecone_region"] = cfg["pinecone_region"]
        if cfg.get("pinecone_serverless") is not None:
            kwargs["pinecone_serverless"] = cfg["pinecone_serverless"]
        if cfg.get("vector_size"):
            kwargs["vector_size"] = cfg["vector_size"]
    if cfg.get("embed_host"):
        kwargs["embed_host"] = cfg["embed_host"]
    if cfg.get("embed_model"):
        kwargs["embed_model"] = cfg["embed_model"]
    if cfg.get("embed_timeout"):
        kwargs["embed_timeout"] = int(cfg["embed_timeout"])
    if cfg.get("persist_path"):
        kwargs["persist_path"] = cfg["persist_path"]
    if not cfg.get("sanitize", True):
        kwargs["sanitize"] = False
    # Default "memory" backend auto-persists to .memos/store.json
    if cfg["backend"] == "memory" and "persist_path" not in kwargs:
        kwargs["persist_path"] = str(Path(".memos") / "store.json")
    return MemOS(**kwargs)


def _coerce_cli_value(value: str):
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_kv_options(values: list[str] | None) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for entry in values or []:
        if "=" not in entry:
            raise ValueError(f"Expected KEY=VALUE, got {entry!r}")
        key, raw = entry.split("=", 1)
        parsed[key] = _coerce_cli_value(raw)
    return parsed




def _get_kg(ns: argparse.Namespace):
    """Return a KnowledgeGraph instance from CLI namespace."""
    from ..knowledge_graph import KnowledgeGraph
    db_path = getattr(ns, "kg_db", None)
    return KnowledgeGraph(db_path=db_path)


def _get_kg_bridge(ns: argparse.Namespace, memos: Any | None = None):
    """Return a KGBridge instance from CLI namespace."""
    from ..kg_bridge import KGBridge
    from ..knowledge_graph import KnowledgeGraph
    if memos is None:
        memos = _get_memos(ns)
    kg = KnowledgeGraph(db_path=getattr(ns, "kg_db", None))
    return KGBridge(memos, kg)




def _ts(val) -> str:
    """Format a timestamp for display."""
    if val is None:
        return ""
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return str(val)




def _parse_timestamp(ts_str: str) -> float:
    """Parse timestamp: epoch, ISO 8601, or relative (1h, 30m, 2d, 1w)."""
    try:
        return float(ts_str)
    except ValueError:
        pass
    now = time.time()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    if ts_str[-1] in units:
        try:
            return now - float(ts_str[:-1]) * units[ts_str[-1]]
        except (ValueError, IndexError):
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M",
                "%Y-%m-%dT%H:%M%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts_str!r}")


def _fmt_ts(epoch: float) -> str:
    """Format an epoch timestamp for display."""
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")






def _get_palace(ns: argparse.Namespace):
    """Return a PalaceIndex using the --db flag or the default path."""
    from ..palace import PalaceIndex
    db = getattr(ns, "palace_db", None) or None
    if db:
        return PalaceIndex(db_path=db)
    return PalaceIndex()


