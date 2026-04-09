"""Unified Brain Search — one query searches memories, wiki pages, and KG facts.

An agent should not need to know *where* information lives. BrainSearch
orchestrates retrieval across all three knowledge layers and returns a
single, fused result set plus a context string ready to inject into a prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScoredMemory:
    """A memory hit with its relevance score."""

    id: str
    content: str
    score: float
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    match_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "score": round(self.score, 4),
            "tags": self.tags,
            "importance": round(self.importance, 3),
            "match_reason": self.match_reason,
        }


@dataclass
class WikiHit:
    """A wiki page matching the query."""

    entity: str
    type: str = "default"
    matches: int = 0
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "type": self.type,
            "matches": self.matches,
            "snippet": self.snippet,
        }


@dataclass
class KGFactHit:
    """A KG fact matching the query."""

    id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    confidence_label: str = "EXTRACTED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
        }


@dataclass
class BrainSearchResult:
    """Fused result from all knowledge layers."""

    query: str
    memories: list[ScoredMemory] = field(default_factory=list)
    wiki_pages: list[WikiHit] = field(default_factory=list)
    kg_facts: list[KGFactHit] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    context: str = ""

    @property
    def total_hits(self) -> int:
        return len(self.memories) + len(self.wiki_pages) + len(self.kg_facts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "entities": self.entities,
            "memories": [m.to_dict() for m in self.memories],
            "wiki_pages": [w.to_dict() for w in self.wiki_pages],
            "kg_facts": [f.to_dict() for f in self.kg_facts],
            "context": self.context,
            "total_hits": self.total_hits,
            "memory_count": len(self.memories),
            "wiki_count": len(self.wiki_pages),
            "fact_count": len(self.kg_facts),
        }


# ---------------------------------------------------------------------------
# Entity extraction (lightweight, zero-LLM)
# ---------------------------------------------------------------------------

# PascalCase words, ALLCAPS 2+, quoted names
_ENTITY_RE = re.compile(
    r'"([^"]+)"'                  # "quoted names"
    r"|'([^']+)'"                 # 'quoted names'
    r"|([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"  # PascalCase multi-word
    r"|([A-Z]{2,}(?:\s+[A-Z]+)*)"         # ALLCAPS tokens
)


def _extract_entities(query: str) -> list[str]:
    """Lightweight entity extraction from a query string."""
    seen: set[str] = set()
    entities: list[str] = []

    def _add(name: str) -> None:
        name = name.strip()
        if not name or len(name) < 2:
            return
        key = name.lower()
        if key not in seen:
            seen.add(key)
            entities.append(name)

    for m in _ENTITY_RE.finditer(query):
        for group in m.groups():
            if group:
                _add(group)

    # Also add capitalized words (potential proper nouns)
    for word in re.findall(r"\b[A-Z][a-z]+\b", query):
        _add(word)

    return entities


# ---------------------------------------------------------------------------
# BrainSearch orchestrator
# ---------------------------------------------------------------------------

class BrainSearch:
    """Orchestrate search across memories, wiki, and KG.

    Usage::

        brain = BrainSearch(memos)
        result = brain.search("Alice Acme infrastructure")
        print(result.context)  # ready-to-inject summary
    """

    def __init__(self, memos: Any) -> None:
        self._memos = memos

    # -- sub-component accessors (lazy) --

    def _get_kg(self) -> Any:
        """Return the KnowledgeGraph instance, creating if needed."""
        from .knowledge_graph import KnowledgeGraph
        kg = getattr(self._memos, "_kg", None)
        if kg is None:
            kg = KnowledgeGraph()
            self._memos._kg = kg
        return kg

    def _get_wiki(self) -> Any:
        """Return the LivingWikiEngine instance, creating if needed."""
        try:
            from .wiki_living import LivingWikiEngine
        except ImportError:
            return None
        wiki = getattr(self._memos, "_living_wiki", None)
        if wiki is None:
            try:
                wiki = LivingWikiEngine(self._memos)
                self._memos._living_wiki = wiki
            except Exception:
                return None
        return wiki

    def _get_kg_bridge(self) -> Any:
        """Return the KGBridge instance."""
        from .kg_bridge import KGBridge
        bridge = getattr(self._memos, "_kg_bridge", None)
        if bridge is None:
            bridge = KGBridge(self._memos, self._get_kg())
            self._memos._kg_bridge = bridge
        return bridge

    # -- main search --

    def search(
        self,
        query: str,
        top_k: int = 10,
        *,
        include_memories: bool = True,
        include_wiki: bool = True,
        include_kg: bool = True,
    ) -> BrainSearchResult:
        """Search all knowledge layers and return a fused result.

        Parameters
        ----------
        query:
            The search query.
        top_k:
            Maximum results per layer.
        include_memories / include_wiki / include_kg:
            Toggle individual layers.

        Returns
        -------
        BrainSearchResult with memories, wiki pages, KG facts, detected
        entities, and a context string ready for prompt injection.
        """
        # 1. Detect entities
        entities = _extract_entities(query)

        # 2. Search memories
        memory_hits: list[ScoredMemory] = []
        if include_memories:
            try:
                results = list(self._memos.recall(query, top=top_k))
                for r in results:
                    memory_hits.append(ScoredMemory(
                        id=r.item.id,
                        content=r.item.content,
                        score=r.score,
                        tags=r.item.tags,
                        importance=r.item.importance,
                        match_reason=r.match_reason,
                    ))
            except Exception:
                pass

        # 3. Search wiki pages
        wiki_hits: list[WikiHit] = []
        if include_wiki:
            wiki = self._get_wiki()
            if wiki is not None:
                try:
                    wiki_results = wiki.search(query)
                    for w in wiki_results[:top_k]:
                        wiki_hits.append(WikiHit(
                            entity=w.get("entity", ""),
                            type=w.get("type", "default"),
                            matches=w.get("matches", 0),
                            snippet=w.get("snippet", ""),
                        ))
                except Exception:
                    pass

        # 4. Search KG facts
        kg_hits: list[KGFactHit] = []
        if include_kg:
            kg = self._get_kg()
            if kg is not None:
                seen_ids: set[str] = set()
                try:
                    # Search by detected entities
                    for entity in entities:
                        for fact in kg.query(entity):
                            if fact["id"] not in seen_ids:
                                seen_ids.add(fact["id"])
                                kg_hits.append(KGFactHit(
                                    id=fact["id"],
                                    subject=fact["subject"],
                                    predicate=fact["predicate"],
                                    object=fact["object"],
                                    confidence=fact.get("confidence", 1.0),
                                    confidence_label=fact.get("confidence_label", "EXTRACTED"),
                                ))
                    # Also search by query substring
                    for fact in kg.search_entities(query):
                        for linked in kg.query(fact["name"]):
                            if linked["id"] not in seen_ids:
                                seen_ids.add(linked["id"])
                                kg_hits.append(KGFactHit(
                                    id=linked["id"],
                                    subject=linked["subject"],
                                    predicate=linked["predicate"],
                                    object=linked["object"],
                                    confidence=linked.get("confidence", 1.0),
                                    confidence_label=linked.get("confidence_label", "EXTRACTED"),
                                ))
                except Exception:
                    pass
                kg_hits = kg_hits[:top_k]

        # 5. Build context string (token-efficient, ready to inject)
        context = self._build_context(query, entities, memory_hits, wiki_hits, kg_hits)

        return BrainSearchResult(
            query=query,
            memories=memory_hits,
            wiki_pages=wiki_hits,
            kg_facts=kg_hits,
            entities=entities,
            context=context,
        )

    # -- context builder --

    @staticmethod
    def _build_context(
        query: str,
        entities: list[str],
        memories: list[ScoredMemory],
        wiki_pages: list[WikiHit],
        kg_facts: list[KGFactHit],
    ) -> str:
        """Build a compact context string for prompt injection."""
        parts: list[str] = []
        parts.append(f"## Brain Search: \"{query}\"")

        if entities:
            parts.append(f"\n**Entities detected**: {', '.join(entities)}")

        if memories:
            parts.append(f"\n### Memories ({len(memories)})")
            for m in memories[:5]:
                tag_str = f" [{', '.join(m.tags[:3])}]" if m.tags else ""
                parts.append(f"- [{m.score:.2f}] {m.content[:200]}{tag_str}")
            if len(memories) > 5:
                parts.append(f"- ... and {len(memories) - 5} more")

        if wiki_pages:
            parts.append(f"\n### Wiki Pages ({len(wiki_pages)})")
            for w in wiki_pages[:5]:
                parts.append(f"- **{w.entity}** ({w.type}): {w.snippet[:150]}")
            if len(wiki_pages) > 5:
                parts.append(f"- ... and {len(wiki_pages) - 5} more")

        if kg_facts:
            parts.append(f"\n### Knowledge Graph Facts ({len(kg_facts)})")
            for f in kg_facts[:5]:
                parts.append(
                    f"- {f.subject} → {f.predicate} → {f.object} "
                    f"[{f.confidence_label}, {f.confidence:.1f}]"
                )
            if len(kg_facts) > 5:
                parts.append(f"- ... and {len(kg_facts) - 5} more")

        if not memories and not wiki_pages and not kg_facts:
            parts.append("\n_No results found across any knowledge layer._")

        return "\n".join(parts)
