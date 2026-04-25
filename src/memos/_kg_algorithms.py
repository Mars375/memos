"""Compatibility exports for KnowledgeGraph algorithms."""

from __future__ import annotations

from ._kg_centrality import god_nodes, surprising_connections
from ._kg_communities import detect_communities
from ._kg_inference import infer_transitive

__all__ = [
    "detect_communities",
    "god_nodes",
    "infer_transitive",
    "surprising_connections",
]
