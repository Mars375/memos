"""Relevance feedback facade for MemOS."""

from __future__ import annotations

from typing import Any

from ._constants import FEEDBACK_IMPORTANCE_DELTA
from .models import FeedbackEntry, FeedbackStats


class FeedbackFacade:
    """Mixin exposing relevance-feedback APIs on MemOS."""

    _store: Any
    _namespace: str
    _events: Any

    def record_feedback(
        self,
        item_id: str,
        feedback: str,
        *,
        query: str = "",
        score_at_recall: float = 0.0,
        agent_id: str = "",
    ) -> FeedbackEntry:
        """Record relevance feedback for a recalled memory item.

        Args:
            item_id: ID of the memory item.
            feedback: "relevant" or "not-relevant".
            query: The query that triggered the recall (optional).
            score_at_recall: Relevance score at recall time (optional).
            agent_id: ID of the agent providing feedback (optional).

        Returns:
            The created FeedbackEntry.

        Raises:
            ValueError: If feedback value is invalid.
        """
        if feedback not in ("relevant", "not-relevant"):
            raise ValueError(f"Invalid feedback: {feedback!r}. Must be 'relevant' or 'not-relevant'")
        entry = FeedbackEntry(
            item_id=item_id,
            feedback=feedback,
            query=query,
            score_at_recall=score_at_recall,
            agent_id=agent_id,
        )

        # Store feedback in the item's metadata for persistence
        item = self._store.get(item_id, namespace=self._namespace)
        if item is not None:
            fb_list = item.metadata.get("_feedback", [])
            fb_list.append(entry.to_dict())
            item.metadata["_feedback"] = fb_list

            # Adjust item importance based on feedback
            delta = FEEDBACK_IMPORTANCE_DELTA if feedback == "relevant" else -FEEDBACK_IMPORTANCE_DELTA
            item.importance = max(0.0, min(1.0, item.importance + delta))
            self._store.upsert(item, namespace=self._namespace)

            self._events.emit_sync(
                "feedback",
                {
                    "item_id": item_id,
                    "feedback": feedback,
                    "importance": item.importance,
                },
                namespace=self._namespace,
            )

        return entry

    def get_feedback(self, item_id: str | None = None, limit: int = 100) -> list[FeedbackEntry]:
        """Get feedback entries, optionally filtered by item_id."""
        entries: list[FeedbackEntry] = []
        if item_id:
            item = self._store.get(item_id, namespace=self._namespace)
            if item and "_feedback" in item.metadata:
                entries = [FeedbackEntry.from_dict(d) for d in item.metadata["_feedback"]]
        else:
            all_items = self._store.list_all(namespace=self._namespace)
            for item in all_items:
                if "_feedback" in item.metadata:
                    entries.extend(FeedbackEntry.from_dict(d) for d in item.metadata["_feedback"])
        entries.sort(key=lambda e: e.created_at)
        return entries[-limit:]

    def feedback_stats(self) -> FeedbackStats:
        """Get aggregate feedback statistics."""
        all_entries = self.get_feedback(limit=1_000_000)
        total = len(all_entries)
        if total == 0:
            return FeedbackStats()
        relevant = sum(1 for e in all_entries if e.feedback == "relevant")
        not_relevant = total - relevant
        items_with = len({e.item_id for e in all_entries})
        avg_score = (relevant - not_relevant) / total
        return FeedbackStats(
            total_feedback=total,
            relevant_count=relevant,
            not_relevant_count=not_relevant,
            items_with_feedback=items_with,
            avg_feedback_score=avg_score,
        )
