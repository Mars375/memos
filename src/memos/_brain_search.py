from __future__ import annotations

import re
from typing import Any

from ._brain_models import BrainSearchResult, KGFact, ScoredMemory, WikiHit
from ._constants import (
    DEFAULT_SNIPPET_WINDOW,
    KG_DIRECT_MATCH_BONUS,
    KG_WEIGHT_AMBIGUOUS,
    KG_WEIGHT_DEFAULT,
    KG_WEIGHT_EXTRACTED,
    KG_WEIGHT_INFERRED,
    WIKI_ENTITY_IN_QUERY_BONUS,
)


class _BrainSearchMixin:
    _memos: Any
    _kg: Any
    _wiki: Any
    _bridge: Any
    _analytics: Any

    PREFERENCE_BOOST_FACTOR: float

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_tags: list[str] | None = None,
        min_score: float = 0.0,
        retrieval_mode: str = "hybrid",
        max_context_chars: int = 2000,
        auto_file: bool = False,
    ) -> BrainSearchResult:
        memories_raw = list(
            self._memos.recall(
                query,
                top=top_k,
                filter_tags=filter_tags,
                min_score=min_score,
                retrieval_mode=retrieval_mode,
            )
        )
        memories = self._score_memories(memories_raw)
        entities = self._expand_entities(query, memories_raw, self._bridge._detect_entities(query, memories_raw))
        wiki_pages = self._score_wiki_hits(query, entities, top_k=top_k)
        kg_facts = self._score_kg_facts(query, entities, top_k=top_k)
        context = self._build_context(
            query=query,
            entities=entities,
            memories=memories,
            wiki_pages=wiki_pages,
            kg_facts=kg_facts,
            max_chars=max_context_chars,
        )
        result = BrainSearchResult(
            query=query,
            memories=memories[:top_k],
            wiki_pages=wiki_pages[:top_k],
            kg_facts=kg_facts[:top_k],
            entities=entities,
            context=context,
        )

        if auto_file and len(context) > 200:
            self._auto_file_wiki(query, result)

        return result

    def _score_memories(self, results: list[Any]) -> list[ScoredMemory]:
        max_score = max((float(getattr(r, "score", 0.0)) for r in results), default=1.0) or 1.0

        pref_tags: set[str] = set()
        pref_max_freq = 1
        if self._analytics is not None:
            try:
                patterns = self._analytics.preference_patterns(top_k=20)
                for p in patterns:
                    for tag in p.get("tags", []):
                        pref_tags.add(tag)
                    freq = p.get("frequency", 0)
                    if freq > pref_max_freq:
                        pref_max_freq = freq
            except Exception:
                pref_tags = set()

        scored: list[ScoredMemory] = []
        for result in results:
            item = result.item
            raw_score = float(getattr(result, "score", 0.0))
            norm_score = raw_score / max_score

            if pref_tags and self.PREFERENCE_BOOST_FACTOR > 0:
                memory_tokens = set(str(t).lower() for t in item.tags)
                content_lower = item.content.lower()
                overlap = sum(1 for tag in pref_tags if tag in content_lower or tag in memory_tokens)
                if overlap > 0:
                    boost = self.PREFERENCE_BOOST_FACTOR * min(overlap / max(len(pref_tags), 1), 1.0)
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

    def _expand_entities(self, query: str, results: list[Any], initial: list[str]) -> list[str]:
        expanded: list[str] = []
        seen: set[str] = set()

        def add(candidate: str) -> None:
            candidate = " ".join(candidate.split()).strip(" ,.;:\t\n")
            if not candidate:
                return
            key = candidate.lower()
            if key in seen:
                return
            seen.add(key)
            expanded.append(candidate)

        for candidate in initial:
            add(candidate)
            parts = [part for part in candidate.split() if len(part) > 1]
            if len(parts) > 1:
                for part in parts:
                    if self._kg.search_entities(part) or self._wiki.read_page(part):
                        add(part)

        token_sources = [query, *[result.item.content for result in results[:3]]]
        for source in token_sources:
            for token in re.findall(r"\b[A-Z][\w.-]+\b", source):
                if self._kg.search_entities(token) or self._wiki.read_page(token):
                    add(token)
        return expanded

    def _score_wiki_hits(self, query: str, entities: list[str], top_k: int) -> list[WikiHit]:
        query_lower = query.lower()
        raw_hits = list(self._wiki.search(query))
        seen_entities = {hit["entity"].lower() for hit in raw_hits}
        for entity in entities:
            if entity.lower() in seen_entities:
                continue
            page = self._wiki.read_page(entity)
            if not page:
                continue
            raw_hits.append(
                {
                    "entity": entity,
                    "type": "entity",
                    "matches": 1,
                    "snippet": self._snippet(page, query if query.strip() else entity),
                }
            )
            seen_entities.add(entity.lower())

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

    def _score_kg_facts(self, query: str, entities: list[str], top_k: int) -> list[KGFact]:
        query_lower = query.lower()
        raw_facts = self._bridge._collect_facts(entities)
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
            direct_match = (
                KG_DIRECT_MATCH_BONUS if subject.lower() in query_lower or obj.lower() in query_lower else 0.0
            )
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

    def _build_context(
        self,
        *,
        query: str,
        entities: list[str],
        memories: list[ScoredMemory],
        wiki_pages: list[WikiHit],
        kg_facts: list[KGFact],
        max_chars: int,
    ) -> str:
        lines = [f"Query: {query}"]
        if entities:
            lines.append("Entities: " + ", ".join(entities[:8]))
        lines.append("")
        lines.append("Fused context:")

        buckets: dict[str, list[tuple[float, str]]] = {
            "memory": [(item.score, f"[memory {item.score:.2f}] {item.content}") for item in memories[:5]],
            "wiki": [(item.score, f"[wiki {item.entity}] {item.snippet}") for item in wiki_pages[:5]],
            "kg": [
                (
                    item.score,
                    f"[kg {item.confidence_label}] {item.subject} -{item.predicate}-> {item.object}",
                )
                for item in kg_facts[:5]
            ],
        }

        while any(buckets.values()):
            ordered_sources = sorted(
                (source for source, items in buckets.items() if items),
                key=lambda source: buckets[source][0][0],
                reverse=True,
            )
            for source in ordered_sources:
                _, text = buckets[source].pop(0)
                candidate = lines + [f"- {text}"]
                rendered = "\n".join(candidate)
                if len(rendered) > max_chars:
                    return "\n".join(lines)
                lines.append(f"- {text}")
        return "\n".join(lines)

    @staticmethod
    def _snippet(content: str, query: str, window: int = DEFAULT_SNIPPET_WINDOW) -> str:
        lowered = content.lower()
        query_lower = query.lower()
        idx = lowered.find(query_lower)
        if idx == -1:
            return content[: window * 2].replace("\n", " ").strip()
        start = max(0, idx - window)
        end = min(len(content), idx + len(query) + window)
        return content[start:end].replace("\n", " ").strip()

    def _auto_file_wiki(self, query: str, result: BrainSearchResult) -> str | None:
        lines = [f"# {query}", ""]
        lines.append("## Search Result")
        lines.append("")
        lines.append(f"> Auto-filed from brain search for: *{query}*")
        lines.append("")

        if result.entities:
            lines.append("## Entities")
            lines.append("")
            for entity in result.entities[:10]:
                slug = self._wiki._safe_slug(entity)
                lines.append(f"- [[{slug}|{entity}]]")
            lines.append("")

        if result.memories:
            lines.append("## Relevant Memories")
            lines.append("")
            for mem in result.memories[:5]:
                lines.append(f"- [{mem.score:.2f}] {mem.content[:200]}")
            lines.append("")

        if result.kg_facts:
            lines.append("## Knowledge Graph Facts")
            lines.append("")
            for fact in result.kg_facts[:5]:
                lines.append(f"- {fact.subject} —{fact.predicate}→ {fact.object} ({fact.confidence_label})")
            lines.append("")

        lines.append("## Fused Context")
        lines.append("")
        lines.append(result.context)
        lines.append("")

        content = "\n".join(lines)

        page_result = self._wiki.create_page(
            entity=query,
            entity_type="topic",
            content=content,
        )
        return page_result.get("slug") if page_result.get("status") == "created" else None
