"""Hybrid Retrieval — Semantic + Keyword BM25 (P20).

Pipeline (mempalace-inspired):
    1. Semantic recall top-50 via existing backend
    2. BM25 score on the 50 candidates (in-house implementation, no deps)
    3. Final score = alpha * semantic + (1 - alpha) * bm25  (alpha=0.7)

Usage:
    from memos.retrieval import HybridRetriever
    retriever = HybridRetriever(alpha=0.7)
    reranked = retriever.rerank(query, candidates)   # list[RecallResult]
"""

from __future__ import annotations

import math
import re
from typing import Any, List


# ---------------------------------------------------------------------------
# Tokenizer (shared)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\b[a-z0-9_']{2,}\b")


def _tokenize(text: str) -> list[str]:
    """Lowercase, alphanumeric tokenization."""
    return _TOKEN_RE.findall(text.lower())


# ---------------------------------------------------------------------------
# BM25 (in-house, no external dependency)
# ---------------------------------------------------------------------------

class BM25:
    """BM25 Okapi scorer for a fixed corpus of documents.

    Args:
        corpus: List of raw document strings.
        k1: Term saturation parameter (default 1.5).
        b: Length normalization parameter (default 0.75).
    """

    def __init__(
        self,
        corpus: list[str],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.k1 = k1
        self.b = b
        self._tokenized = [_tokenize(doc) for doc in corpus]
        self._N = len(self._tokenized)
        self._avgdl = (
            sum(len(d) for d in self._tokenized) / self._N if self._N else 1.0
        )
        # Document frequency per term
        self._df: dict[str, int] = {}
        for tokens in self._tokenized:
            for term in set(tokens):
                self._df[term] = self._df.get(term, 0) + 1

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log((self._N - df + 0.5) / (df + 0.5) + 1)

    def score(self, doc_index: int, query_tokens: list[str]) -> float:
        """BM25 score for one document against pre-tokenized query."""
        doc = self._tokenized[doc_index]
        dl = len(doc)
        if dl == 0:
            return 0.0
        tf_map: dict[str, int] = {}
        for t in doc:
            tf_map[t] = tf_map.get(t, 0) + 1

        score = 0.0
        for term in query_tokens:
            if term not in tf_map:
                continue
            tf = tf_map[term]
            idf = self._idf(term)
            norm = tf * (self.k1 + 1) / (
                tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
            )
            score += idf * norm
        return score

    def scores(self, query: str) -> list[float]:
        """Return BM25 scores for all documents against *query*."""
        q_tokens = _tokenize(query)
        return [self.score(i, q_tokens) for i in range(self._N)]


# ---------------------------------------------------------------------------
# Keyword-only scorer (for retrieval_mode="keyword")
# ---------------------------------------------------------------------------

def keyword_score(query: str, content: str) -> float:
    """Simple TF-based keyword score (fraction of query terms present)."""
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return 0.0
    doc_tokens = set(_tokenize(content))
    return len(q_tokens & doc_tokens) / len(q_tokens)


# ---------------------------------------------------------------------------
# HybridRetriever
# ---------------------------------------------------------------------------

def _normalize(scores: list[float]) -> list[float]:
    """Min-max normalize a list of floats to [0, 1]."""
    if not scores:
        return scores
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [0.5] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


class HybridRetriever:
    """Blend semantic recall scores with BM25 keyword re-ranking.

    Args:
        alpha: Weight for semantic score in the blend (0–1, default 0.7).
               Higher alpha = more semantic, lower = more keyword-driven.
    """

    VALID_MODES = ("semantic", "keyword", "hybrid")

    def __init__(self, alpha: float = 0.7) -> None:
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be between 0.0 and 1.0, got {alpha!r}")
        self.alpha = alpha

    def rerank(self, query: str, candidates: list[Any]) -> list[Any]:
        """Re-rank *candidates* (list of RecallResult) using hybrid scoring.

        The input semantic scores are blended with BM25 scores computed over
        the candidate corpus.  Returns the list sorted by descending hybrid score.
        """
        if not candidates:
            return candidates

        contents = [r.item.content for r in candidates]
        bm25 = BM25(contents)
        raw_bm25 = bm25.scores(query)

        semantic_scores = [r.score for r in candidates]
        norm_semantic = _normalize(semantic_scores)
        norm_bm25 = _normalize(raw_bm25)

        blended = [
            self.alpha * s + (1 - self.alpha) * b
            for s, b in zip(norm_semantic, norm_bm25)
        ]

        # Attach blended score and sort
        for r, score in zip(candidates, blended):
            r.score = score

        return sorted(candidates, key=lambda r: r.score, reverse=True)

    def keyword_recall(
        self,
        query: str,
        candidates: list[Any],
        top: int = 5,
        min_score: float = 0.0,
    ) -> list[Any]:
        """Keyword-only recall: score all candidates by TF overlap, return top-K."""
        scored = []
        for r in candidates:
            r.score = keyword_score(query, r.item.content)
            if r.score >= min_score:
                scored.append(r)
        return sorted(scored, key=lambda r: r.score, reverse=True)[:top]
