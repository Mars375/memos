"""Recall quality benchmark suite compatibility facade."""

from __future__ import annotations

from ._benchmark_quality_data import CATEGORIES, QUERY_TEMPLATES, generate_dataset
from ._benchmark_quality_metrics import _is_relevant, _is_relevant_for, _ndcg_at_k, _percentile
from ._benchmark_quality_models import QualityQueryResult, QualityReport
from ._benchmark_quality_runner import run_quality_benchmark

__all__ = [
    "CATEGORIES",
    "QUERY_TEMPLATES",
    "QualityQueryResult",
    "QualityReport",
    "_is_relevant",
    "_is_relevant_for",
    "_ndcg_at_k",
    "_percentile",
    "generate_dataset",
    "run_quality_benchmark",
]
