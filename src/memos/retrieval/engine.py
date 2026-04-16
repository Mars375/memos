"""Hybrid retrieval engine — embedding + keyword search."""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

from .._constants import (
    DEFAULT_EMBED_TIMEOUT,
    DEFAULT_SEMANTIC_WEIGHT,
    EMBED_CACHE_EVICT_COUNT,
    EMBED_CACHE_MAX,
    IMPORTANCE_BOOST_WEIGHT,
    RECENCY_BONUS_WEIGHT,
    RECENCY_FADE_DAYS,
    SECONDS_PER_DAY,
    TAG_BONUS_MAX,
    TAG_BONUS_PER_TAG,
)
from ..models import MemoryItem, RecallResult, ScoreBreakdown
from ..storage.base import StorageBackend

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..cache.embedding_cache import EmbeddingCache


@runtime_checkable
class Embedder(Protocol):
    """Protocol for pluggable embedding providers."""

    def encode(self, text: str) -> Optional[list[float]]: ...

    @property
    def model_name(self) -> str: ...


def _bm25_score(query: str, content: str) -> float:
    """Simple BM25-like keyword scoring."""
    query_tokens = set(re.findall(r"\w+", query.lower()))
    content_tokens = set(re.findall(r"\w+", content.lower()))
    if not query_tokens:
        return 0.0
    overlap = query_tokens & content_tokens
    # Simplified BM25: overlap ratio with length normalization
    if not content_tokens:
        return 0.0
    tf = len(overlap) / max(len(content_tokens), 1)
    idf = math.log(1 + 1 / max(len(query_tokens) - len(overlap) + 1, 1))
    return tf * idf


