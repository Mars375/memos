"""Hybrid retrieval engine — embedding + keyword search."""

from __future__ import annotations

import math
import re
from typing import Optional

from ..models import MemoryItem, RecallResult
from ..storage.base import StorageBackend


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
    """Hybrid retrieval combining semantic and keyword search."""

    def __init__(
        self,
        store: StorageBackend,
        embed_host: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
        semantic_weight: float = 0.6,
    ) -> None:
        self._store = store
        self._embed_host = embed_host
        self._embed_model = embed_model
        self._semantic_weight = semantic_weight
        self._keyword_weight = 1.0 - semantic_weight
        # Local embedding cache for small stores
        self._embed_cache: dict[str, list[float]] = {}

    def index(self, item: MemoryItem) -> None:
        """Index a memory item for retrieval."""
        # Pre-compute embedding for semantic search
        self._get_embedding(item.content)

    def search(
        self,
        query: str,
        top: int = 5,
        filter_tags: Optional[list[str]] = None,
    ) -> list[RecallResult]:
        """Search memories using hybrid semantic + keyword scoring.
        
        Falls back to keyword-only if embedding service is unavailable.
        """
        all_items = self._store.list_all()

        # Filter by tags if specified
        if filter_tags:
            tag_set = set(t.lower() for t in filter_tags)
            all_items = [
                item for item in all_items
                if tag_set & set(t.lower() for t in item.tags)
            ]

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
                tag_overlap = len(
                    set(t.lower() for t in item.tags)
                    & set(t.lower() for t in filter_tags)
                )
                tag_bonus = min(tag_overlap * 0.1, 0.3)

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
            importance_boost = item.importance * 0.1

            # Recency bonus (fades over 30 days)
            import time
            age_days = (time.time() - item.created_at) / 86400
            recency_bonus = max(0, 0.1 * (1 - age_days / 30))

            # Final score
            final_score = (
                self._semantic_weight * sem_score
                + self._keyword_weight * kw_score
                + tag_bonus
                + importance_boost
                + recency_bonus
            )

            if final_score > 0:
                results.append(RecallResult(
                    item=item,
                    score=min(final_score, 1.0),
                    match_reason=match_reason,
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top]

    def _get_embedding(self, text: str) -> Optional[list[float]]:
        """Get embedding from Ollama, with caching."""
        if text in self._embed_cache:
            return self._embed_cache[text]

        try:
            import httpx
            resp = httpx.post(
                f"{self._embed_host}/api/embed",
                json={"model": self._embed_model, "input": text},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            # Ollama returns {"embeddings": [[...]]}
            embeddings = data.get("embeddings", [])
            if embeddings:
                vec = embeddings[0]
                self._embed_cache[text] = vec
                # Limit cache size
                if len(self._embed_cache) > 5000:
                    keys = list(self._embed_cache.keys())[:2500]
                    for k in keys:
                        del self._embed_cache[k]
                return vec
        except Exception:
            pass  # Graceful fallback to keyword-only

        return None

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
