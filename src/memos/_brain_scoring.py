from __future__ import annotations

from typing import Any

from ._brain_models import KGFact, ScoredMemory, WikiHit
from ._constants import (
    KG_DIRECT_MATCH_BONUS,
    KG_WEIGHT_AMBIGUOUS,
    KG_WEIGHT_DEFAULT,
    KG_WEIGHT_EXTRACTED,
    KG_WEIGHT_INFERRED,
    WIKI_ENTITY_IN_QUERY_BONUS,
)


def collect_preference_tags(analytics: Any) -> set[str]:
    pref_tags: set[str] = set()
    if analytics is None:
        return pref_tags

    try:
        patterns = analytics.preference_patterns(top_k=20)
        for pattern in patterns:
            for tag in pattern.get("tags", []):
                pref_tags.add(tag)
    except Exception:
        return set()
    return pref_tags


def score_memories(results: list[Any], pref_tags: set[str], preference_boost_factor: float) -> list[ScoredMemory]:
    max_score = max((float(getattr(r, "score", 0.0)) for r in results), default=1.0) or 1.0

    scored: list[ScoredMemory] = []
    for result in results:
        item = result.item
        raw_score = float(getattr(result, "score", 0.0))
        norm_score = raw_score / max_score

        if pref_tags and preference_boost_factor > 0:
            memory_tokens = set(str(t).lower() for t in item.tags)
            content_lower = item.content.lower()
            overlap = sum(1 for tag in pref_tags if tag in content_lower or tag in memory_tokens)
            if overlap > 0:
                boost = preference_boost_factor * min(overlap / max(len(pref_tags), 1), 1.0)
                norm_score = min(norm_score + boost, 1.0)

        scored.append(
            ScoredMemory(
                id=item.id,
                content=item.content,
                tags=list(item.tags),
                importance=float(item.importance),
                score=round(norm_score, 4),
                match_reason=getattr(result, "match_reason", ""),
                created_at=float(item.created_at),
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def score_wiki_hits(query: str, raw_hits: list[dict[str, Any]], top_k: int) -> list[WikiHit]:
    query_lower = query.lower()
    max_matches = max((int(hit.get("matches", 0)) for hit in raw_hits), default=1) or 1
    scored: list[WikiHit] = []
    for hit in raw_hits:
        entity = str(hit.get("entity", ""))
        matches = int(hit.get("matches", 0))
        bonus = WIKI_ENTITY_IN_QUERY_BONUS if entity.lower() in query_lower else 0.0
        score = min(1.0, (matches / max_matches) + bonus)
        scored.append(
            WikiHit(
                entity=entity,
                type=str(hit.get("type", "default")),
                matches=matches,
                snippet=str(hit.get("snippet", "")).strip(),
                score=round(score, 4),
            )
        )
    scored.sort(key=lambda item: (item.score, item.matches, item.entity.lower()), reverse=True)
    return scored[:top_k]


def score_kg_facts(query: str, raw_facts: list[dict[str, Any]], top_k: int) -> list[KGFact]:
    query_lower = query.lower()
    label_weight = {
        "EXTRACTED": KG_WEIGHT_EXTRACTED,
        "INFERRED": KG_WEIGHT_INFERRED,
        "AMBIGUOUS": KG_WEIGHT_AMBIGUOUS,
    }
    scored: list[KGFact] = []
    for fact in raw_facts:
        subject = str(fact.get("subject", ""))
        obj = str(fact.get("object", ""))
        label = str(fact.get("confidence_label", "EXTRACTED"))
        direct_match = KG_DIRECT_MATCH_BONUS if subject.lower() in query_lower or obj.lower() in query_lower else 0.0
        score = min(1.0, label_weight.get(label, KG_WEIGHT_DEFAULT) + direct_match)
        scored.append(
            KGFact(
                id=str(fact.get("id", "")),
                subject=subject,
                predicate=str(fact.get("predicate", "")),
                object=obj,
                confidence=float(fact.get("confidence", 1.0)),
                confidence_label=label,
                source=fact.get("source"),
                created_at=fact.get("created_at"),
                score=round(score, 4),
            )
        )
    scored.sort(key=lambda item: (item.score, item.created_at or 0.0), reverse=True)
    return scored[:top_k]