class RetrievalEngine:
    """Hybrid retrieval combining semantic and keyword search.

    Supports two modes:
    - **Default**: In-memory hybrid search using Ollama embeddings + BM25.
    - **Qdrant-native**: If the store is a QdrantBackend, delegates hybrid
      scoring to Qdrant's native vector search + local BM25 re-ranking.
    """

    def __init__(
        self,
        store: StorageBackend,
        embed_host: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
        semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
        embedder: Optional[Embedder] = None,
        embed_timeout: float = DEFAULT_EMBED_TIMEOUT,
    ) -> None:
        self._store = store
        self._embed_host = embed_host
        self._embed_model = embed_model
        self._semantic_weight = semantic_weight
        self._keyword_weight = 1.0 - semantic_weight
        # Pluggable local embedder (sentence-transformers, ONNX, etc.)
        # When set, _get_embedding() tries this before Ollama.
        self._embedder = embedder
        self._embed_timeout = embed_timeout
        # Local embedding cache for small stores
        self._embed_cache: dict[str, list[float]] = {}
        # Optional persistent cache (set via set_cache)
        self._persistent_cache: "EmbeddingCache | None" = None

    def set_cache(self, cache: "EmbeddingCache") -> None:
        """Wire a persistent embedding cache for cross-session reuse."""
        self._persistent_cache = cache

    # ------------------------------------------------------------------
    # Temporal proximity boost
    # ------------------------------------------------------------------

    @staticmethod
    def _temporal_boost(created_at: float) -> float:
        """Return a recency boost based on how recently a memory was created.

        Tiers:
            < 1 day  → 0.2
            < 7 days → 0.1
            < 30 days → 0.05
            older    → 0.0
        """
        import time as _time

        age_days = (_time.time() - created_at) / SECONDS_PER_DAY
        if age_days < 1.0:
            return 0.2
        if age_days < 7.0:
            return 0.1
        if age_days < 30.0:
            return 0.05
        return 0.0

    def index(self, item: MemoryItem) -> None:
        """Index a memory item for retrieval."""
        # Pre-compute embedding for semantic search
        self._get_embedding(item.content)

    def search(
        self,
        query: str,
        top: int = 5,
        filter_tags: Optional[list[str]] = None,
        *,
        namespace: str = "",
    ) -> list[RecallResult]:
        """Search memories using hybrid semantic + keyword scoring.

        When the underlying store is QdrantBackend, delegates to native
        hybrid_search() for optimal vector + BM25 scoring. Otherwise falls
        back to the in-memory hybrid approach.
        """
        # Fast path: delegate to Qdrant native hybrid search
        from ..storage.qdrant_backend import QdrantBackend

        if isinstance(self._store, QdrantBackend):
            return self._qdrant_hybrid_search(
                query,
                top,
                filter_tags,
                namespace=namespace,
            )

        # Standard in-memory hybrid search
        all_items = self._store.list_all(namespace=namespace)

        # Filter by tags if specified
        if filter_tags:
            tag_set = set(t.lower() for t in filter_tags)
            all_items = [item for item in all_items if tag_set & set(t.lower() for t in item.tags)]

        if not all_items:
            return []

        # Try semantic search
        query_embedding = self._get_embedding(query)
        has_semantic = query_embedding is not None

        results = []
        for item in all_items:
            # Keyword score
            kw_score = _bm25_score(query, item.content)

            # Tag bonus
            tag_bonus = 0.0
            if filter_tags:
                tag_overlap = len(set(t.lower() for t in item.tags) & set(t.lower() for t in filter_tags))
                tag_bonus = min(tag_overlap * TAG_BONUS_PER_TAG, TAG_BONUS_MAX)

            # Semantic score
            sem_score = 0.0
            match_reason = "keyword"
            if has_semantic:
                item_embedding = self._get_embedding(item.content)
                if item_embedding:
                    sem_score = self._cosine_sim(query_embedding, item_embedding)
                    if sem_score > kw_score:
                        match_reason = "semantic"

            # Importance boost
            importance_boost = item.importance * IMPORTANCE_BOOST_WEIGHT

            # Recency bonus (fades over 30 days)
            import time

            age_days = (time.time() - item.created_at) / SECONDS_PER_DAY
            recency_bonus = max(0, RECENCY_BONUS_WEIGHT * (1 - age_days / RECENCY_FADE_DAYS))

            # Temporal proximity boost (tiered: 0.2 / 0.1 / 0.05)
            temporal_boost = self._temporal_boost(item.created_at)

            # Final score
            final_score = (
                self._semantic_weight * sem_score
                + self._keyword_weight * kw_score
                + tag_bonus
                + importance_boost
                + recency_bonus
                + temporal_boost
            )

            if final_score > 0:
                breakdown = ScoreBreakdown(
                    semantic=round(self._semantic_weight * sem_score, 4),
                    keyword=round(self._keyword_weight * kw_score, 4),
                    importance=round(importance_boost, 4),
                    recency=round(recency_bonus, 4),
                    tag_bonus=round(tag_bonus, 4),
                    total=round(min(final_score, 1.0), 4),
                    backend="hybrid" if has_semantic else "keyword-only",
                )
                results.append(
                    RecallResult(
                        item=item,
                        score=min(final_score, 1.0),
                        match_reason=match_reason,
                        score_breakdown=breakdown,
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top]

    def _qdrant_hybrid_search(
        self,
        query: str,
        top: int,
        filter_tags: Optional[list[str]],
        *,
        namespace: str = "",
    ) -> list[RecallResult]:
        """Delegate hybrid search to QdrantBackend.hybrid_search()."""
        from ..storage.qdrant_backend import QdrantBackend

        assert isinstance(self._store, QdrantBackend)

        pairs = self._store.hybrid_search(
            query,
            limit=top * 2,  # Overfetch for tag filtering
            namespace=namespace,
            vector_weight=self._semantic_weight,
            keyword_weight=self._keyword_weight,
        )

        results = []
        for item, score in pairs:
            # Apply tag filter
            if filter_tags:
                tag_set = set(t.lower() for t in filter_tags)
                if not (tag_set & set(t.lower() for t in item.tags)):
                    continue

            # Importance boost
            importance_boost = item.importance * IMPORTANCE_BOOST_WEIGHT

            # Recency bonus (fades over 30 days)
            import time as _time

            age_days = (_time.time() - item.created_at) / SECONDS_PER_DAY
            recency_bonus = max(0, RECENCY_BONUS_WEIGHT * (1 - age_days / RECENCY_FADE_DAYS))

            # Temporal proximity boost (tiered: 0.2 / 0.1 / 0.05)
            temporal_boost = self._temporal_boost(item.created_at)

            final_score = min(score + importance_boost + recency_bonus + temporal_boost, 1.0)

            match_reason = "semantic" if score > 0.5 else "keyword"
            breakdown = ScoreBreakdown(
                semantic=round(score * self._semantic_weight, 4) if score > 0.5 else 0.0,
                keyword=round(score * self._keyword_weight, 4) if score <= 0.5 else 0.0,
                importance=round(importance_boost, 4),
                recency=round(recency_bonus, 4),
                tag_bonus=0.0,
                total=round(final_score, 4),
                backend="qdrant",
            )
            results.append(
                RecallResult(
                    item=item,
                    score=final_score,
                    match_reason=match_reason,
                    score_breakdown=breakdown,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top]

    def _get_embedding(self, text: str) -> Optional[list[float]]:
        """Get embedding — pluggable embedder first, then Ollama, with caching."""
        # L1: in-memory cache (fastest)
        if text in self._embed_cache:
            return self._embed_cache[text]

        # L2: persistent disk cache
        cache_key = self._embed_model
        if self._embedder is not None:
            cache_key = getattr(self._embedder, "model_name", self._embed_model)
        if self._persistent_cache is not None:
            cached = self._persistent_cache.get(text, model=cache_key)
            if cached is not None:
                self._embed_cache[text] = cached  # Promote to L1
                return cached

        vec: Optional[list[float]] = None

        # Try pluggable local embedder first (sentence-transformers, ONNX, etc.)
        if self._embedder is not None:
            try:
                vec = self._embedder.encode(text)
            except Exception:
                logger.warning("Local embedder failed", exc_info=True)
                pass  # Fall through to Ollama

        # Fallback: Ollama API
        if vec is None:
            try:
                import httpx

                resp = httpx.post(
                    f"{self._embed_host}/api/embed",
                    json={"model": self._embed_model, "input": text},
                    timeout=self._embed_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                # Ollama returns {"embeddings": [[...]]}
                embeddings = data.get("embeddings", [])
                if embeddings:
                    vec = embeddings[0]
            except Exception:
                logger.warning("Ollama embedding failed", exc_info=True)
                pass  # Graceful fallback to keyword-only

        # Cache result if obtained
        if vec is not None:
            self._embed_cache[text] = vec
            if self._persistent_cache is not None:
                self._persistent_cache.put(text, vec, model=cache_key)
            # Limit L1 cache size
            if len(self._embed_cache) > EMBED_CACHE_MAX:
                keys = list(self._embed_cache.keys())[:EMBED_CACHE_EVICT_COUNT]
                for k in keys:
                    del self._embed_cache[k]

        return vec

    @staticmethod
    def _bm25(query: str, content: str) -> float:
        return _bm25_score(query, content)

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
