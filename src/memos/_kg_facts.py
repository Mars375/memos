"""Fact creation and invalidation for KnowledgeGraph."""

from __future__ import annotations

import time

from ._kg_helpers import current_time, short_id
from .utils import parse_date as _parse_date


def add_fact(
    kg,
    subject: str,
    predicate: str,
    object: str,
    valid_from: str | float | None = None,
    valid_to: str | float | None = None,
    confidence: float = 1.0,
    source: str | None = None,
    confidence_label: str = "EXTRACTED",
) -> str:
    """Add a triple to the knowledge graph.

    Returns the ID of the new triple.
    """
    if confidence_label not in kg.VALID_LABELS:
        raise ValueError(f"Invalid confidence_label: {confidence_label!r}. Must be one of {kg.VALID_LABELS}")
    fact_id = short_id()
    now = time.time()
    vf = _parse_date(valid_from)
    vt = _parse_date(valid_to)
    kg._conn.execute(
        """
        INSERT INTO triples
            (id, subject, predicate, object, valid_from, valid_to,
             confidence, confidence_label, source, created_at, invalidated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            fact_id,
            subject,
            predicate,
            str(object),
            vf,
            vt,
            confidence,
            confidence_label,
            source,
            now,
        ),
    )
    # Auto-upsert subject and object into the entities table so that
    # stats()["total_entities"] and search_entities() reflect reality.
    for entity_name in {subject, str(object)}:
        existing = kg._conn.execute("SELECT id FROM entities WHERE name=?", (entity_name,)).fetchone()
        if existing is None:
            kg._conn.execute(
                """
                INSERT INTO entities (id, name, type, properties, created_at)
                VALUES (?, ?, 'auto', '{}', ?)
                """,
                (short_id(), entity_name, now),
            )
    kg._conn.commit()
    kg._communities_cache = None
    kg._communities_cache_ts = 0.0
    return fact_id


def invalidate(kg, fact_id: str, reason: str | None = None) -> bool:
    """Mark a triple as invalidated. Returns True if found and updated."""
    now = current_time()
    cur = kg._conn.execute(
        "UPDATE triples SET invalidated_at=? WHERE id=? AND invalidated_at IS NULL",
        (now, fact_id),
    )
    kg._conn.commit()
    if cur.rowcount > 0:
        kg._communities_cache = None
        kg._communities_cache_ts = 0.0
    return cur.rowcount > 0
