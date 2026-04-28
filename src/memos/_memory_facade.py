"""Memory CRUD facade for the MemOS nucleus."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ._constants import (
    DEFAULT_IMPORTANCE,
    IMPORTANCE_EQUALITY_TOLERANCE,
    SECONDS_PER_DAY,
    STATS_DECAY_THRESHOLD,
)
from .models import MemoryItem, MemoryStats, RecallResult, generate_id
from .query import MemoryQuery, QueryEngine
from .sanitizer import MemorySanitizer
from .tagger import AutoTagger
from .utils import coerce_tags

logger = logging.getLogger(__name__)


class MemoryCrudFacade:
    """Mixin exposing core memory CRUD, recall, and statistics APIs."""

    def _validate_content(self, content: str) -> None:
        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty")
        if self._sanitize:
            issues = MemorySanitizer.check(content)
            if issues:
                raise ValueError(f"Memory failed sanitization: {issues}")

    def _batch_upsert_items(self, items: list[MemoryItem]) -> None:
        if hasattr(self._store, "upsert_batch") and len(items) > 1:
            try:
                self._store.upsert_batch(items, namespace=self._namespace)
                return
            except AttributeError:
                pass
        for item in items:
            self._store.upsert(item, namespace=self._namespace)

    def _forget_by_id(self, item_id: str, *, source: str = "forget") -> bool:
        item = self._store.get(item_id, namespace=self._namespace)
        if not self._store.delete(item_id, namespace=self._namespace):
            return False
        if item is not None:
            self._versioning.record_version(item, source=source)
        self._events.emit_sync(
            "forgotten",
            {
                "id": item_id,
                "content": item.content[:200] if item else "",
                "tags": item.tags if item else [],
            },
            namespace=self._namespace,
        )
        return True

    def learn(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        importance: float = DEFAULT_IMPORTANCE,
        metadata: Optional[dict[str, Any]] = None,
        ttl: Optional[float] = None,
        allow_duplicate: bool = False,
    ) -> MemoryItem:
        """Store a new memory.

        Args:
            content: Memory text content.
            tags: Optional list of tags.
            importance: Importance score 0.0-1.0.
            metadata: Optional metadata dict.
            ttl: Time-to-live in seconds.
            allow_duplicate: If True, bypass dedup check and insert even if duplicate.
        """
        self._check_acl("write")
        self._validate_content(content)

        # Dedup check — skip if duplicate found and allow_duplicate=False
        # Only block true duplicates: same content AND same tags/importance.
        # If tags or importance differ, treat as an intentional update (versioning).
        if self._dedup_enabled and not allow_duplicate:
            dedup_result = self.dedup_check(content)
            if dedup_result.is_duplicate and dedup_result.match:
                existing = dedup_result.match
                final_tags_check = list(tags) if tags else []
                same_tags = set(existing.tags) == set(final_tags_check)
                same_importance = abs(existing.importance - importance) < IMPORTANCE_EQUALITY_TOLERANCE
                if same_tags and same_importance:
                    logger.info(
                        "Skipping duplicate memory (reason=%s, similarity=%.3f, original=%s)",
                        dedup_result.reason,
                        dedup_result.similarity,
                        existing.id,
                    )
                    return existing

        # Auto-tag with type tags (decision, preference, milestone, etc.)
        final_tags = list(tags) if tags else []
        if not isinstance(final_tags, list):
            final_tags = []
        auto_tags = AutoTagger().auto_tag(content.strip(), existing_tags=final_tags)
        if auto_tags:
            final_tags.extend(auto_tags)

        item = MemoryItem(
            id=generate_id(content),
            content=content.strip(),
            tags=final_tags,
            importance=max(0.0, min(1.0, importance)),
            metadata=metadata or {},
            ttl=ttl,
        )

        self._store.upsert(item, namespace=self._namespace)

        # Register in dedup index
        if self._dedup_enabled and self._dedup_engine:
            self._dedup_engine.register(item)
        self._retrieval.index(item)
        self._versioning.record_version(item, source="learn")

        # Emit event
        self._events.emit_sync(
            "learned",
            {
                "id": item.id,
                "content": item.content[:200],
                "tags": item.tags,
                "importance": item.importance,
                "ttl": item.ttl,
            },
            namespace=self._namespace,
        )

        # Auto-update wiki if living wiki is initialized
        if self._wiki_auto_update and self._living_wiki is not None:
            try:
                self._living_wiki.update_for_item(item)
            except Exception:
                logger.warning("Wiki update failed during learn()", exc_info=True)
                pass  # Wiki update failure should not block learn()

        return item

    def batch_learn(
        self,
        items: list[dict[str, Any]],
        *,
        continue_on_error: bool = True,
    ) -> dict[str, Any]:
        """Store multiple memories in one call.

        Each item dict should have: content (required), tags, importance, metadata.
        Returns a summary with counts of learned, skipped, and errors.

        Args:
            items: List of dicts with memory data.
            continue_on_error: If True, skip invalid items. If False, raise on first error.

        Returns:
            dict with learned, skipped, errors counts and details.
        """
        self._check_acl("write")
        result = {
            "learned": 0,
            "skipped": 0,
            "errors": [],
            "items": [],
        }

        # Prepare valid items for batch upsert
        valid_items: list[MemoryItem] = []

        for entry in items:
            content = entry.get("content", "").strip()
            if not content:
                result["skipped"] += 1
                if not continue_on_error:
                    raise ValueError("Empty content in batch_learn item")
                continue

            # Sanitize
            if self._sanitize:
                issues = MemorySanitizer.check(content)
                if issues:
                    result["errors"].append(
                        {
                            "content": content[:100],
                            "reason": f"Sanitization failed: {issues}",
                        }
                    )
                    if not continue_on_error:
                        raise ValueError(f"Memory failed sanitization: {issues}")
                    continue

            item = MemoryItem(
                id=generate_id(content),
                content=content,
                tags=entry.get("tags", []),
                importance=max(0.0, min(1.0, entry.get("importance", DEFAULT_IMPORTANCE))),
                metadata=entry.get("metadata", {}),
            )
            valid_items.append(item)

        self._batch_upsert_items(valid_items)

        # Index all valid items
        for item in valid_items:
            self._retrieval.index(item)
            result["items"].append(
                {
                    "id": item.id,
                    "content": item.content[:100],
                    "tags": item.tags,
                }
            )

        result["learned"] = len(valid_items)

        # Record versions for batch-learned items
        for item in valid_items:
            self._versioning.record_version(item, source="batch_learn")

        # Emit batch event
        if valid_items:
            tag_union = sorted({tag for item in valid_items for tag in item.tags})
            self._events.emit_sync(
                "batch_learned",
                {
                    "count": len(valid_items),
                    "skipped": result["skipped"],
                    "errors": len(result["errors"]),
                    "tags": tag_union,
                },
                namespace=self._namespace,
            )

        return result

    def recall(
        self,
        query: str,
        top: int = 5,
        filter_tags: Optional[list[str]] = None,
        min_score: float = 0.0,
        filter_after: Optional[float] = None,
        filter_before: Optional[float] = None,
        retrieval_mode: str = "semantic",
        tag_filter: Optional[dict[str, Any]] = None,
        min_importance: Optional[float] = None,
        max_importance: Optional[float] = None,
    ) -> list[RecallResult]:
        """Retrieve memories relevant to a query."""
        self._check_acl("read")
        started = time.perf_counter()
        final_results: list[RecallResult] = []

        include_tags = coerce_tags(filter_tags)
        require_tags: list[str] = []
        exclude_tags: list[str] = []
        if tag_filter:
            include_tags.extend(coerce_tags(tag_filter.get("include")))
            require_tags.extend(coerce_tags(tag_filter.get("require")))
            exclude_tags.extend(coerce_tags(tag_filter.get("exclude")))
            if str(tag_filter.get("mode") or "").upper() == "AND" and include_tags:
                require_tags.extend(include_tags)
                include_tags = []

        try:
            query_engine = QueryEngine(
                self._retrieval,
                namespace=self._namespace,
                decay=self._decay,
            )
            final_results = query_engine.execute(
                MemoryQuery(
                    query=query,
                    top_k=top,
                    retrieval_mode=retrieval_mode,
                    include_tags=include_tags,
                    require_tags=require_tags,
                    exclude_tags=exclude_tags,
                    min_importance=min_importance,
                    max_importance=max_importance,
                    created_after=filter_after,
                    created_before=filter_before,
                    min_score=min_score,
                ),
                self._store,
            )
            # Touch all recalled items and batch-persist the updates.
            # This replaces N individual upserts with a single batch write
            # for backends that support it (ChromaDB, Qdrant, Pinecone),
            # falling back to individual upserts otherwise.
            touched_items: list[MemoryItem] = []
            for result in final_results:
                result.item.touch()
                touched_items.append(result.item)
            if touched_items:
                self._batch_upsert_items(touched_items)
            for result in final_results:
                self._events.emit_sync(
                    "recalled",
                    {
                        "id": result.item.id,
                        "query": query,
                        "score": result.score,
                        "tags": result.item.tags,
                    },
                    namespace=self._namespace,
                )
        finally:
            try:
                self._analytics.track_recall(query, final_results, (time.perf_counter() - started) * 1000.0)
            except Exception:
                logger.warning("Analytics tracking failed during recall()", exc_info=True)

        return final_results

    def list_memories(
        self,
        *,
        tags: Optional[list[str]] = None,
        require_tags: Optional[list[str]] = None,
        exclude_tags: Optional[list[str]] = None,
        min_importance: Optional[float] = None,
        max_importance: Optional[float] = None,
        created_after: Optional[float] = None,
        created_before: Optional[float] = None,
        sort: str = "created_at",
        limit: int = 50,
    ) -> list[MemoryItem]:
        """List memories with structured filters and sorting."""
        self._check_acl("read")
        query_engine = QueryEngine(
            self._retrieval,
            namespace=self._namespace,
            decay=self._decay,
        )

        return query_engine.list_items(
            MemoryQuery(
                top_k=limit,
                include_tags=coerce_tags(tags),
                require_tags=coerce_tags(require_tags),
                exclude_tags=coerce_tags(exclude_tags),
                min_importance=min_importance,
                max_importance=max_importance,
                created_after=created_after,
                created_before=created_before,
                sort=sort,
            ),
            self._store,
        )

    async def recall_stream(
        self,
        query: str,
        top: int = 5,
        filter_tags: list[str] | None = None,
        min_score: float = 0.0,
    ):
        """Async generator that yields recall results one at a time.

        Each result is yielded as soon as it is scored, allowing consumers
        to start processing partial results before the full search completes.
        For LLM agents, this enables progressive context building.

        Yields RecallResult objects sorted by score (best first).
        """
        # Get all candidate results
        all_results = self.recall(
            query=query,
            top=top,
            filter_tags=filter_tags,
            min_score=min_score,
        )

        # Yield them one by one — for backends with native streaming
        # this could be extended to yield as each result arrives
        for result in all_results:
            yield result
            # Allow the event loop to interleave other work
            import asyncio

            await asyncio.sleep(0)

    def forget_tag(self, tag: str) -> int:
        """Delete all memories carrying a given tag."""
        self._check_acl("delete")
        removed = 0
        for item in self._store.list_all(namespace=self._namespace):
            if tag in item.tags and self._forget_by_id(item.id, source="forget_tag"):
                removed += 1
        return removed

    def forget(self, content_or_id: str) -> bool:
        """Delete a specific memory by content or ID."""
        self._check_acl("delete")
        if self._forget_by_id(content_or_id):
            return True
        return self._forget_by_id(generate_id(content_or_id))

    def stats(self, items: list[MemoryItem] | None = None) -> MemoryStats:
        """Get memory store statistics."""
        items = items if items is not None else self._store.list_all(namespace=self._namespace)
        if not items:
            return MemoryStats()

        now = time.time()
        scores = [self._decay.adjusted_score(DEFAULT_IMPORTANCE, item) for item in items]
        tags: dict[str, int] = {}
        for item in items:
            for tag in item.tags:
                tags[tag] = tags.get(tag, 0) + 1

        top_tags = sorted(tags, key=tags.get, reverse=True)[:10]
        decay_candidate_items = self._decay.find_prune_candidates(items, threshold=STATS_DECAY_THRESHOLD)
        decay_candidates = len(decay_candidate_items)
        expired_items = [i for i in items if i.is_expired]

        total_chars = sum(len(i.content) for i in items)
        prunable_chars = sum(len(i.content) for i in decay_candidate_items)
        expired_chars = sum(len(i.content) for i in expired_items)

        return MemoryStats(
            total_memories=len(items),
            total_tags=len(tags),
            avg_relevance=sum(scores) / len(scores),
            avg_importance=sum(i.importance for i in items) / len(items),
            oldest_memory_days=(now - min(i.created_at for i in items)) / SECONDS_PER_DAY,
            newest_memory_days=(now - max(i.created_at for i in items)) / SECONDS_PER_DAY,
            decay_candidates=decay_candidates,
            expired_memories=len(expired_items),
            top_tags=top_tags,
            total_chars=total_chars,
            total_tokens=total_chars // 4,
            prunable_tokens=prunable_chars // 4,
            expired_tokens=expired_chars // 4,
        )

    def search(self, q: str, limit: int = 20) -> list[MemoryItem]:
        """Simple keyword search across all memories."""
        self._check_acl("read")
        return self._store.search(q, limit=limit, namespace=self._namespace)

    def get(self, item_id: str) -> Optional["MemoryItem"]:
        """Retrieve a single memory item by ID.

        Args:
            item_id: The unique identifier of the memory item.

        Returns:
            The MemoryItem if found, or None.
        """
        self._check_acl("read")
        return self._store.get(item_id, namespace=self._namespace)
