"""Path queries and multi-hop graph traversal for KnowledgeGraph."""

from __future__ import annotations

from typing import List, Optional

from ._constants import DEFAULT_FIND_PATHS_MAX, DEFAULT_SHORTEST_PATH_MAX_HOPS
from ._kg_helpers import current_time, row_to_dict


def _get_active_neighbors(kg, entity: str, direction: str = "both") -> List[dict]:
    """Get all active triples connected to *entity* (internal helper)."""
    t = current_time()
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


def neighbors(kg, entity: str, depth: int = 1, direction: str = "both") -> dict:
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
            for triple in _get_active_neighbors(kg, node, direction):
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
    kg,
    entity_a: str,
    entity_b: str,
    max_hops: int = 3,
    max_paths: int = DEFAULT_FIND_PATHS_MAX,
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
    t = current_time()
    cur = kg._conn.execute(
        "SELECT * FROM triples WHERE invalidated_at IS NULL"
        " AND (valid_from IS NULL OR valid_from <= ?)"
        " AND (valid_to IS NULL OR valid_to >= ?)",
        (t, t),
    )
    all_triples = [row_to_dict(r) for r in cur.fetchall()]

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
    kg,
    entity_a: str,
    entity_b: str,
    max_hops: int = DEFAULT_SHORTEST_PATH_MAX_HOPS,
) -> Optional[List[dict]]:
    """Find the shortest path between entity_a and entity_b.

    Returns the path as a list of triples, or None if no path exists.
    """
    paths = kg.find_paths(entity_a, entity_b, max_hops=max_hops, max_paths=1)
    return paths[0] if paths else None
