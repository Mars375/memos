"""Graph algorithms for KnowledgeGraph — community detection, hub analysis, inference."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import List

from ._constants import DEFAULT_INFERENCE_MAX_DEPTH
from ._kg_helpers import row_to_dict


def detect_communities(kg, algorithm: str = "label_propagation") -> List[dict]:
    """Detect entity communities using label-propagation clustering.

    Pure Python implementation — no external dependencies.
    Builds an undirected adjacency list from all active facts and
    runs iterative label-propagation: each node adopts the most
    common label among its neighbours.  Converges in ~10 iterations.

    Results are cached for 60 seconds.

    Args:
        algorithm: Kept for API compatibility. Only ``"label_propagation"``
            is supported.

    Returns:
        List of community dicts with keys:
            id (str), label (str), nodes (list[str]),
            size (int), top_entity (str)
    """
    # Check cache (60 s TTL)
    now = time.time()
    if kg._communities_cache is not None and (now - kg._communities_cache_ts) < 60:
        return kg._communities_cache

    if algorithm not in ("label_propagation", "louvain"):
        raise ValueError(f"Unsupported algorithm: {algorithm!r}. Use 'label_propagation'.")

    # Fetch all active facts
    rows = kg._conn.execute("SELECT subject, object FROM triples WHERE invalidated_at IS NULL").fetchall()

    if not rows:
        kg._communities_cache = []
        kg._communities_cache_ts = now
        return []

    # Build undirected adjacency list
    adj: dict[str, set[str]] = defaultdict(set)
    all_nodes: set[str] = set()
    for r in rows:
        s, o = r["subject"], r["object"]
        all_nodes.add(s)
        all_nodes.add(o)
        adj[s].add(o)
        adj[o].add(s)

    # Initialise labels — each node is its own community
    labels: dict[str, str] = {node: node for node in all_nodes}

    # Label propagation (deterministic: sorted order, ties broken
    # lexicographically so that tests are reproducible).
    node_list = sorted(all_nodes)
    for _ in range(10):
        changed = False
        for node in node_list:
            neighbours = adj.get(node)
            if not neighbours:
                continue
            # Tally neighbour labels
            counts: dict[str, int] = defaultdict(int)
            for nb in neighbours:
                counts[labels[nb]] += 1
            max_count = max(counts.values())
            best = min(lab for lab, c in counts.items() if c == max_count)
            if best != labels[node]:
                labels[node] = best
                changed = True
        if not changed:
            break

    # Group nodes by their final label
    groups: dict[str, list[str]] = defaultdict(list)
    for node in all_nodes:
        groups[labels[node]].append(node)

    result: list[dict] = []
    for label, members in groups.items():
        members.sort()
        # top_entity = highest-degree node in the community
        top_entity = max(members, key=lambda n: len(adj.get(n, set())))
        result.append(
            {
                "id": "",
                "label": label,
                "nodes": members,
                "size": len(members),
                "top_entity": top_entity,
            }
        )

    # Sort by size descending, assign sequential ids
    result.sort(key=lambda c: c["size"], reverse=True)
    for i, c in enumerate(result):
        c["id"] = str(i)

    kg._communities_cache = result
    kg._communities_cache_ts = now
    return result


def god_nodes(kg, top_k: int = 10) -> List[dict]:
    """Return the highest-degree entities in the knowledge graph.

    Counts appearances of each entity as both subject and object
    across all active facts.  Also reports the break-down of facts
    where the entity appears as subject vs. object, and the three
    most common predicates involving the entity.

    Returns:
        List of dicts with keys:
            entity (str), degree (int),
            facts_as_subject (int), facts_as_object (int),
            top_predicates (list[str])
    """
    rows = kg._conn.execute(
        "SELECT subject, predicate, object FROM triples WHERE invalidated_at IS NULL"
    ).fetchall()

    subject_count: dict[str, int] = defaultdict(int)
    object_count: dict[str, int] = defaultdict(int)
    predicate_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for r in rows:
        s, p, o = r["subject"], r["predicate"], r["object"]
        subject_count[s] += 1
        object_count[o] += 1
        predicate_counts[s][p] += 1
        predicate_counts[o][p] += 1

    degree: dict[str, int] = defaultdict(int)
    for entity in set(list(subject_count.keys()) + list(object_count.keys())):
        degree[entity] = subject_count.get(entity, 0) + object_count.get(entity, 0)

    sorted_entities = sorted(degree.items(), key=lambda x: x[1], reverse=True)

    result: list[dict] = []
    for entity, deg in sorted_entities[:top_k]:
        f_subj = subject_count.get(entity, 0)
        f_obj = object_count.get(entity, 0)
        preds = predicate_counts.get(entity, {})
        top_3 = [p for p, _ in sorted(preds.items(), key=lambda x: x[1], reverse=True)][:3]
        result.append(
            {
                "entity": entity,
                "degree": deg,
                "facts_as_subject": f_subj,
                "facts_as_object": f_obj,
                "top_predicates": top_3,
            }
        )
    return result


def surprising_connections(kg, top_k: int = 10) -> List[dict]:
    """Find edges that connect entities from different communities.

    Uses detect_communities() to build an entity→community map,
    then scores each fact whose subject and object belong to
    different communities.

    The surprise_score is based on the product of the degrees of
    the connected entities (cross-community bridges involving
    high-degree nodes are more surprising).

    Returns:
        List of dicts with keys:
            id, subject, predicate, object, surprise_score, reason
    """
    communities = kg.detect_communities()
    if not communities:
        return []

    # Build entity → community id map
    entity_to_community: dict[str, int] = {}
    for comm in communities:
        for member in comm["nodes"]:
            entity_to_community[member] = int(comm["id"])

    # Get all active facts
    rows = kg._conn.execute("SELECT * FROM triples WHERE invalidated_at IS NULL").fetchall()
    facts = [row_to_dict(r) for r in rows]

    # Compute degree map for scoring
    degree: dict[str, int] = defaultdict(int)
    for f in facts:
        degree[f["subject"]] += 1
        degree[f["object"]] += 1

    # Find cross-community edges
    surprising: list[dict] = []
    for f in facts:
        subj_comm = entity_to_community.get(f["subject"])
        obj_comm = entity_to_community.get(f["object"])
        if subj_comm is None or obj_comm is None:
            continue
        if subj_comm != obj_comm:
            # Surprise score: product of entity degrees
            subj_deg = degree.get(f["subject"], 1)
            obj_deg = degree.get(f["object"], 1)
            surprise_score = round(subj_deg * obj_deg, 2)
            reason = (
                f"Cross-community bridge: "
                f"'{f['subject']}' (community {subj_comm}) → "
                f"'{f['object']}' (community {obj_comm})"
            )
            surprising.append(
                {
                    "id": f["id"],
                    "subject": f["subject"],
                    "predicate": f["predicate"],
                    "object": f["object"],
                    "surprise_score": surprise_score,
                    "reason": reason,
                }
            )

    # Sort by surprise_score descending
    surprising.sort(key=lambda x: x["surprise_score"], reverse=True)
    return surprising[:top_k]


def infer_transitive(
    kg,
    predicate: str,
    inferred_predicate: str | None = None,
    max_depth: int = DEFAULT_INFERENCE_MAX_DEPTH,
) -> list[str]:
    """Create INFERRED facts for transitive chains.

    If A-predicate->B and B-predicate->C, creates A-{inferred_predicate}->C
    with confidence_label='INFERRED'.

    Returns list of new fact IDs (empty if nothing to infer).
    """
    if inferred_predicate is None:
        inferred_predicate = predicate

    active = kg._conn.execute(
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
                            existing = kg._conn.execute(
                                "SELECT id FROM triples "
                                "WHERE subject=? AND predicate=? AND object=? "
                                "AND invalidated_at IS NULL",
                                (new_path[0], inferred_predicate, new_path[-1]),
                            ).fetchone()
                            if existing is None:
                                fid = kg.add_fact(
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
