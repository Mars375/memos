"""Unified Brain Search across memories, wiki pages, and knowledge graph."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .kg_bridge import KGBridge
from .knowledge_graph import KnowledgeGraph
from .wiki_living import LivingWikiEngine


@dataclass
class ScoredMemory:
    id: str
    content: str
    tags: list[str]
    importance: float
    score: float
    match_reason: str
    created_at: float


@dataclass
class WikiHit:
    entity: str
    type: str
    matches: int
    snippet: str
    score: float


@dataclass
class KGFact:
    id: str
    subject: str
    predicate: str
    object: str
    confidence: float
    confidence_label: str
    source: str | None
    created_at: float | None
    score: float


@dataclass
class BrainSearchResult:
    query: str
    memories: list[ScoredMemory]
    wiki_pages: list[WikiHit]
    kg_facts: list[KGFact]
    entities: list[str]
    context: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "memories": [asdict(item) for item in self.memories],
            "wiki_pages": [asdict(item) for item in self.wiki_pages],
            "kg_facts": [asdict(item) for item in self.kg_facts],
            "entities": list(self.entities),
            "context": self.context,
        }


class BrainSearch:
    """Unified search facade across memory, living wiki, and knowledge graph."""

    def __init__(
        self,
        memos: Any,
        kg: KnowledgeGraph | None = None,
        wiki_dir: str | None = None,
    ) -> None:
        self._memos = memos
        self._kg = kg or getattr(memos, "_kg", None) or KnowledgeGraph()
        self._memos._kg = self._kg
        self._bridge = getattr(memos, "_kg_bridge", None) or KGBridge(memos, self._kg)
        self._memos._kg_bridge = self._bridge
        self._wiki = LivingWikiEngine(memos, wiki_dir=wiki_dir)

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_tags: list[str] | None = None,
        min_score: float = 0.0,
        retrieval_mode: str = "hybrid",
        max_context_chars: int = 2000,
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
        return BrainSearchResult(
            query=query,
            memories=memories[:top_k],
            wiki_pages=wiki_pages[:top_k],
            kg_facts=kg_facts[:top_k],
            entities=entities,
            context=context,
        )

    def _score_memories(self, results: list[Any]) -> list[ScoredMemory]:
        max_score = max((float(getattr(r, "score", 0.0)) for r in results), default=1.0) or 1.0
        scored: list[ScoredMemory] = []
        for result in results:
            item = result.item
            raw_score = float(getattr(result, "score", 0.0))
            scored.append(
                ScoredMemory(
                    id=item.id,
                    content=item.content,
                    tags=list(item.tags),
                    importance=float(item.importance),
                    score=round(raw_score / max_score, 4),
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
            bonus = 0.15 if entity.lower() in query_lower else 0.0
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
            "EXTRACTED": 1.0,
            "INFERRED": 0.85,
            "AMBIGUOUS": 0.65,
        }
        scored: list[KGFact] = []
        for fact in raw_facts:
            subject = str(fact.get("subject", ""))
            obj = str(fact.get("object", ""))
            label = str(fact.get("confidence_label", "EXTRACTED"))
            direct_match = 0.2 if subject.lower() in query_lower or obj.lower() in query_lower else 0.0
            score = min(1.0, label_weight.get(label, 0.7) + direct_match)
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
            "memory": [
                (item.score, f"[memory {item.score:.2f}] {item.content}")
                for item in memories[:5]
            ],
            "wiki": [
                (item.score, f"[wiki {item.entity}] {item.snippet}")
                for item in wiki_pages[:5]
            ],
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
    def _snippet(content: str, query: str, window: int = 80) -> str:
        lowered = content.lower()
        query_lower = query.lower()
        idx = lowered.find(query_lower)
        if idx == -1:
            return content[: window * 2].replace("\n", " ").strip()
        start = max(0, idx - window)
        end = min(len(content), idx + len(query) + window)
        return content[start:end].replace("\n", " ").strip()
