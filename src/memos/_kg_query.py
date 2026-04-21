"""Read-only query methods for KnowledgeGraph."""

from __future__ import annotations

import json
from typing import List

from ._kg_helpers import current_time, row_to_dict
from .utils import parse_date as _parse_date


def query(
    kg,
    entity: str,
    time: float | str | None = None,
    direction: str = "both",
) -> List[dict]:
    """Return all active facts linked to *entity* at a given point in time.

    direction: 'subject' | 'object' | 'both'
    time: epoch float, ISO string, or None (= now)
    """
    t = _parse_date(time) if time is not None else current_time()
    rows: list = []
    if direction in ("subject", "both"):
        cur = kg._conn.execute(
            "SELECT * FROM triples WHERE subject=? AND invalidated_at IS NULL"
            " AND (valid_from IS NULL OR valid_from <= ?)"
            " AND (valid_to IS NULL OR valid_to >= ?)",
            (entity, t, t),
        )
        rows.extend(cur.fetchall())
    if direction in ("object", "both"):
        cur = kg._conn.execute(
            "SELECT * FROM triples WHERE object=? AND invalidated_at IS NULL"
            " AND (valid_from IS NULL OR valid_from <= ?)"
            " AND (valid_to IS NULL OR valid_to >= ?)",
            (entity, t, t),
        )
        rows.extend(cur.fetchall())
    seen_ids: set[str] = set()
    deduped: list[dict] = []
    for r in rows:
        d = row_to_dict(r)
        if d["id"] not in seen_ids:
            seen_ids.add(d["id"])
            deduped.append(d)
    return deduped


def query_predicate(
    kg,
    predicate: str,
    time: float | str | None = None,
) -> List[dict]:
    """Return all active triples with the given predicate at time T."""
    t = _parse_date(time) if time is not None else current_time()
    cur = kg._conn.execute(
        "SELECT * FROM triples WHERE predicate=? AND invalidated_at IS NULL"
        " AND (valid_from IS NULL OR valid_from <= ?)"
        " AND (valid_to IS NULL OR valid_to >= ?)",
        (predicate, t, t),
    )
    return [row_to_dict(r) for r in cur.fetchall()]


def timeline(kg, entity: str) -> List[dict]:
    """Return all facts (active and invalidated) about *entity*, chronologically."""
    cur = kg._conn.execute(
        """
        SELECT * FROM triples
        WHERE subject=? OR object=?
        ORDER BY COALESCE(valid_from, created_at) ASC
        """,
        (entity, entity),
    )
    return [row_to_dict(r) for r in cur.fetchall()]


def active_triples(kg) -> List[dict]:
    """Return all active triples in created order."""
    cur = kg._conn.execute("SELECT * FROM triples WHERE invalidated_at IS NULL ORDER BY created_at ASC")
    return [row_to_dict(r) for r in cur.fetchall()]


def active_subject_object_pairs(kg) -> list[tuple[str, str]]:
    """Return active (subject, object) pairs in created order."""
    rows = kg._conn.execute(
        "SELECT subject, object FROM triples WHERE invalidated_at IS NULL ORDER BY created_at ASC"
    ).fetchall()
    return [(str(row["subject"]), str(row["object"])) for row in rows]


def query_by_label(
    kg,
    label: str,
    active_only: bool = True,
) -> List[dict]:
    """Return all facts with the given confidence_label."""
    if label not in kg.VALID_LABELS:
        raise ValueError(f"Invalid label {label!r}. Must be one of {kg.VALID_LABELS}")
    if active_only:
        cur = kg._conn.execute(
            "SELECT * FROM triples WHERE confidence_label=? AND invalidated_at IS NULL",
            (label,),
        )
    else:
        cur = kg._conn.execute(
            "SELECT * FROM triples WHERE confidence_label=?",
            (label,),
        )
    return [row_to_dict(r) for r in cur.fetchall()]


def label_stats(kg) -> dict[str, int]:
    """Return counts per confidence_label (active facts only)."""
    stats = {label: 0 for label in kg.VALID_LABELS}
    rows = kg._conn.execute(
        "SELECT confidence_label, COUNT(*) as cnt FROM triples "
        "WHERE invalidated_at IS NULL GROUP BY confidence_label"
    ).fetchall()
    for r in rows:
        if r["confidence_label"] in stats:
            stats[r["confidence_label"]] = r["cnt"]
    return stats


def search_entities(kg, query: str) -> List[dict]:
    """Full-text search on entity names (case-insensitive substring match)."""
    cur = kg._conn.execute(
        "SELECT * FROM entities WHERE LOWER(name) LIKE LOWER(?)",
        (f"%{query}%",),
    )
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "type": r["type"],
            "properties": json.loads(r["properties"]),
            "created_at": r["created_at"],
        }
        for r in cur.fetchall()
    ]


def stats(kg) -> dict:
    """Return aggregate statistics."""
    total_facts = kg._conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0]
    active_facts = kg._conn.execute("SELECT COUNT(*) FROM triples WHERE invalidated_at IS NULL").fetchone()[0]
    invalidated_facts = total_facts - active_facts
    total_entities = kg._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    return {
        "total_facts": total_facts,
        "total_entities": total_entities,
        "active_facts": active_facts,
        "invalidated_facts": invalidated_facts,
    }


def backlinks(
    kg,
    entity: str,
    predicate: str | None = None,
    active_only: bool = True,
) -> List[dict]:
    """Return all triples where *entity* is the object (incoming edges).

    Args:
        entity: The target entity to find backlinks for.
        predicate: Optional filter — only return backlinks via this predicate.
        active_only: If True (default), exclude invalidated facts.

    Returns:
        List of fact dicts, each with subject/predicate/object/confidence/...
    """
    sql = "SELECT * FROM triples WHERE object=?"
    params: list[object] = [entity]
    if predicate is not None:
        sql += " AND predicate=?"
        params.append(predicate)
    if active_only:
        sql += " AND invalidated_at IS NULL"
    sql += " ORDER BY created_at ASC"
    cur = kg._conn.execute(sql, params)
    return [row_to_dict(r) for r in cur.fetchall()]


def query_entities(
    kg,
    entities: list[str],
    time: float | str | None = None,
) -> list[dict]:
    """Return all active facts linked to any entity in *entities*.

    Uses a single SQL query with an IN clause instead of N individual queries.
    """
    if not entities:
        return []
    t = _parse_date(time) if time is not None else current_time()
    placeholders = ",".join("?" for _ in entities)
    params: list[object] = list(entities) + [t, t]
    cur = kg._conn.execute(
        f"SELECT * FROM triples WHERE "
        f"(subject IN ({placeholders}) OR object IN ({placeholders})) "
        f"AND invalidated_at IS NULL "
        f"AND (valid_from IS NULL OR valid_from <= ?) "
        f"AND (valid_to IS NULL OR valid_to >= ?)",
        list(entities) + params,
    )
    seen_ids: set[str] = set()
    deduped: list[dict] = []
    for r in cur.fetchall():
        d = row_to_dict(r)
        if d["id"] not in seen_ids:
            seen_ids.add(d["id"])
            deduped.append(d)
    return deduped
