"""Knowledge graph quality analysis (lint) for KnowledgeGraph."""

from __future__ import annotations

from collections import defaultdict

from ._kg_helpers import row_to_dict

# Cross-predicate transitivity patterns for lint suggestions
_TRANSITIVE_PAIRS = [
    ("works_at", "located_in", "located_in"),
    ("member_of", "part_of", "member_of"),
    ("owns", "located_in", "located_in"),
    ("manages", "works_on", "works_on"),
]


def lint(kg, min_facts: int = 2) -> dict:
    """Detect knowledge graph quality issues.

    Returns a structured report dict with:
      - contradictions: list of {subject, predicate, objects, fact_ids}
        where one subject+predicate points to multiple different objects
        (all facts currently valid / not invalidated)
      - orphans: list of entity names that appear in exactly one triple
        (degree == 1, likely dangling references)
      - sparse: list of entity names with fewer than `min_facts` active facts
      - suggested_facts: list of {subject, predicate, object, reason, via}
        for potential new facts inferred from transitive relationships
        that don't already exist as explicit facts
      - summary: {contradictions, orphans, sparse, suggested_facts,
        total_entities, active_facts}
    """
    # Active facts only
    rows = kg._conn.execute("SELECT * FROM triples WHERE invalidated_at IS NULL ORDER BY subject, predicate").fetchall()
    facts = [row_to_dict(r) for r in rows]

    # --- Contradictions: same (subject, predicate) → multiple objects,
    #     all currently valid (no invalidated_at) ---
    sp_to_objects: dict[tuple, set] = defaultdict(set)
    sp_to_fact_ids: dict[tuple, list[str]] = defaultdict(list)
    for f in facts:
        sp_to_objects[(f["subject"], f["predicate"])].add(f["object"])
        sp_to_fact_ids[(f["subject"], f["predicate"])].append(f["id"])

    contradictions = [
        {
            "subject": s,
            "predicate": p,
            "objects": sorted(objs),
            "fact_ids": sp_to_fact_ids[(s, p)],
        }
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

    # --- Suggested new facts based on transitive relationships ---
    # Build adjacency: predicate → {subject: [objects]}
    pred_adj: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for f in facts:
        pred_adj[f["predicate"]][f["subject"]].append(f["object"])

    # Existing facts as a set for fast lookup
    existing_facts: set[tuple[str, str, str]] = set()
    for f in facts:
        existing_facts.add((f["subject"], f["predicate"], f["object"]))

    suggested: list[dict] = []
    seen_suggestions: set[tuple[str, str, str]] = set()

    for predicate, adj in pred_adj.items():
        # For each predicate, find transitive chains: A→B and B→C suggests A→C
        for a, b_list in adj.items():
            for b in b_list:
                c_list = adj.get(b, [])
                for c in c_list:
                    if c == a:
                        continue  # skip self-loops
                    key = (a, predicate, c)
                    if key in existing_facts or key in seen_suggestions:
                        continue
                    seen_suggestions.add(key)
                    suggested.append(
                        {
                            "subject": a,
                            "predicate": predicate,
                            "object": c,
                            "reason": "transitive_inference",
                            "via": [a, b, c],
                        }
                    )

    # Also suggest cross-predicate transitivity for common patterns
    # e.g., if A "works_at" B and B "located_in" C → suggest A "located_in" C
    for pred1, pred2, result_pred in _TRANSITIVE_PAIRS:
        adj1 = pred_adj.get(pred1, {})
        adj2 = pred_adj.get(pred2, {})
        for a, b_list in adj1.items():
            for b in b_list:
                c_list = adj2.get(b, [])
                for c in c_list:
                    if c == a:
                        continue
                    key = (a, result_pred, c)
                    if key in existing_facts or key in seen_suggestions:
                        continue
                    seen_suggestions.add(key)
                    suggested.append(
                        {
                            "subject": a,
                            "predicate": result_pred,
                            "object": c,
                            "reason": "cross_predicate_transitive",
                            "via": [a, b, c],
                        }
                    )

    total_entities = len(degree)
    return {
        "contradictions": contradictions,
        "orphans": orphans,
        "sparse": sparse,
        "suggested_facts": suggested,
        "summary": {
            "contradictions": len(contradictions),
            "orphans": len(orphans),
            "sparse": len(sparse),
            "suggested_facts": len(suggested),
            "total_entities": total_entities,
            "active_facts": len(facts),
        },
    }
