"""Temporal Knowledge Graph — SQLite-backed triple store with valid_from/valid_to.

Standalone module: no dependency on MemOS core.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def _short_id() -> str:
    """Generate an 8-char UUID fragment."""
    return uuid.uuid4().hex[:8]


def _parse_date(value: str | float | None) -> Optional[float]:
    """Parse a date value to a Unix timestamp float.

    Accepts:
    - None → None
    - float/int → passed through as-is (epoch)
    - ISO 8601 string (e.g. "2024-01-15T10:00:00Z")
    - Relative strings: "1h", "2d", "1w" (relative to *now*, in the past)
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip()
    # Relative: 1h, 2d, 1w, 30m, 45s
    if len(value) >= 2 and value[-1] in "smhdw" and value[:-1].replace(".", "").isdigit():
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return time.time() - float(value[:-1]) * units[value[-1]]
    # ISO 8601
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    # Try float cast last
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Cannot parse date: {value!r}")


class KnowledgeGraph:
    """Temporal knowledge graph stored in SQLite.

    Entities are nodes; triples are directed edges (subject, predicate, object)
    with optional temporal bounds (valid_from, valid_to) and confidence.

    Default DB path: ~/.memos/kg.db
    Pass db_path=":memory:" for in-memory (useful for tests).
    """

    VALID_LABELS = ("EXTRACTED", "INFERRED", "AMBIGUOUS")

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".memos" / "kg.db"
        db_path = Path(db_path) if db_path != ":memory:" else db_path
        if db_path != ":memory:" and isinstance(db_path, Path):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                type        TEXT NOT NULL DEFAULT 'thing',
                properties  TEXT NOT NULL DEFAULT '{}',
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS triples (
                id                TEXT PRIMARY KEY,
                subject           TEXT NOT NULL,
                predicate         TEXT NOT NULL,
                object            TEXT NOT NULL,
                valid_from        REAL,
                valid_to          REAL,
                confidence        REAL NOT NULL DEFAULT 1.0,
                confidence_label  TEXT NOT NULL DEFAULT 'EXTRACTED',
                source            TEXT,
                created_at        REAL NOT NULL,
                invalidated_at    REAL
            );

            CREATE INDEX IF NOT EXISTS idx_triples_subject   ON triples(subject);
            CREATE INDEX IF NOT EXISTS idx_triples_object    ON triples(object);
            CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate);
            CREATE INDEX IF NOT EXISTS idx_triples_subj_pred ON triples(subject, predicate);
            CREATE INDEX IF NOT EXISTS idx_triples_valid_from ON triples(valid_from);
            CREATE INDEX IF NOT EXISTS idx_triples_valid_to   ON triples(valid_to);
        """)
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(triples)").fetchall()}
        if "confidence_label" not in columns:
            self._conn.execute("ALTER TABLE triples ADD COLUMN confidence_label TEXT NOT NULL DEFAULT 'EXTRACTED'")
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_fact(
        self,
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
        if confidence_label not in self.VALID_LABELS:
            raise ValueError(f"Invalid confidence_label: {confidence_label!r}. Must be one of {self.VALID_LABELS}")
        fact_id = _short_id()
        now = time.time()
        vf = _parse_date(valid_from)
        vt = _parse_date(valid_to)
        self._conn.execute(
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
            existing = self._conn.execute("SELECT id FROM entities WHERE name=?", (entity_name,)).fetchone()
            if existing is None:
                self._conn.execute(
                    """
                    INSERT INTO entities (id, name, type, properties, created_at)
                    VALUES (?, ?, 'auto', '{}', ?)
                    """,
                    (_short_id(), entity_name, now),
                )
        self._conn.commit()
        return fact_id

    def query(
        self,
        entity: str,
        time: float | str | None = None,
        direction: str = "both",
    ) -> List[dict]:
        """Return all active facts linked to *entity* at a given point in time.

        direction: 'subject' | 'object' | 'both'
        time: epoch float, ISO string, or None (= now)
        """
        t = _parse_date(time) if time is not None else _current_time()
        rows: list[sqlite3.Row] = []
        if direction in ("subject", "both"):
            cur = self._conn.execute(
                "SELECT * FROM triples WHERE subject=? AND invalidated_at IS NULL"
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to >= ?)",
                (entity, t, t),
            )
            rows.extend(cur.fetchall())
        if direction in ("object", "both"):
            cur = self._conn.execute(
                "SELECT * FROM triples WHERE object=? AND invalidated_at IS NULL"
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to >= ?)",
                (entity, t, t),
            )
            rows.extend(cur.fetchall())
        seen_ids: set[str] = set()
        deduped: list[dict] = []
        for r in rows:
            d = _row_to_dict(r)
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                deduped.append(d)
        return deduped

    def query_predicate(
        self,
        predicate: str,
        time: float | str | None = None,
    ) -> List[dict]:
        """Return all active triples with the given predicate at time T."""
        t = _parse_date(time) if time is not None else _current_time()
        cur = self._conn.execute(
            "SELECT * FROM triples WHERE predicate=? AND invalidated_at IS NULL"
            " AND (valid_from IS NULL OR valid_from <= ?)"
            " AND (valid_to IS NULL OR valid_to >= ?)",
            (predicate, t, t),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def timeline(self, entity: str) -> List[dict]:
        """Return all facts (active and invalidated) about *entity*, chronologically."""
        cur = self._conn.execute(
            """
            SELECT * FROM triples
            WHERE subject=? OR object=?
            ORDER BY COALESCE(valid_from, created_at) ASC
            """,
            (entity, entity),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def invalidate(self, fact_id: str, reason: str | None = None) -> bool:
        """Mark a triple as invalidated. Returns True if found and updated."""
        now = _current_time()
        cur = self._conn.execute(
            "UPDATE triples SET invalidated_at=? WHERE id=? AND invalidated_at IS NULL",
            (now, fact_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def query_by_label(
        self,
        label: str,
        active_only: bool = True,
    ) -> List[dict]:
        """Return all facts with the given confidence_label."""
        if label not in self.VALID_LABELS:
            raise ValueError(f"Invalid label {label!r}. Must be one of {self.VALID_LABELS}")
        if active_only:
            cur = self._conn.execute(
                "SELECT * FROM triples WHERE confidence_label=? AND invalidated_at IS NULL",
                (label,),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM triples WHERE confidence_label=?",
                (label,),
            )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def label_stats(self) -> dict[str, int]:
        """Return counts per confidence_label (active facts only)."""
        stats = {label: 0 for label in self.VALID_LABELS}
        rows = self._conn.execute(
            "SELECT confidence_label, COUNT(*) as cnt FROM triples "
            "WHERE invalidated_at IS NULL GROUP BY confidence_label"
        ).fetchall()
        for r in rows:
            if r["confidence_label"] in stats:
                stats[r["confidence_label"]] = r["cnt"]
        return stats

    def infer_transitive(
        self,
        predicate: str,
        inferred_predicate: str | None = None,
        max_depth: int = 3,
    ) -> list[str]:
        """Create INFERRED facts for transitive chains.

        If A-predicate->B and B-predicate->C, creates A-{inferred_predicate}->C
        with confidence_label='INFERRED'.

        Returns list of new fact IDs (empty if nothing to infer).
        """
        if inferred_predicate is None:
            inferred_predicate = predicate

        active = self._conn.execute(
            "SELECT subject, object FROM triples WHERE predicate=? AND invalidated_at IS NULL",
            (predicate,),
        ).fetchall()

        # Build adjacency
        adj: dict[str, list[str]] = {}
        for row in active:
            adj.setdefault(row["subject"], []).append(row["object"])

        # BFS to find chains
        new_ids: list[str] = []
        visited_chains: set[frozenset[tuple[str, str]]] = set()

        for start in list(adj.keys()):
            queue: list[tuple[str, list[str]]] = [(start, [start])]
            for _ in range(max_depth):
                next_queue: list[tuple[str, list[str]]] = []
                for current, path in queue:
                    for neighbor in adj.get(current, []):
                        if neighbor in path:
                            continue
                        new_path = path + [neighbor]
                        # If path length >= 3, we have a transitive chain
                        if len(new_path) >= 3:
                            chain_key = frozenset((new_path[i], new_path[i + 1]) for i in range(len(new_path) - 1))
                            if chain_key not in visited_chains:
                                visited_chains.add(chain_key)
                                # Check if inferred fact already exists
                                existing = self._conn.execute(
                                    "SELECT id FROM triples "
                                    "WHERE subject=? AND predicate=? AND object=? "
                                    "AND invalidated_at IS NULL",
                                    (new_path[0], inferred_predicate, new_path[-1]),
                                ).fetchone()
                                if existing is None:
                                    fid = self.add_fact(
                                        new_path[0],
                                        inferred_predicate,
                                        new_path[-1],
                                        confidence_label="INFERRED",
                                        source=f"inferred:transitive:{predicate}",
                                    )
                                    new_ids.append(fid)
                        next_queue.append((neighbor, new_path))
                queue = next_queue
                if not queue:
                    break

        return new_ids

    def search_entities(self, query: str) -> List[dict]:
        """Full-text search on entity names (case-insensitive substring match)."""
        cur = self._conn.execute(
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

    def stats(self) -> dict:
        """Return aggregate statistics."""
        total_facts = self._conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0]
        active_facts = self._conn.execute("SELECT COUNT(*) FROM triples WHERE invalidated_at IS NULL").fetchone()[0]
        invalidated_facts = total_facts - active_facts
        total_entities = self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        return {
            "total_facts": total_facts,
            "total_entities": total_entities,
            "active_facts": active_facts,
            "invalidated_facts": invalidated_facts,
        }

    def backlinks(
        self,
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
        cur = self._conn.execute(sql, params)
        return [_row_to_dict(r) for r in cur.fetchall()]

    def lint(self, min_facts: int = 2) -> dict:
        """Detect knowledge graph quality issues.

        Returns a dict with:
          - contradictions: list of {subject, predicate, objects} where one
            subject+predicate points to multiple different objects
          - orphans: list of entity names that appear in exactly one triple
            (degree == 1, likely dangling references)
          - sparse: list of entity names with fewer than `min_facts` active facts
          - summary: {contradictions, orphans, sparse, total_entities, active_facts}
        """
        # Active facts only
        rows = self._conn.execute(
            "SELECT * FROM triples WHERE invalidated_at IS NULL ORDER BY subject, predicate"
        ).fetchall()
        facts = [_row_to_dict(r) for r in rows]

        # --- Contradictions: same (subject, predicate) → multiple objects ---
        from collections import defaultdict

        sp_to_objects: dict[tuple, set] = defaultdict(set)
        for f in facts:
            sp_to_objects[(f["subject"], f["predicate"])].add(f["object"])

        contradictions = [
            {"subject": s, "predicate": p, "objects": sorted(objs)}
            for (s, p), objs in sp_to_objects.items()
            if len(objs) > 1
        ]

        # --- Orphans: entities with degree == 1 ---
        degree: dict[str, int] = defaultdict(int)
        for f in facts:
            degree[f["subject"]] += 1
            degree[f["object"]] += 1
        orphans = sorted(e for e, d in degree.items() if d == 1)

        # --- Sparse entities: fewer than min_facts active facts ---
        sparse_counts: dict[str, int] = defaultdict(int)
        for f in facts:
            sparse_counts[f["subject"]] += 1
        sparse = sorted(e for e, count in sparse_counts.items() if count < min_facts)

        total_entities = len(degree)
        return {
            "contradictions": contradictions,
            "orphans": orphans,
            "sparse": sparse,
            "summary": {
                "contradictions": len(contradictions),
                "orphans": len(orphans),
                "sparse": len(sparse),
                "total_entities": total_entities,
                "active_facts": len(facts),
            },
        }

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Path Queries — multi-hop graph traversal
    # ------------------------------------------------------------------

    def _get_active_neighbors(self, entity: str, direction: str = "both") -> List[dict]:
        """Get all active triples connected to *entity* (internal helper)."""
        t = _current_time()
        rows: list[sqlite3.Row] = []
        if direction in ("subject", "both"):
            cur = self._conn.execute(
                "SELECT * FROM triples WHERE subject=? AND invalidated_at IS NULL"
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to >= ?)",
                (entity, t, t),
            )
            rows.extend(cur.fetchall())
        if direction in ("object", "both"):
            cur = self._conn.execute(
                "SELECT * FROM triples WHERE object=? AND invalidated_at IS NULL"
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to >= ?)",
                (entity, t, t),
            )
            rows.extend(cur.fetchall())
        seen_ids: set[str] = set()
        deduped: list[dict] = []
        for r in rows:
            d = _row_to_dict(r)
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                deduped.append(d)
        return deduped

    def neighbors(self, entity: str, depth: int = 1, direction: str = "both") -> dict:
        """Expand entity neighborhood up to *depth* hops.

        Returns a dict with:
        - "center": the entity name
        - "depth": the depth used
        - "nodes": set of unique entity names discovered
        - "edges": list of active triples in the neighborhood
        - "layers": for each hop (1..depth), the new entities discovered
        """
        if depth < 1:
            raise ValueError("depth must be >= 1")
        all_edges: list[dict] = []
        all_nodes: set[str] = {entity}
        layers: dict[int, list[str]] = {}
        frontier: set[str] = {entity}
        seen_edge_ids: set[str] = set()

        for hop in range(1, depth + 1):
            next_frontier: set[str] = set()
            layer_new: list[str] = []
            for node in frontier:
                for triple in self._get_active_neighbors(node, direction):
                    if triple["id"] in seen_edge_ids:
                        continue
                    seen_edge_ids.add(triple["id"])
                    all_edges.append(triple)
                    subj, obj = triple["subject"], triple["object"]
                    for candidate in (subj, obj):
                        if candidate not in all_nodes:
                            all_nodes.add(candidate)
                            next_frontier.add(candidate)
                            layer_new.append(candidate)
            layers[hop] = sorted(layer_new)
            frontier = next_frontier
            if not frontier:
                break

        return {
            "center": entity,
            "depth": depth,
            "nodes": sorted(all_nodes),
            "edges": all_edges,
            "layers": layers,
        }

    def find_paths(
        self,
        entity_a: str,
        entity_b: str,
        max_hops: int = 3,
        max_paths: int = 10,
    ) -> List[List[dict]]:
        """Find all paths between entity_a and entity_b up to *max_hops*.

        Uses BFS. Returns a list of paths; each path is a list of triples
        connecting entity_a to entity_b. At most *max_paths* paths returned.

        A path is valid if: the first triple contains entity_a, the last
        contains entity_b, and consecutive triples share an entity.
        """
        if max_hops < 1:
            raise ValueError("max_hops must be >= 1")
        if entity_a == entity_b:
            return []

        # Build adjacency: entity -> list of active triples
        t = _current_time()
        cur = self._conn.execute(
            "SELECT * FROM triples WHERE invalidated_at IS NULL"
            " AND (valid_from IS NULL OR valid_from <= ?)"
            " AND (valid_to IS NULL OR valid_to >= ?)",
            (t, t),
        )
        all_triples = [_row_to_dict(r) for r in cur.fetchall()]

        adj: dict[str, list[dict]] = {}
        for triple in all_triples:
            for node in (triple["subject"], triple["object"]):
                adj.setdefault(node, []).append(triple)

        # BFS with path tracking
        # State: (current_entity, path_of_triples, visited_edge_ids)
        paths_found: list[list[dict]] = []
        queue: list[tuple[str, list[dict], frozenset[str]]] = [(entity_a, [], frozenset())]

        for hop in range(max_hops + 1):
            next_queue: list[tuple[str, list[dict], frozenset[str]]] = []
            visited_this_level: set[str] = set()
            for current, path, visited_edges in queue:
                if current == entity_b and len(path) > 0:
                    paths_found.append(path)
                    if len(paths_found) >= max_paths:
                        return paths_found
                    continue
                if hop == max_hops:
                    continue
                for triple in adj.get(current, []):
                    if triple["id"] in visited_edges:
                        continue
                    # Determine the next entity
                    if triple["subject"] == current:
                        next_entity = triple["object"]
                    elif triple["object"] == current:
                        next_entity = triple["subject"]
                    else:
                        continue  # shouldn't happen
                    new_edges = visited_edges | {triple["id"]}
                    next_queue.append((next_entity, path + [triple], new_edges))
                    visited_this_level.add(next_entity)
            queue = next_queue
            if not queue:
                break

        return paths_found

    def shortest_path(
        self,
        entity_a: str,
        entity_b: str,
        max_hops: int = 5,
    ) -> Optional[List[dict]]:
        """Find the shortest path between entity_a and entity_b.

        Returns the path as a list of triples, or None if no path exists.
        """
        paths = self.find_paths(entity_a, entity_b, max_hops=max_hops, max_paths=1)
        return paths[0] if paths else None

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> KnowledgeGraph:
        return self

    def __exit__(self, *_) -> None:
        self.close()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _current_time() -> float:
    return time.time()


def _row_to_dict(row: sqlite3.Row) -> dict:
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
