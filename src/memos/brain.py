"""Unified Brain Search across memories, wiki pages, and knowledge graph."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ._constants import (
    DEFAULT_SNIPPET_WINDOW,
    KG_DIRECT_MATCH_BONUS,
    KG_WEIGHT_AMBIGUOUS,
    KG_WEIGHT_DEFAULT,
    KG_WEIGHT_EXTRACTED,
    KG_WEIGHT_INFERRED,
    WIKI_ENTITY_IN_QUERY_BONUS,
)
from .kg_bridge import KGBridge
from .knowledge_graph import KnowledgeGraph
from .wiki_graph import GraphWikiEngine
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


@dataclass
class SuggestedQuestion:
    question: str
    category: str
    score: float
    entities: list[str]


@dataclass
class EntityNeighbor:
    entity: str
    relation_count: int
    predicates: list[str]


@dataclass
class EntitySubgraph:
    center: str
    depth: int
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    layers: dict[int, list[str]]


@dataclass
class EntityDetail:
    entity: str
    wiki_page: str
    memories: list[dict[str, Any]]
    kg_facts: list[dict[str, Any]]
    kg_neighbors: list[EntityNeighbor]
    backlinks: list[str]
    community: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "wiki_page": self.wiki_page,
            "memories": list(self.memories),
            "kg_facts": list(self.kg_facts),
            "kg_neighbors": [asdict(item) for item in self.kg_neighbors],
            "backlinks": list(self.backlinks),
            "community": self.community,
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

        existing_bridge = getattr(memos, "_kg_bridge", None)
        if existing_bridge is not None and getattr(existing_bridge, "kg", None) is not self._kg:
            existing_bridge = None
        self._bridge = existing_bridge or KGBridge(memos, self._kg)
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

    def entity_detail(
        self,
        entity: str,
        *,
        top_memories: int = 5,
        neighbor_limit: int = 12,
    ) -> EntityDetail:
        canonical = self._canonical_entity_name(entity)
        self._ensure_wiki_page(canonical)

        wiki_page = self._wiki.read_page(canonical) or ""
        memories = self._entity_memories(canonical, top=top_memories)
        kg_facts = self._entity_kg_facts(canonical)
        kg_neighbors = self._entity_neighbors(canonical, limit=neighbor_limit)
        backlinks = self._entity_backlinks(canonical)

        if not wiki_page:
            wiki_page = self._render_fallback_wiki(canonical, memories, kg_facts, backlinks)

        return EntityDetail(
            entity=canonical,
            wiki_page=wiki_page,
            memories=memories,
            kg_facts=kg_facts,
            kg_neighbors=kg_neighbors,
            backlinks=backlinks,
            community=self._community_for_entity(canonical),
        )

    def entity_subgraph(self, entity: str, depth: int = 2) -> EntitySubgraph:
        canonical = self._canonical_entity_name(entity)
        neighborhood = self._kg.neighbors(canonical, depth=depth, direction="both")
        nodes = [{"id": name, "label": name, "is_center": name == canonical} for name in neighborhood["nodes"]]
        edges = [
            {
                "id": edge["id"],
                "source": edge["subject"],
                "target": edge["object"],
                "predicate": edge["predicate"],
                "confidence": edge["confidence"],
                "confidence_label": edge.get("confidence_label", "EXTRACTED"),
            }
            for edge in neighborhood["edges"]
        ]
        return EntitySubgraph(
            center=canonical,
            depth=depth,
            nodes=nodes,
            edges=edges,
            layers=neighborhood["layers"],
        )

    def suggest_questions(self, top_k: int = 5) -> list[SuggestedQuestion]:
        """Generate suggested exploration questions based on the KG structure.

        Combines three question sources:
        1. Hub exploration from god nodes (high-degree entities)
        2. Cross-community questions from surprising connections
        3. Orphan entity exploration (entities mentioned only once)

        Returns up to *top_k* suggestions sorted by relevance score.
        """
        candidates: list[SuggestedQuestion] = []

        # 1. Hub exploration questions from god nodes
        god_nodes = self._kg.god_nodes(top_k=20)
        max_degree = max((n["degree"] for n in god_nodes), default=1) or 1
        for node in god_nodes:
            entity = node["entity"]
            degree = node["degree"]
            score = round(degree / max_degree, 4)
            candidates.append(
                SuggestedQuestion(
                    question=f"What is connected to {entity}?",
                    category="hub_exploration",
                    score=score,
                    entities=[entity],
                )
            )

        # 2. Cross-community questions from surprising connections
        surprising = self._kg.surprising_connections(top_k=20)
        max_surprise = max((c["surprise_score"] for c in surprising), default=1.0) or 1.0
        for conn in surprising:
            subject = conn["subject"]
            obj = conn["object"]
            surprise = conn["surprise_score"]
            score = round(surprise / max_surprise, 4)
            candidates.append(
                SuggestedQuestion(
                    question=f"How does {subject} relate to {obj}?",
                    category="cross_community",
                    score=score,
                    entities=[subject, obj],
                )
            )

        # 3. Orphan entities (degree == 1) — suggest exploration
        orphans = self._find_orphan_entities()
        for entity in orphans:
            candidates.append(
                SuggestedQuestion(
                    question=f"Tell me more about {entity}",
                    category="orphan_exploration",
                    score=0.3,
                    entities=[entity],
                )
            )

        # Sort by score descending, then alphabetically for stable order
        candidates.sort(key=lambda q: (-q.score, q.question))
        return candidates[:top_k]

    def _find_orphan_entities(self) -> list[str]:
        """Find entities that appear in only a single KG fact (degree == 1)."""
        rows = self._kg._conn.execute(
            "SELECT subject, object FROM triples WHERE invalidated_at IS NULL"
        ).fetchall()

        degree: dict[str, int] = {}
        for r in rows:
            degree[r["subject"]] = degree.get(r["subject"], 0) + 1
            degree[r["object"]] = degree.get(r["object"], 0) + 1

        orphans = sorted(entity for entity, deg in degree.items() if deg == 1)
        return orphans[:20]

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

    def _canonical_entity_name(self, entity: str) -> str:
        entity = " ".join(entity.split()).strip()
        if not entity:
            return entity
        matches = self._kg.search_entities(entity)
        for hit in matches:
            if hit["name"].lower() == entity.lower():
                return hit["name"]
        page = next((page for page in self._wiki.list_pages() if page.entity.lower() == entity.lower()), None)
        if page:
            return page.entity
        return matches[0]["name"] if matches else entity

    def _ensure_wiki_page(self, entity: str) -> None:
        if self._wiki.read_page(entity):
            return
        self._wiki.update(force=False)

    def _entity_memories(self, entity: str, top: int) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        seen: set[str] = set()
        db = self._wiki._get_db()
        try:
            rows = db.execute(
                "SELECT memory_id, snippet, added_at FROM entity_memories WHERE LOWER(entity_name)=LOWER(?) ORDER BY added_at DESC",
                (entity,),
            ).fetchall()
        finally:
            db.close()

        for row in rows:
            item = self._memos._store.get(row["memory_id"], namespace=self._memos._namespace)
            if item is None or item.id in seen:
                continue
            seen.add(item.id)
            ranked.append(
                {
                    "id": item.id,
                    "content": item.content,
                    "tags": list(item.tags),
                    "importance": float(item.importance),
                    "created_at": float(item.created_at),
                    "access_count": int(getattr(item, "access_count", 0)),
                    "source": "wiki_link",
                }
            )

        if len(ranked) < top:
            entity_lower = entity.lower()
            for item in self._memos._store.list_all(namespace=self._memos._namespace):
                haystacks = [item.content.lower(), *[str(tag).lower() for tag in item.tags]]
                if entity_lower not in " ".join(haystacks) or item.id in seen:
                    continue
                seen.add(item.id)
                ranked.append(
                    {
                        "id": item.id,
                        "content": item.content,
                        "tags": list(item.tags),
                        "importance": float(item.importance),
                        "created_at": float(item.created_at),
                        "access_count": int(getattr(item, "access_count", 0)),
                        "source": "content_match",
                    }
                )

        ranked.sort(
            key=lambda item: (-item["importance"], -item["created_at"], -item["access_count"]),
        )
        return ranked[:top]

    def _entity_kg_facts(self, entity: str) -> list[dict[str, Any]]:
        facts = self._kg.query(entity)
        facts.sort(key=lambda fact: (fact.get("created_at") or 0.0, fact.get("confidence") or 0.0), reverse=True)
        return facts

    def _entity_neighbors(self, entity: str, limit: int) -> list[EntityNeighbor]:
        edges = self._kg.neighbors(entity, depth=1, direction="both")["edges"]
        neighbor_meta: dict[str, dict[str, Any]] = {}
        for edge in edges:
            other = edge["object"] if edge["subject"] == entity else edge["subject"]
            meta = neighbor_meta.setdefault(other, {"count": 0, "predicates": set()})
            meta["count"] += 1
            meta["predicates"].add(edge["predicate"])
        ranked = [
            EntityNeighbor(
                entity=name,
                relation_count=meta["count"],
                predicates=sorted(meta["predicates"]),
            )
            for name, meta in neighbor_meta.items()
        ]
        ranked.sort(key=lambda item: (-item.relation_count, item.entity.lower()))
        return ranked[:limit]

    def _entity_backlinks(self, entity: str) -> list[str]:
        db = self._wiki._get_db()
        try:
            rows = db.execute(
                "SELECT target_entity FROM backlinks WHERE LOWER(source_entity)=LOWER(?) ORDER BY target_entity COLLATE NOCASE",
                (entity,),
            ).fetchall()
        finally:
            db.close()
        return [row["target_entity"] for row in rows]

    def _community_for_entity(self, entity: str) -> str | None:
        engine = GraphWikiEngine(self._kg)
        facts = engine._load_facts()
        if not facts:
            return None
        adjacency: dict[str, set[str]] = {}
        nodes: set[str] = set()
        for fact in facts:
            subject = fact["subject"]
            obj = fact["object"]
            nodes.update({subject, obj})
            adjacency.setdefault(subject, set()).add(obj)
            adjacency.setdefault(obj, set()).add(subject)
        bridge_nodes = engine._find_bridge_nodes(nodes, adjacency)
        communities = engine._detect_communities(nodes, adjacency, bridge_nodes=bridge_nodes)
        for community in communities:
            if entity in community.entities:
                return community.community_id
        return None

    def _render_fallback_wiki(
        self,
        entity: str,
        memories: list[dict[str, Any]],
        kg_facts: list[dict[str, Any]],
        backlinks: list[str],
    ) -> str:
        lines = [f"# {entity}", "", "## Overview", ""]
        if memories:
            lines.append(memories[0]["content"])
        else:
            lines.append("No living wiki page yet for this entity.")
        lines.extend(["", "## Key Facts", ""])
        if kg_facts:
            for fact in kg_facts[:8]:
                lines.append(f"- {fact['subject']} -{fact['predicate']}-> {fact['object']}")
        else:
            lines.append("- No graph facts yet.")
        lines.extend(["", "## Backlinks", ""])
        if backlinks:
            lines.extend(f"- {name}" for name in backlinks[:12])
        else:
            lines.append("- No backlinks yet.")
        return "\n".join(lines)

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
