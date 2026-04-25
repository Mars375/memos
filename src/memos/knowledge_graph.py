"""Temporal Knowledge Graph public compatibility module.

The implementation lives in ``memos._kg_core`` with focused helper modules for
facts, queries, paths, algorithms, and linting. Importing ``KnowledgeGraph``
from ``memos.knowledge_graph`` remains the supported public API.
"""

from __future__ import annotations

from ._kg_core import KnowledgeGraph

__all__ = ["KnowledgeGraph"]
