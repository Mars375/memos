"""Hierarchical Palace compatibility facade.

Provides a 2-level hierarchy:
  Wing — top-level domain (person, project, agent, workspace …)
  Room — thematic category inside a wing (auth, deployment, api …)

Public imports from ``memos.palace`` remain supported.
"""

from __future__ import annotations

from ._palace_base import PalaceSQLiteBase
from ._palace_diary import PalaceDiaryMixin
from ._palace_hierarchy import PalaceHierarchyMixin
from ._palace_recall import PalaceRecall


class PalaceIndex(PalaceSQLiteBase, PalaceHierarchyMixin, PalaceDiaryMixin):
    """SQLite-backed index of Wings, Rooms and memory assignments."""


__all__ = ["PalaceIndex", "PalaceRecall"]
