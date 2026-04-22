"""Data models for Brain Search results and entity structures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


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
