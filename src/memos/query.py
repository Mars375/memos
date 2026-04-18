"""Structured query helpers for advanced recall filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .decay.engine import DecayEngine
from .models import MemoryItem, RecallResult
from .retrieval.engine import RetrievalEngine
from .retrieval.hybrid import HybridRetriever
from .storage.base import StorageBackend

_VALID_RETRIEVAL_MODES = {"semantic", "keyword", "hybrid"}
_VALID_SORTS = {"created_at", "importance", "accessed_at"}


@dataclass
class MemoryQuery:
    """Structured memory query for recall and listing endpoints."""

    query: str = ""
    top_k: int = 5
    retrieval_mode: str = "semantic"
    include_tags: list[str] = field(default_factory=list)
    require_tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    min_importance: float | None = None
    max_importance: float | None = None
    created_after: float | None = None
    created_before: float | None = None
    min_score: float = 0.0
    sort: str = "score"


class QueryEngine:
    """Execute structured memory queries against a MemOS store."""

    def __init__(
        self,
        retrieval: RetrievalEngine,
        *,
        namespace: str = "",
        decay: Optional[DecayEngine] = None,
    ) -> None:
        self._retrieval = retrieval
        self._namespace = namespace
        self._decay = decay

    def execute(self, query: MemoryQuery, store: StorageBackend) -> list[RecallResult]:
        """Run a filtered recall query and return ranked recall results."""
        normalized = self._normalize(query)
        text = normalized.query.strip()
        if not text:
            return []

        filtered_items = self._filtered_items(normalized, store)
        if not filtered_items:
            return []

        candidates = [RecallResult(item=item, score=0.0, match_reason="keyword") for item in filtered_items]
        if normalized.retrieval_mode == "keyword":
            return HybridRetriever().keyword_recall(
                text,
                candidates,
                top=normalized.top_k,
                min_score=normalized.min_score,
            )

        all_items = filtered_items
        search_top = max(len(all_items), normalized.top_k, 1)
        engine_results = self._retrieval.search(
            text,
            top=search_top,
            filter_tags=None,
            namespace=self._namespace,
            items=all_items,
        )

        allowed_ids = {item.id for item in filtered_items}
        results = [
            RecallResult(
                item=result.item,
                score=result.score,
                match_reason=result.match_reason,
                score_breakdown=result.score_breakdown,
            )
            for result in engine_results
            if result.item.id in allowed_ids
        ]

        if not results:
            return HybridRetriever().keyword_recall(
                text,
                candidates,
                top=normalized.top_k,
                min_score=normalized.min_score,
            )

        results = self._apply_decay(results, normalized.min_score)
        if normalized.retrieval_mode == "hybrid" and results:
            results = HybridRetriever().rerank(text, results)
            results = self._apply_decay(results, normalized.min_score)

        return sorted(results, key=lambda item: item.score, reverse=True)[: normalized.top_k]

    def list_items(self, query: MemoryQuery, store: StorageBackend) -> list[MemoryItem]:
        """Return all items matching structured filters, sorted as requested."""
        normalized = self._normalize(query)
        items = self._filtered_items(normalized, store)
        if not items:
            return []

        sort_key = normalized.sort if normalized.sort in _VALID_SORTS else "created_at"
        if sort_key == "importance":
            items.sort(key=lambda item: (item.importance, item.created_at), reverse=True)
        elif sort_key == "accessed_at":
            items.sort(key=lambda item: (item.accessed_at, item.created_at), reverse=True)
        else:
            items.sort(key=lambda item: item.created_at, reverse=True)
        return items[: normalized.top_k]

    def _filtered_items(self, query: MemoryQuery, store: StorageBackend) -> list[MemoryItem]:
        return [item for item in store.list_all(namespace=self._namespace) if self._matches(item, query)]

    def _apply_decay(self, results: list[RecallResult], min_score: float) -> list[RecallResult]:
        if self._decay is None:
            return [result for result in results if result.score >= min_score]

        adjusted: list[RecallResult] = []
        for result in results:
            decayed = self._decay.adjusted_score(result.score, result.item)
            if decayed >= min_score:
                result.score = decayed
                adjusted.append(result)
        return adjusted

    def _matches(self, item: MemoryItem, query: MemoryQuery) -> bool:
        if item.is_expired:
            return False
        if query.created_after is not None and item.created_at < query.created_after:
            return False
        if query.created_before is not None and item.created_at > query.created_before:
            return False
        if query.min_importance is not None and item.importance < query.min_importance:
            return False
        if query.max_importance is not None and item.importance > query.max_importance:
            return False

        tag_set = {tag.lower() for tag in item.tags}
        include_tags = {tag.lower() for tag in query.include_tags}
        require_tags = {tag.lower() for tag in query.require_tags}
        exclude_tags = {tag.lower() for tag in query.exclude_tags}

        if include_tags and not (tag_set & include_tags):
            return False
        if require_tags and not require_tags.issubset(tag_set):
            return False
        if exclude_tags and (tag_set & exclude_tags):
            return False
        return True

    @staticmethod
    def _normalize(query: MemoryQuery) -> MemoryQuery:
        retrieval_mode = query.retrieval_mode or "semantic"
        if retrieval_mode not in _VALID_RETRIEVAL_MODES:
            raise ValueError(
                f"retrieval_mode must be one of {tuple(sorted(_VALID_RETRIEVAL_MODES))}, got {retrieval_mode!r}"
            )
        return MemoryQuery(
            query=query.query,
            top_k=max(int(query.top_k or 5), 1),
            retrieval_mode=retrieval_mode,
            include_tags=[tag for tag in query.include_tags if tag],
            require_tags=[tag for tag in query.require_tags if tag],
            exclude_tags=[tag for tag in query.exclude_tags if tag],
            min_importance=query.min_importance,
            max_importance=query.max_importance,
            created_after=query.created_after,
            created_before=query.created_before,
            min_score=float(query.min_score or 0.0),
            sort=query.sort or "score",
        )
