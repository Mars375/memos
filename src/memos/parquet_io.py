"""Parquet export/import for MemOS memories.

Provides efficient binary serialization using Apache Parquet via pyarrow.
Falls back to a clear error if pyarrow is not installed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .models import MemoryItem


def _check_pyarrow() -> None:
    """Raise ImportError with helpful message if pyarrow is missing."""
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        raise ImportError("pyarrow is required for Parquet export/import. Install with: pip install memos[parquet]")


def _items_to_rows(items: list[MemoryItem], *, include_metadata: bool = True) -> list[dict[str, Any]]:
    """Convert MemoryItem list to row dicts suitable for a Parquet table."""
    rows = []
    for item in items:
        row: dict[str, Any] = {
            "id": item.id,
            "content": item.content,
            "tags": "|".join(item.tags),  # Parquet has no native list-of-string
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
            "relevance_score": item.relevance_score,
            "ttl": item.ttl,
        }
        if include_metadata:
            row["metadata_json"] = json.dumps(item.metadata, default=str)
        rows.append(row)
    return rows


def _rows_to_items(
    rows: list[dict[str, Any]],
    *,
    tags_prefix: list[str] | None = None,
) -> list[MemoryItem]:
    """Convert Parquet row dicts back to MemoryItem objects."""
    items = []
    for row in rows:
        tags_str = row.get("tags", "")
        tags = [t for t in tags_str.split("|") if t] if tags_str else []
        if tags_prefix:
            tags.extend(tags_prefix)

        metadata = {}
        meta_json = row.get("metadata_json")
        if meta_json:
            try:
                metadata = json.loads(meta_json)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        item = MemoryItem(
            id=row.get("id", ""),
            content=row.get("content", ""),
            tags=tags,
            importance=float(row.get("importance", 0.5)),
            created_at=float(row.get("created_at", time.time())),
            accessed_at=float(row.get("accessed_at", time.time())),
            access_count=int(row.get("access_count", 0)),
            relevance_score=float(row.get("relevance_score", 0.0)),
            metadata=metadata,
            ttl=row.get("ttl"),
        )
        items.append(item)
    return items


def export_parquet(
    items: list[MemoryItem],
    path: str | Path,
    *,
    include_metadata: bool = True,
    compression: str = "zstd",
) -> dict[str, Any]:
    """Export memories to a Parquet file.

    Args:
        items: List of MemoryItem objects to export.
        path: Output file path.
        include_metadata: Whether to include metadata as JSON column.
        compression: Parquet compression codec (zstd, snappy, gzip, none).

    Returns:
        Summary dict with count, path, size_bytes.
    """
    _check_pyarrow()

    import pyarrow as pa
    import pyarrow.parquet as pq

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = _items_to_rows(items, include_metadata=include_metadata)

    if not rows:
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("content", pa.string()),
                pa.field("tags", pa.string()),
                pa.field("importance", pa.float64()),
                pa.field("created_at", pa.float64()),
                pa.field("accessed_at", pa.float64()),
                pa.field("access_count", pa.int64()),
                pa.field("relevance_score", pa.float64()),
                pa.field("ttl", pa.float64()),
            ]
        )
        if include_metadata:
            schema = schema.append(pa.field("metadata_json", pa.string()))
        table = pa.table(
            {field.name: pa.array([], type=field.type) for field in schema},
            schema=schema,
        )
    else:
        # Convert row-oriented to column-oriented for pyarrow
        columns: dict[str, list] = {}
        for key in rows[0]:
            columns[key] = [row[key] for row in rows]
        table = pa.table(columns)

    pq.write_table(table, str(path), compression=compression)

    size_bytes = path.stat().st_size
    return {
        "total": len(items),
        "path": str(path),
        "size_bytes": size_bytes,
        "compression": compression,
    }


def import_parquet(
    path: str | Path,
    *,
    tags_prefix: list[str] | None = None,
) -> list[MemoryItem]:
    """Import memories from a Parquet file.

    Args:
        path: Input Parquet file path.
        tags_prefix: Optional tags to add to all imported items.

    Returns:
        List of MemoryItem objects parsed from the file.
    """
    _check_pyarrow()

    import pyarrow.parquet as pq

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    table = pq.read_table(str(path))
    rows = table.to_pydict()

    n_rows = table.num_rows
    if n_rows == 0:
        return []

    row_list = []
    for i in range(n_rows):
        row = {col: rows[col][i] for col in rows}
        row_list.append(row)

    return _rows_to_items(row_list, tags_prefix=tags_prefix)
