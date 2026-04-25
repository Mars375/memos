"""Centrality and bridge analysis for the MemOS knowledge graph."""

from __future__ import annotations

from collections import defaultdict
from typing import List

from ._kg_helpers import row_to_dict


def god_nodes(kg, top_k: int = 10) -> List[dict]:
    """Return the highest-degree entities in the knowledge graph."""
    rows = kg._conn.execute("SELECT subject, predicate, object FROM triples WHERE invalidated_at IS NULL").fetchall()

    subject_count: dict[str, int] = defaultdict(int)
    object_count: dict[str, int] = defaultdict(int)
    predicate_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        subject, predicate, obj = row["subject"], row["predicate"], row["object"]
        subject_count[subject] += 1
        object_count[obj] += 1
        predicate_counts[subject][predicate] += 1
        predicate_counts[obj][predicate] += 1

    degree: dict[str, int] = defaultdict(int)
    for entity in set(list(subject_count.keys()) + list(object_count.keys())):
        degree[entity] = subject_count.get(entity, 0) + object_count.get(entity, 0)

    sorted_entities = sorted(degree.items(), key=lambda item: item[1], reverse=True)

    result: list[dict] = []
    for entity, degree_value in sorted_entities[:top_k]:
        preds = predicate_counts.get(entity, {})
        top_3 = [predicate for predicate, _ in sorted(preds.items(), key=lambda item: item[1], reverse=True)][:3]
        result.append(
            {
                "entity": entity,
                "degree": degree_value,
                "facts_as_subject": subject_count.get(entity, 0),
                "facts_as_object": object_count.get(entity, 0),
                "top_predicates": top_3,
            }
        )
    return result


def surprising_connections(kg, top_k: int = 10) -> List[dict]:
    """Find edges that connect entities from different communities."""
    communities = kg.detect_communities()
    if not communities:
        return []

    entity_to_community: dict[str, int] = {}
    for community in communities:
        for member in community["nodes"]:
            entity_to_community[member] = int(community["id"])

    rows = kg._conn.execute("SELECT * FROM triples WHERE invalidated_at IS NULL").fetchall()
    facts = [row_to_dict(row) for row in rows]

    degree: dict[str, int] = defaultdict(int)
    for fact in facts:
        degree[fact["subject"]] += 1
        degree[fact["object"]] += 1

    surprising: list[dict] = []
    for fact in facts:
        subj_comm = entity_to_community.get(fact["subject"])
        obj_comm = entity_to_community.get(fact["object"])
        if subj_comm is None or obj_comm is None or subj_comm == obj_comm:
            continue

        subj_deg = degree.get(fact["subject"], 1)
        obj_deg = degree.get(fact["object"], 1)
        reason = (
            f"Cross-community bridge: "
            f"'{fact['subject']}' (community {subj_comm}) → "
            f"'{fact['object']}' (community {obj_comm})"
        )
        surprising.append(
            {
                "id": fact["id"],
                "subject": fact["subject"],
                "predicate": fact["predicate"],
                "object": fact["object"],
                "surprise_score": round(subj_deg * obj_deg, 2),
                "reason": reason,
            }
        )

    surprising.sort(key=lambda item: item["surprise_score"], reverse=True)
    return surprising[:top_k]
