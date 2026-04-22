"""Unified Brain Search across memories, wiki pages, and knowledge graph."""

from __future__ import annotations

from typing import Any

from ._brain_analytics import _BrainAnalyticsMixin
from ._brain_entity import _BrainEntityMixin
from ._brain_models import (
    BrainSearchResult,
    EntityDetail,
    EntityNeighbor,
    EntitySubgraph,
    KGFact,
    ScoredMemory,
    SuggestedQuestion,
    WikiHit,
)
from ._brain_search import _BrainSearchMixin
from .kg_bridge import KGBridge
from .knowledge_graph import KnowledgeGraph
from .wiki_living import LivingWikiEngine

__all__ = [
    "BrainSearch",
    "BrainSearchResult",
    "EntityDetail",
    "EntityNeighbor",
    "EntitySubgraph",
    "KGFact",
    "ScoredMemory",
    "SuggestedQuestion",
    "WikiHit",
]


class BrainSearch(
    _BrainSearchMixin,
    _BrainEntityMixin,
    _BrainAnalyticsMixin,
):
    """Unified search facade across memory, living wiki, and knowledge graph."""

    PREFERENCE_BOOST_FACTOR = 0.15

    def __init__(
        self,
        memos: Any,
        kg: KnowledgeGraph | None = None,
        wiki_dir: str | None = None,
        analytics: Any | None = None,
    ) -> None:
        self._memos = memos
        self._kg = kg or getattr(memos, "kg", None) or KnowledgeGraph()
        memos.kg = self._kg

        existing_bridge = getattr(memos, "kg_bridge", None)
        if existing_bridge is not None and getattr(existing_bridge, "kg", None) is not self._kg:
            existing_bridge = None
        self._bridge = existing_bridge or KGBridge(memos, self._kg)
        memos.kg_bridge = self._bridge

        self._wiki = LivingWikiEngine(memos, wiki_dir=wiki_dir)

        self._analytics = analytics
