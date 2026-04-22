from __future__ import annotations

from typing import Any

from ._brain_models import SuggestedQuestion


class _BrainAnalyticsMixin:
    _kg: Any
    _wiki: Any

    def surprising_connections(self, top_n: int = 5) -> list[dict[str, Any]]:
        communities = self._kg.detect_communities()
        if not communities:
            return []

        entity_to_comm: dict[str, str] = {}
        for comm in communities:
            for member in comm["nodes"]:
                entity_to_comm[member] = comm.get("label", comm.get("id", ""))

        unique_communities = set(entity_to_comm.values())
        if len(unique_communities) <= 1:
            return []

        rows = self._kg.active_triples()

        predicate_degree: dict[str, int] = {}
        for r in rows:
            p = r["predicate"]
            predicate_degree[p] = predicate_degree.get(p, 0) + 1

        CROSS_COMMUNITY_BONUS = 2.0
        results: list[dict[str, Any]] = []
        for r in rows:
            subject = r["subject"]
            obj = r["object"]
            subj_comm = entity_to_comm.get(subject)
            obj_comm = entity_to_comm.get(obj)
            if subj_comm is None or obj_comm is None:
                continue
            if subj_comm == obj_comm:
                continue
            confidence = float(r["confidence"])
            pred = r["predicate"]
            pred_deg = predicate_degree.get(pred, 1)
            edge_rarity = 1.0 / pred_deg
            score = round(CROSS_COMMUNITY_BONUS * confidence * edge_rarity, 6)
            reason = (
                f"Cross-domain link: {subject} in community {subj_comm} "
                f"is connected to {obj} in community {obj_comm} via {pred}"
            )
            results.append(
                {
                    "subject": subject,
                    "object": obj,
                    "predicate": pred,
                    "confidence": confidence,
                    "score": score,
                    "reason": reason,
                }
            )

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]

    def suggest_questions(self, top_k: int = 5) -> list[SuggestedQuestion]:
        candidates: list[SuggestedQuestion] = []
        seen_questions: set[str] = set()

        def _add(question: str, category: str, score: float, entities: list[str]) -> None:
            if question not in seen_questions:
                seen_questions.add(question)
                candidates.append(
                    SuggestedQuestion(
                        question=question,
                        category=category,
                        score=score,
                        entities=list(entities),
                    )
                )

        god_nodes = self._kg.god_nodes(top_k=20)
        max_degree = max((n["degree"] for n in god_nodes), default=1) or 1
        for node in god_nodes:
            entity = node["entity"]
            degree = node["degree"]
            score = round(degree / max_degree, 4)
            _add(f"What is connected to {entity}?", "hub_exploration", score, [entity])

        surprising = self._kg.surprising_connections(top_k=20)
        max_surprise = max((c["surprise_score"] for c in surprising), default=1.0) or 1.0
        for conn in surprising:
            subject = conn["subject"]
            obj = conn["object"]
            surprise = conn["surprise_score"]
            score = round(surprise / max_surprise, 4)
            _add(f"How does {subject} relate to {obj}?", "cross_community", score, [subject, obj])

        orphans = self._find_orphan_entities()
        for entity in orphans:
            _add(f"Tell me more about {entity}", "orphan_exploration", 0.3, [entity])

        top3 = god_nodes[:3]
        for i in range(len(top3)):
            for j in range(i + 1, len(top3)):
                e1 = top3[i]["entity"]
                e2 = top3[j]["entity"]
                score = round(0.5 * (top3[i]["degree"] / max_degree + top3[j]["degree"] / max_degree), 4)
                _add(
                    f"What is the relationship between {e1} and {e2}?",
                    "god_node_relationship",
                    score,
                    [e1, e2],
                )

        communities = self._kg.detect_communities()
        for comm in communities:
            if comm["size"] <= 2:
                for member in comm["nodes"]:
                    _add(
                        f"What else is connected to {member}?",
                        "small_community",
                        0.4,
                        [member],
                    )

        ambiguous_facts = self._kg.query_by_label("AMBIGUOUS", active_only=True)
        for fact in ambiguous_facts:
            _add(
                f"Is it true that {fact['subject']} {fact['predicate']} {fact['object']}?",
                "ambiguous_verification",
                0.6,
                [fact["subject"], fact["object"]],
            )

        wiki_sparse = self._find_wiki_sparse_entities()
        for entity, fact_count in wiki_sparse:
            _add(
                f"What do we know about {entity}?",
                "wiki_sparse",
                0.35,
                [entity],
            )

        candidates.sort(key=lambda q: (-q.score, q.question))
        return candidates[:top_k]

    def _find_wiki_sparse_entities(self) -> list[tuple[str, int]]:
        try:
            pages = self._wiki.list_pages()
        except Exception:
            return []

        if not pages:
            return []

        rows = self._kg.active_subject_object_pairs()
        fact_count: dict[str, int] = {}
        for subject, obj in rows:
            fact_count[subject] = fact_count.get(subject, 0) + 1
            fact_count[obj] = fact_count.get(obj, 0) + 1

        sparse = []
        for page in pages:
            entity = page.entity
            count = fact_count.get(entity, 0)
            if count <= 2:
                sparse.append((entity, count))
        sparse.sort(key=lambda x: x[1])
        return sparse[:20]

    def _find_orphan_entities(self) -> list[str]:
        rows = self._kg.active_subject_object_pairs()

        degree: dict[str, int] = {}
        for subject, obj in rows:
            degree[subject] = degree.get(subject, 0) + 1
            degree[obj] = degree.get(obj, 0) + 1

        orphans = sorted(entity for entity, deg in degree.items() if deg == 1)
        return orphans[:20]
