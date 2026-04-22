"""Temporal Knowledge Graph — SQLite-backed triple store with valid_from/valid_to.

Standalone module: no dependency on MemOS core.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from ._kg_algorithms import detect_communities, god_nodes, infer_transitive, surprising_connections
from ._kg_facts import add_fact, invalidate
from ._kg_lint import lint as _lint
from ._kg_paths import (
    find_paths,
    neighbors,
    shortest_path,
)
from ._kg_query import (
    active_subject_object_pairs,
    active_triples,
    backlinks,
    label_stats,
    query,
    query_by_label,
    query_entities,
    query_predicate,
    search_entities,
    stats,
    timeline,
)


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
        self._communities_cache: list[dict] | None = None
        self._communities_cache_ts: float = 0.0

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

    # -- Fact CRUD (delegated to _kg_facts) --

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
        return add_fact(self, subject, predicate, object, valid_from, valid_to, confidence, source, confidence_label)

    def invalidate(self, fact_id: str, reason: str | None = None) -> bool:
        return invalidate(self, fact_id, reason)

    # -- Read queries (delegated to _kg_query) --

    def query(self, entity: str, time: float | str | None = None, direction: str = "both") -> List[dict]:
        return query(self, entity, time, direction)

    def query_predicate(self, predicate: str, time: float | str | None = None) -> List[dict]:
        return query_predicate(self, predicate, time)

    def timeline(self, entity: str) -> List[dict]:
        return timeline(self, entity)

    def active_triples(self) -> List[dict]:
        return active_triples(self)

    def active_subject_object_pairs(self) -> list[tuple[str, str]]:
        return active_subject_object_pairs(self)

    def query_by_label(self, label: str, active_only: bool = True) -> List[dict]:
        return query_by_label(self, label, active_only)

    def label_stats(self) -> dict[str, int]:
        return label_stats(self)

    def search_entities(self, query: str) -> List[dict]:
        return search_entities(self, query)

    def query_entities(self, entities: list[str], time: float | str | None = None) -> list[dict]:
        return query_entities(self, entities, time)

    def stats(self) -> dict:
        return stats(self)

    def backlinks(self, entity: str, predicate: str | None = None, active_only: bool = True) -> List[dict]:
        return backlinks(self, entity, predicate, active_only)

    # -- Path queries (delegated to _kg_paths) --

    def neighbors(self, entity: str, depth: int = 1, direction: str = "both") -> dict:
        return neighbors(self, entity, depth, direction)

    def find_paths(self, entity_a: str, entity_b: str, max_hops: int = 3, max_paths: int = 10) -> List[List[dict]]:
        return find_paths(self, entity_a, entity_b, max_hops, max_paths)

    def shortest_path(self, entity_a: str, entity_b: str, max_hops: int = 5) -> Optional[List[dict]]:
        return shortest_path(self, entity_a, entity_b, max_hops)

    # -- Algorithms (delegated to _kg_algorithms) --

    def detect_communities(self, algorithm: str = "label_propagation") -> List[dict]:
        return detect_communities(self, algorithm)

    def god_nodes(self, top_k: int = 10) -> List[dict]:
        return god_nodes(self, top_k)

    def surprising_connections(self, top_k: int = 10) -> List[dict]:
        return surprising_connections(self, top_k)

    def infer_transitive(self, predicate: str, inferred_predicate: str | None = None, max_depth: int = 3) -> list[str]:
        return infer_transitive(self, predicate, inferred_predicate, max_depth)

    # -- Lint (delegated to _kg_lint) --

    def lint(self, min_facts: int = 2) -> dict:
        return _lint(self, min_facts)

    # -- Lifecycle --

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    def __enter__(self) -> KnowledgeGraph:
        return self

    def __exit__(self, *_) -> None:
        self.close()
