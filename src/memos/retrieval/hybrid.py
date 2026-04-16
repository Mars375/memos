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
from typing import Any

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
        self._avgdl = sum(len(d) for d in self._tokenized) / self._N if self._N else 1.0
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
            norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl))
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
        keyword_boost: Multiplicative boost applied when query keywords
                       overlap with document content (default 1.5).
    """

    VALID_MODES = ("semantic", "keyword", "hybrid")

    def __init__(self, alpha: float = 0.7, keyword_boost: float = 1.5) -> None:
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be between 0.0 and 1.0, got {alpha!r}")
        if keyword_boost < 0.0:
            raise ValueError(f"keyword_boost must be non-negative, got {keyword_boost!r}")
        self.alpha = alpha
        self.keyword_boost = keyword_boost

    @staticmethod
    def _keyword_overlap(query: str, content: str) -> float:
        """Return the fraction of query tokens that appear in content tokens.

        Returns a value in [0.0, 1.0] where 1.0 means every query word
        appears in the content.
        """
        q_tokens = set(_tokenize(query))
        if not q_tokens:
            return 0.0
        c_tokens = set(_tokenize(content))
        return len(q_tokens & c_tokens) / len(q_tokens)

    def rerank(self, query: str, candidates: list[Any]) -> list[Any]:
        """Re-rank *candidates* (list of RecallResult) using hybrid scoring.

        The input semantic scores are blended with BM25 scores computed over
        the candidate corpus.  An additional keyword-overlap boost is applied
        so documents that share more words with the query are promoted.

        Returns the list sorted by descending hybrid score.
        """
        if not candidates:
            return candidates

        contents = [r.item.content for r in candidates]
        bm25 = BM25(contents)
        raw_bm25 = bm25.scores(query)

        semantic_scores = [r.score for r in candidates]
        norm_semantic = _normalize(semantic_scores)
        norm_bm25 = _normalize(raw_bm25)

        blended = [self.alpha * s + (1 - self.alpha) * b for s, b in zip(norm_semantic, norm_bm25)]

        # Apply keyword-overlap boost
        if self.keyword_boost != 1.0:
            boosted = []
            for score, cand in zip(blended, candidates):
                overlap = self._keyword_overlap(query, cand.item.content)
                # Scale the boost factor by the overlap fraction so partial
                # matches get a partial boost.
                factor = 1.0 + (self.keyword_boost - 1.0) * overlap
                boosted.append(score * factor)
            blended = boosted

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

    def llm_rerank(
        self,
        query: str,
        candidates: list[Any],
        top_k: int = 5,
        llm_client: Any = None,
    ) -> list[Any]:
        """Re-rank candidates using an LLM for relevance judgments.

        Takes the top candidates from semantic + BM25 search and asks an LLM
        to order them by relevance to *query*.

        Args:
            query: The user's search query.
            candidates: Ranked candidate list (each must have ``.item.content``
                        and ``.score``).
            top_k: Number of results to return after re-ranking.
            llm_client: An object with a ``.chat(prompt: str) -> str`` method.
                        If *None*, candidates are returned as-is (capped to
                        *top_k*).

        Returns:
            Re-ordered list of at most *top_k* candidates.
        """
        if not candidates:
            return candidates

        # No LLM client → pass through (still cap to top_k)
        if llm_client is None:
            return candidates[:top_k]

        # Build candidate summaries for the ranking prompt
        summaries: list[str] = []
        for idx, cand in enumerate(candidates):
            content = cand.item.content if hasattr(cand, "item") else str(cand)
            # Truncate long content to keep the prompt manageable
            snippet = content[:300] + ("..." if len(content) > 300 else "")
            summaries.append(f"[{idx}] {snippet}")

        prompt = (
            "You are a relevance ranking assistant.  Given the following query "
            "and candidate documents, return a ranked list of document indices "
            "(most relevant first) as a JSON array of integers.\n\n"
            f"Query: {query}\n\n"
            "Candidates:\n" + "\n".join(summaries) + "\n\nReturn ONLY a JSON array of integers, e.g. [2, 0, 3, 1]."
        )

        try:
            raw_response: str = llm_client.chat(prompt)
        except Exception:
            # If the LLM call fails, return original order capped to top_k
            return candidates[:top_k]

        # Parse the LLM response to extract the ordering
        ordering = self._parse_llm_ordering(raw_response, len(candidates))

        if not ordering:
            # Fallback: return original order
            return candidates[:top_k]

        # Reorder candidates according to LLM ranking
        reordered = [candidates[i] for i in ordering if 0 <= i < len(candidates)]

        # Append any candidates the LLM didn't mention
        seen = set(ordering)
        for idx, cand in enumerate(candidates):
            if idx not in seen:
                reordered.append(cand)

        return reordered[:top_k]

    @staticmethod
    def _parse_llm_ordering(response: str, max_idx: int) -> list[int]:
        """Parse the LLM response to extract an ordered list of integer indices.

        Tries several strategies:
        1. Find a JSON array in the response (e.g. ``[2, 0, 3, 1]``)
        2. Find all integers in the response text
        """
        import json as _json

        # Strategy 1: look for a JSON array
        # Try to find bracket-enclosed content
        text = response.strip()
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = _json.loads(text[start : end + 1])
                if isinstance(parsed, list):
                    indices = [int(x) for x in parsed if isinstance(x, (int, float))]
                    if indices and all(0 <= i < max_idx for i in indices):
                        return indices
            except (ValueError, TypeError):
                pass

        # Strategy 2: find all integers in the text
        import re as _re

        numbers = [int(m.group(0)) for m in _re.finditer(r"\d+", text)]
        valid = [n for n in numbers if 0 <= n < max_idx]
        # Deduplicate while preserving order
        seen: set[int] = set()
        unique: list[int] = []
        for n in valid:
            if n not in seen:
                seen.add(n)
                unique.append(n)
        return unique
