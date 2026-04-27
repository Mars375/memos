"""Scoped recall helper for the memory palace."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from .models import RecallResult

if TYPE_CHECKING:
    from .core import MemOS
    from .palace import PalaceIndex


class PalaceRecall:
    """Scoped recall that filters results to a wing/room scope."""

    def __init__(self, palace: "PalaceIndex") -> None:
        self._palace = palace

    def palace_recall(
        self,
        memos: "MemOS",
        query: str,
        wing_name: Optional[str] = None,
        room_name: Optional[str] = None,
        top: int = 10,
    ) -> List[RecallResult]:
        """Recall memories scoped to *wing_name* / *room_name*."""
        scoped_ids: Optional[set[str]] = None

        if wing_name is not None:
            try:
                ids = self._palace.list_memories(wing_name=wing_name, room_name=room_name)
                scoped_ids = set(ids)
            except KeyError:
                scoped_ids = None

        fetch_top = top * 5 if scoped_ids is not None else top
        all_results = memos.recall(query=query, top=fetch_top)

        if scoped_ids is not None and scoped_ids:
            filtered = [result for result in all_results if result.item.id in scoped_ids]
            if filtered:
                return filtered[:top]

        if fetch_top != top:
            return memos.recall(query=query, top=top)
        return all_results[:top]


__all__ = ["PalaceRecall"]
