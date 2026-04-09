"""Unified Brain Search and entity views for MemOS.

An agent should not need to know *where* information lives. BrainSearch
orchestrates retrieval across memories, wiki pages, and the knowledge graph,
and can also return unified per-entity views for the dashboard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
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
class EntityNeighbor:
    """A neighboring entity in the knowledge graph."""

    entity: str
    fact_count: int = 0
    predicates: list[str] = field(default_factory=list)
    community: Optional[str] = None
    degree: int = 0
    is_god_node: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "fact_count": self.fact_count,
            "predicates": self.predicates,
            "community": self.community,
            "degree": self.degree,
            "is_god_node": self.is_god_node,
        }


@dataclass
class EntityDetailResult:
    """Unified detail view for an entity."""

    entity: str
    wiki_page: str = ""
    memories: list[ScoredMemory] = field(default_factory=list)
    kg_facts: list[KGFactHit] = field(default_factory=list)
    kg_neighbors: list[EntityNeighbor] = field(default_factory=list)
    backlinks: list[str] = field(default_factory=list)
    community: Optional[str] = None
    is_god_node: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "wiki_page": self.wiki_page,
            "memories": [m.to_dict() for m in self.memories],
            "kg_facts": [f.to_dict() for f in self.kg_facts],
            "kg_neighbors": [n.to_dict() for n in self.kg_neighbors],
            "backlinks": self.backlinks,
            "community": self.community,
            "is_god_node": self.is_god_node,
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
    r'"([^"]+)"'
    r"|'([^']+)'"
    r"|([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"
    r"|([A-Z]{2,}(?:\s+[A-Z]+)*)"
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

    for match in _ENTITY_RE.finditer(query):
        for group in match.groups():
            if group:
                _add(group)

    for word in re.findall(r"\b[A-Z][a-z]+\b", query):
        _add(word)

    return entities


# ---------------------------------------------------------------------------
# Frontmatter / markdown helpers
# ---------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    meta: dict[str, Any] = {}
    block = text[4:end]
    body = text[end + 5 :]
    current_list: Optional[str] = None

    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list:
            meta.setdefault(current_list, []).append(line[4:].strip().strip('"'))
            continue
        current_list = None
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not value:
            meta[key] = []
            current_list = key
            continue
        value = value.strip('"')
        if value.lower() in {"true", "false"}:
            meta[key] = value.lower() == "true"
            continue
        try:
            meta[key] = int(value)
            continue
        except ValueError:
            pass
        try:
            meta[key] = float(value)
            continue
        except ValueError:
            pass
        meta[key] = value

    return meta, body



def _render_frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f'  - "{item}"')
        elif isinstance(value, str):
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)



def _replace_section(body: str, title: str, lines: list[str]) -> str:
    section_lines = [f"## {title}", "", *(lines or ["- None."])]
    section = "\n".join(section_lines).rstrip() + "\n"
    pattern = re.compile(rf"(?ms)^## {re.escape(title)}\n.*?(?=^## |\Z)")
    body = body.strip()
    if pattern.search(body):
        updated = pattern.sub(section, body)
    else:
        updated = body + ("\n\n" if body else "") + section
    return updated.strip() + "\n"



def _strip_frontmatter(text: str) -> str:
    _, body = _split_frontmatter(text)
    return body.strip() if body else text.strip()


# ---------------------------------------------------------------------------
# BrainSearch orchestrator
# ---------------------------------------------------------------------------

class BrainSearch:
    """Orchestrate search across memories, wiki, and KG."""

    def __init__(self, memos: Any) -> None:
        self._memos = memos

    # -- sub-component accessors (lazy) --

    def _get_kg(self) -> Any:
        from .knowledge_graph import KnowledgeGraph

        kg = getattr(self._memos, "_kg", None)
        if kg is None:
            kg = KnowledgeGraph(db_path=getattr(self._memos, "_kg_db_path", None))
            self._memos._kg = kg
        return kg

    def _get_wiki(self) -> Any:
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

    def _get_graph_wiki(self) -> Any:
        from .wiki_graph import GraphWikiEngine

        graph_wiki = getattr(self._memos, "_graph_wiki", None)
        if graph_wiki is None:
            graph_wiki = GraphWikiEngine(self._get_kg())
            self._memos._graph_wiki = graph_wiki
        return graph_wiki

    def _get_graph_analysis(self) -> dict[str, Any]:
        try:
            return self._get_graph_wiki().analyze()
        except Exception:
            return {
                "facts": [],
                "adjacency": {},
                "bridge_nodes": [],
                "communities": [],
                "entity_to_community": {},
                "degrees": {},
                "facts_by_community": {},
                "cross_facts_by_community": {},
                "backlinks": {},
                "god_nodes": {},
            }

    def _get_kg_bridge(self) -> Any:
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
        entities = _extract_entities(query)

        memory_hits: list[ScoredMemory] = []
        if include_memories:
            try:
                results = list(self._memos.recall(query, top=top_k))
                for result in results:
                    memory_hits.append(
                        ScoredMemory(
                            id=result.item.id,
                            content=result.item.content,
                            score=result.score,
                            tags=result.item.tags,
                            importance=result.item.importance,
                            match_reason=result.match_reason,
                        )
                    )
            except Exception:
                pass

        wiki_hits: list[WikiHit] = []
        if include_wiki:
            wiki = self._get_wiki()
            if wiki is not None:
                try:
                    wiki_results = wiki.search(query)
                    for wiki_result in wiki_results[:top_k]:
                        wiki_hits.append(
                            WikiHit(
                                entity=wiki_result.get("entity", ""),
                                type=wiki_result.get("type", "default"),
                                matches=wiki_result.get("matches", 0),
                                snippet=wiki_result.get("snippet", ""),
                            )
                        )
                except Exception:
                    pass

        kg_hits: list[KGFactHit] = []
        if include_kg:
            kg = self._get_kg()
            if kg is not None:
                seen_ids: set[str] = set()
                try:
                    for entity in entities:
                        for fact in kg.query(entity):
                            if fact["id"] not in seen_ids:
                                seen_ids.add(fact["id"])
                                kg_hits.append(self._fact_to_hit(fact))
                    for fact in kg.search_entities(query):
                        for linked in kg.query(fact["name"]):
                            if linked["id"] not in seen_ids:
                                seen_ids.add(linked["id"])
                                kg_hits.append(self._fact_to_hit(linked))
                except Exception:
                    pass
                kg_hits = kg_hits[:top_k]

        context = self._build_context(query, entities, memory_hits, wiki_hits, kg_hits)
        return BrainSearchResult(
            query=query,
            memories=memory_hits,
            wiki_pages=wiki_hits,
            kg_facts=kg_hits,
            entities=entities,
            context=context,
        )

    # -- entity views --

    def entity_detail(
        self,
        entity: str,
        *,
        memory_top: int = 5,
        neighbor_top: int = 12,
    ) -> EntityDetailResult:
        entity = self._resolve_entity_name(entity)
        kg = self._get_kg()
        wiki = self._get_wiki()
        analysis = self._get_graph_analysis()

        page_path: Optional[Path] = None
        backlinks: list[str] = []
        wiki_page = ""
        if wiki is not None:
            try:
                wiki.update(force=False)
                for page in wiki.list_pages():
                    if page.entity.lower() == entity.lower():
                        entity = page.entity
                        page_path = page.path
                        backlinks = page.backlinks
                        break
                wiki_page = wiki.read_page(entity) or ""
            except Exception:
                wiki_page = ""

        fact_rows = kg.query(entity)
        kg_facts = [self._fact_to_hit(fact) for fact in fact_rows]
        memories = self._entity_memories(entity, top_k=memory_top)
        neighbors = self._entity_neighbors(entity, fact_rows, analysis, limit=neighbor_top)
        if not backlinks:
            backlinks = sorted({neighbor.entity for neighbor in neighbors})

        community = analysis.get("entity_to_community", {}).get(entity)
        is_god_node = entity in analysis.get("god_nodes", {})
        wiki_page = self._enrich_wiki_page(
            entity=entity,
            wiki_page=wiki_page,
            community=community,
            backlinks=backlinks,
            kg_facts=kg_facts,
            neighbors=neighbors,
            memories=memories,
            page_path=page_path,
        )

        return EntityDetailResult(
            entity=entity,
            wiki_page=wiki_page,
            memories=memories,
            kg_facts=kg_facts,
            kg_neighbors=neighbors,
            backlinks=backlinks,
            community=community,
            is_god_node=is_god_node,
        )

    def entity_subgraph(self, entity: str, *, depth: int = 2) -> dict[str, Any]:
        entity = self._resolve_entity_name(entity)
        kg = self._get_kg()
        analysis = self._get_graph_analysis()
        neighborhood = kg.neighbors(entity, depth=depth)
        degrees = analysis.get("degrees", {})
        communities = analysis.get("entity_to_community", {})
        god_nodes = analysis.get("god_nodes", {})

        nodes = [
            {
                "id": name,
                "label": name,
                "entity": name,
                "kind": "entity",
                "content": self._wiki_preview(name) or name,
                "tags": [communities[name]] if communities.get(name) else [],
                "primary_tag": communities.get(name, "__entity__"),
                "importance": min(1.0, 0.2 + min(degrees.get(name, 0), 8) / 8),
                "access_count": degrees.get(name, 0),
                "age_days": 0,
                "community": communities.get(name),
                "degree": degrees.get(name, 0),
                "is_god_node": name in god_nodes,
            }
            for name in neighborhood["nodes"]
        ]
        edges = [
            {
                "id": edge["id"],
                "source": edge["subject"],
                "target": edge["object"],
                "predicate": edge["predicate"],
                "confidence": edge.get("confidence", 1.0),
                "confidence_label": edge.get("confidence_label", "EXTRACTED"),
                "weight": max(1.0, float(edge.get("confidence", 1.0))),
            }
            for edge in neighborhood["edges"]
        ]
        return {
            "center": entity,
            "depth": depth,
            "community": communities.get(entity),
            "is_god_node": entity in god_nodes,
            "nodes": nodes,
            "edges": edges,
            "layers": neighborhood["layers"],
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }

    def entity_graph(self, *, limit: int = 500) -> dict[str, Any]:
        analysis = self._get_graph_analysis()
        facts = analysis.get("facts", [])
        degrees = analysis.get("degrees", {})
        communities = analysis.get("entity_to_community", {})
        god_nodes = analysis.get("god_nodes", {})

        entity_names = sorted(
            {fact["subject"] for fact in facts} | {fact["object"] for fact in facts},
            key=lambda name: (-degrees.get(name, 0), name.lower()),
        )[:limit]
        allowed = set(entity_names)

        nodes = []
        for name in entity_names:
            community = communities.get(name)
            nodes.append(
                {
                    "id": name,
                    "label": name,
                    "entity": name,
                    "kind": "entity",
                    "content": self._wiki_preview(name) or name,
                    "tags": [community] if community else [],
                    "primary_tag": community or "__entity__",
                    "importance": min(1.0, 0.2 + min(degrees.get(name, 0), 8) / 8),
                    "access_count": degrees.get(name, 0),
                    "age_days": 0,
                    "community": community,
                    "degree": degrees.get(name, 0),
                    "is_god_node": name in god_nodes,
                    "community_count": len(god_nodes.get(name, [])),
                }
            )

        edges = [
            {
                "id": fact["id"],
                "source": fact["subject"],
                "target": fact["object"],
                "predicate": fact["predicate"],
                "confidence": fact.get("confidence", 1.0),
                "confidence_label": fact.get("confidence_label", "EXTRACTED"),
                "weight": max(1.0, float(fact.get("confidence", 1.0))),
            }
            for fact in facts
            if fact["subject"] in allowed and fact["object"] in allowed
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "graph_kind": "entity",
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_memories": getattr(self._memos.stats(), "total_memories", 0),
                "total_tags": getattr(self._memos.stats(), "total_tags", 0),
                "community_count": len(analysis.get("communities", [])),
                "god_nodes": len(god_nodes),
            },
        }

    # -- helpers --

    @staticmethod
    def _fact_to_hit(fact: dict[str, Any]) -> KGFactHit:
        return KGFactHit(
            id=fact["id"],
            subject=fact["subject"],
            predicate=fact["predicate"],
            object=fact["object"],
            confidence=fact.get("confidence", 1.0),
            confidence_label=fact.get("confidence_label", "EXTRACTED"),
        )

    def _resolve_entity_name(self, entity: str) -> str:
        entity = entity.strip()
        if not entity:
            return entity

        kg = self._get_kg()
        try:
            for hit in kg.search_entities(entity):
                if hit["name"].lower() == entity.lower():
                    return hit["name"]
            if kg.search_entities(entity):
                return kg.search_entities(entity)[0]["name"]
        except Exception:
            pass

        wiki = self._get_wiki()
        if wiki is not None:
            try:
                for page in wiki.list_pages():
                    if page.entity.lower() == entity.lower():
                        return page.entity
            except Exception:
                pass
        return entity

    def _entity_memories(self, entity: str, *, top_k: int = 5) -> list[ScoredMemory]:
        entity_lower = entity.lower()
        collected: dict[str, ScoredMemory] = {}

        try:
            store_items = self._memos._store.list_all(namespace=self._memos._namespace)
        except Exception:
            store_items = []

        for item in store_items:
            if getattr(item, "is_expired", False):
                continue
            content_lower = item.content.lower()
            mention_count = content_lower.count(entity_lower)
            tag_match = any(tag.lower() == entity_lower for tag in getattr(item, "tags", []))
            if mention_count <= 0 and not tag_match:
                continue
            score = mention_count * 1.5 + float(getattr(item, "importance", 0.5))
            score += min(float(getattr(item, "access_count", 0)), 10.0) * 0.05
            collected[item.id] = ScoredMemory(
                id=item.id,
                content=item.content,
                score=score,
                tags=list(getattr(item, "tags", [])),
                importance=float(getattr(item, "importance", 0.5)),
                match_reason="content mention" if mention_count > 0 else "tag match",
            )

        try:
            recall_results = self._memos.recall(entity, top=max(top_k * 3, 10))
            for result in recall_results:
                item = result.item
                if item.id in collected:
                    collected[item.id].score = max(collected[item.id].score, result.score)
                    continue
                collected[item.id] = ScoredMemory(
                    id=item.id,
                    content=item.content,
                    score=result.score,
                    tags=item.tags,
                    importance=item.importance,
                    match_reason=result.match_reason,
                )
        except Exception:
            pass

        ranked = sorted(
            collected.values(),
            key=lambda memory: (-memory.score, -memory.importance, memory.id),
        )
        return ranked[:top_k]

    def _entity_neighbors(
        self,
        entity: str,
        facts: list[dict[str, Any]],
        analysis: dict[str, Any],
        *,
        limit: int = 12,
    ) -> list[EntityNeighbor]:
        neighbor_map: dict[str, dict[str, Any]] = {}
        communities = analysis.get("entity_to_community", {})
        degrees = analysis.get("degrees", {})
        god_nodes = analysis.get("god_nodes", {})

        for fact in facts:
            if fact["subject"].lower() == entity.lower():
                other = fact["object"]
            else:
                other = fact["subject"]
            if other.lower() == entity.lower():
                continue
            row = neighbor_map.setdefault(
                other,
                {
                    "entity": other,
                    "fact_count": 0,
                    "predicates": set(),
                    "community": communities.get(other),
                    "degree": degrees.get(other, 0),
                    "is_god_node": other in god_nodes,
                },
            )
            row["fact_count"] += 1
            row["predicates"].add(fact["predicate"])

        neighbors = [
            EntityNeighbor(
                entity=row["entity"],
                fact_count=row["fact_count"],
                predicates=sorted(row["predicates"]),
                community=row["community"],
                degree=row["degree"],
                is_god_node=row["is_god_node"],
            )
            for row in neighbor_map.values()
        ]
        neighbors.sort(key=lambda neighbor: (-neighbor.fact_count, -neighbor.degree, neighbor.entity.lower()))
        return neighbors[:limit]

    def _wiki_preview(self, entity: str, *, max_chars: int = 220) -> str:
        wiki = self._get_wiki()
        if wiki is None:
            return ""
        try:
            content = wiki.read_page(entity) or ""
        except Exception:
            return ""
        if not content:
            return ""
        preview = re.sub(r"\s+", " ", _strip_frontmatter(content)).strip()
        return preview[:max_chars]

    def _enrich_wiki_page(
        self,
        *,
        entity: str,
        wiki_page: str,
        community: Optional[str],
        backlinks: list[str],
        kg_facts: list[KGFactHit],
        neighbors: list[EntityNeighbor],
        memories: list[ScoredMemory],
        page_path: Optional[Path],
    ) -> str:
        meta, body = _split_frontmatter(wiki_page)
        if not body.strip():
            body = f"# {entity}\n\n## Overview\n\nAuto-generated entity view.\n"

        meta.setdefault("entity", entity)
        meta["community"] = community or ""
        meta["kg_facts_count"] = len(kg_facts)
        meta["backlinks_count"] = len(backlinks)
        meta["top_memories"] = [memory.id for memory in memories[:3]]

        body = _replace_section(
            body,
            "Graph Neighbors",
            [
                f"- [[{neighbor.entity}]] — {', '.join(neighbor.predicates)} ({neighbor.fact_count} fact{'s' if neighbor.fact_count != 1 else ''})"
                for neighbor in neighbors
            ],
        )
        body = _replace_section(
            body,
            "Backlinks",
            [f"- [[{backlink}]]" for backlink in backlinks],
        )
        body = _replace_section(
            body,
            "Top Memories",
            [
                f"- `{memory.id[:8]}` — {memory.content[:180]}"
                for memory in memories
            ],
        )

        rendered = _render_frontmatter(meta) + "\n\n" + body.strip() + "\n"
        if page_path is not None and page_path.exists():
            try:
                current = page_path.read_text(encoding="utf-8")
                if current != rendered:
                    page_path.write_text(rendered, encoding="utf-8")
            except Exception:
                pass
        return rendered

    # -- context builder --

    @staticmethod
    def _build_context(
        query: str,
        entities: list[str],
        memories: list[ScoredMemory],
        wiki_pages: list[WikiHit],
        kg_facts: list[KGFactHit],
    ) -> str:
        parts: list[str] = []
        parts.append(f'## Brain Search: "{query}"')

        if entities:
            parts.append(f"\n**Entities detected**: {', '.join(entities)}")

        if memories:
            parts.append(f"\n### Memories ({len(memories)})")
            for memory in memories[:5]:
                tag_str = f" [{', '.join(memory.tags[:3])}]" if memory.tags else ""
                parts.append(f"- [{memory.score:.2f}] {memory.content[:200]}{tag_str}")
            if len(memories) > 5:
                parts.append(f"- ... and {len(memories) - 5} more")

        if wiki_pages:
            parts.append(f"\n### Wiki Pages ({len(wiki_pages)})")
            for wiki_page in wiki_pages[:5]:
                parts.append(f"- **{wiki_page.entity}** ({wiki_page.type}): {wiki_page.snippet[:150]}")
            if len(wiki_pages) > 5:
                parts.append(f"- ... and {len(wiki_pages) - 5} more")

        if kg_facts:
            parts.append(f"\n### Knowledge Graph Facts ({len(kg_facts)})")
            for fact in kg_facts[:5]:
                parts.append(
                    f"- {fact.subject} → {fact.predicate} → {fact.object} "
                    f"[{fact.confidence_label}, {fact.confidence:.1f}]"
                )
            if len(kg_facts) > 5:
                parts.append(f"- ... and {len(kg_facts) - 5} more")

        if not memories and not wiki_pages and not kg_facts:
            parts.append("\n_No results found across any knowledge layer._")

        return "\n".join(parts)
