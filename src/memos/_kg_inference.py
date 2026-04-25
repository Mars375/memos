"""Inference helpers for the MemOS knowledge graph."""

from __future__ import annotations

from ._constants import DEFAULT_INFERENCE_MAX_DEPTH


def infer_transitive(
    kg,
    predicate: str,
    inferred_predicate: str | None = None,
    max_depth: int = DEFAULT_INFERENCE_MAX_DEPTH,
) -> list[str]:
    """Create INFERRED facts for transitive chains."""
    if inferred_predicate is None:
        inferred_predicate = predicate

    active = kg._conn.execute(
        "SELECT subject, object FROM triples WHERE predicate=? AND invalidated_at IS NULL",
        (predicate,),
    ).fetchall()

    adj: dict[str, list[str]] = {}
    for row in active:
        adj.setdefault(row["subject"], []).append(row["object"])

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
                    if len(new_path) >= 3:
                        chain_key = frozenset((new_path[i], new_path[i + 1]) for i in range(len(new_path) - 1))
                        if chain_key not in visited_chains:
                            visited_chains.add(chain_key)
                            existing = kg._conn.execute(
                                "SELECT id FROM triples "
                                "WHERE subject=? AND predicate=? AND object=? "
                                "AND invalidated_at IS NULL",
                                (new_path[0], inferred_predicate, new_path[-1]),
                            ).fetchone()
                            if existing is None:
                                fact_id = kg.add_fact(
                                    new_path[0],
                                    inferred_predicate,
                                    new_path[-1],
                                    confidence_label="INFERRED",
                                    source=f"inferred:transitive:{predicate}",
                                )
                                new_ids.append(fact_id)
                    next_queue.append((neighbor, new_path))
            queue = next_queue
            if not queue:
                break

    return new_ids
