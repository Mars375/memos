"""Low-level helpers for the KnowledgeGraph modules."""

from __future__ import annotations

import sqlite3
import time
import uuid

from ._constants import KG_SHORT_ID_LENGTH


def short_id() -> str:
    """Generate an 8-char UUID fragment."""
    return uuid.uuid4().hex[:KG_SHORT_ID_LENGTH]


def current_time() -> float:
    """Return the current epoch time."""
    return time.time()


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a ``sqlite3.Row`` to a plain dict."""
    return {
        "id": row["id"],
        "subject": row["subject"],
        "predicate": row["predicate"],
        "object": row["object"],
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
        "confidence": row["confidence"],
        "source": row["source"],
        "created_at": row["created_at"],
        "invalidated_at": row["invalidated_at"],
        "confidence_label": row["confidence_label"] if "confidence_label" in row.keys() else "EXTRACTED",
    }
