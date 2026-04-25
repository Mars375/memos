"""Community detection for the MemOS knowledge graph."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import List


def detect_communities(kg, algorithm: str = "label_propagation") -> List[dict]:
    """Detect entity communities using label-propagation clustering."""
    now = time.time()
    if kg._communities_cache is not None and (now - kg._communities_cache_ts) < 60:
        return kg._communities_cache

    if algorithm not in ("label_propagation", "louvain"):
        raise ValueError(f"Unsupported algorithm: {algorithm!r}. Use 'label_propagation'.")

    rows = kg._conn.execute("SELECT subject, object FROM triples WHERE invalidated_at IS NULL").fetchall()
    if not rows:
        kg._communities_cache = []
        kg._communities_cache_ts = now
        return []

    adj: dict[str, set[str]] = defaultdict(set)
    all_nodes: set[str] = set()
    for row in rows:
        subject, obj = row["subject"], row["object"]
        all_nodes.add(subject)
        all_nodes.add(obj)
        adj[subject].add(obj)
        adj[obj].add(subject)

    labels: dict[str, str] = {node: node for node in all_nodes}
    node_list = sorted(all_nodes)
    for _ in range(10):
        changed = False
        for node in node_list:
            neighbours = adj.get(node)
            if not neighbours:
                continue
            counts: dict[str, int] = defaultdict(int)
            for neighbour in neighbours:
                counts[labels[neighbour]] += 1
            max_count = max(counts.values())
            best = min(label for label, count in counts.items() if count == max_count)
            if best != labels[node]:
                labels[node] = best
                changed = True
        if not changed:
            break

    groups: dict[str, list[str]] = defaultdict(list)
    for node in all_nodes:
        groups[labels[node]].append(node)

    result: list[dict] = []
    for label, members in groups.items():
        members.sort()
        top_entity = max(members, key=lambda node: len(adj.get(node, set())))
        result.append(
            {
                "id": "",
                "label": label,
                "nodes": members,
                "size": len(members),
                "top_entity": top_entity,
            }
        )

    result.sort(key=lambda community: community["size"], reverse=True)
    for index, community in enumerate(result):
        community["id"] = str(index)

    kg._communities_cache = result
    kg._communities_cache_ts = now
    return result
