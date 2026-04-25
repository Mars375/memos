from __future__ import annotations

import re
from typing import Any

from ._brain_context import build_context, snippet
from ._brain_models import BrainSearchResult, KGFact, ScoredMemory, WikiHit
from ._brain_scoring import (
    collect_preference_tags,
    score_kg_facts,
    score_memories,
    score_wiki_hits,
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
        context = build_context(
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
        return score_memories(results, collect_preference_tags(self._analytics), self.PREFERENCE_BOOST_FACTOR)

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
                    "snippet": snippet(page, query if query.strip() else entity),
                }
            )
            seen_entities.add(entity.lower())

        return score_wiki_hits(query, raw_hits, top_k)

    def _score_kg_facts(self, query: str, entities: list[str], top_k: int) -> list[KGFact]:
        return score_kg_facts(query, self._bridge._collect_facts(entities), top_k)

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
        return build_context(
            query=query,
            entities=entities,
            memories=memories,
            wiki_pages=wiki_pages,
            kg_facts=kg_facts,
            max_chars=max_chars,
        )

    @staticmethod
    def _snippet(content: str, query: str) -> str:
        return snippet(content, query)

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
