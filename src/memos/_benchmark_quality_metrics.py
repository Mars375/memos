"""Metric helpers for recall quality benchmarks."""

from __future__ import annotations

import math

from ._benchmark_quality_models import QualityQueryResult


def _is_relevant(query_result: QualityQueryResult, content: str) -> bool:
    """Check if a returned memory is relevant to the query."""
    content_lower = content.lower()
    keyword_hits = sum(1 for keyword in query_result.expected_keywords if keyword.lower() in content_lower)
    return keyword_hits >= 1


def _is_relevant_for(query_spec, content: str) -> bool:
    """Check if content is relevant to a query specification."""
    content_lower = content.lower()
    keywords = getattr(query_spec, "expected_keywords", None) or (
        query_spec.get("expected_keywords", []) if isinstance(query_spec, dict) else []
    )
    hits = sum(1 for keyword in keywords if keyword.lower() in content_lower)
    return hits >= 1


def _ndcg_at_k(relevances: list[bool], k: int) -> float:
    """Compute NDCG@K."""

    def dcg(relevance_scores: list[float]) -> float:
        return sum(relevance / math.log2(index + 2) for index, relevance in enumerate(relevance_scores))

    actual = [1.0 if relevant else 0.0 for relevant in relevances[:k]]
    ideal = sorted(actual, reverse=True)
    if not ideal or sum(ideal) == 0:
        return 0.0
    return dcg(actual) / dcg(ideal)


def _percentile(sorted_data: list[float], p: float) -> float:
    """Calculate percentile from sorted data."""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (p / 100.0)
    floor_index = int(k)
    ceiling_index = floor_index + 1
    if ceiling_index >= len(sorted_data):
        return sorted_data[floor_index]
    lower = sorted_data[floor_index] * (ceiling_index - k)
    upper = sorted_data[ceiling_index] * (k - floor_index)
    return lower + upper


__all__ = ["_is_relevant", "_is_relevant_for", "_ndcg_at_k", "_percentile"]
