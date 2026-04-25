"""Unified Brain Search public compatibility module.

The implementation lives in focused private modules. Importing from
``memos.brain`` remains supported for public API compatibility.
"""

from __future__ import annotations

from ._brain_facade import BrainSearch
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
