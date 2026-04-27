"""Runner for recall quality benchmarks."""

from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone
from typing import Any, Optional

from . import __version__
from ._benchmark_quality_data import generate_dataset
from ._benchmark_quality_metrics import _is_relevant_for, _ndcg_at_k, _percentile
from ._benchmark_quality_models import QualityQueryResult, QualityReport
from .core import MemOS
from .models import RecallResult


def run_quality_benchmark(
    memos: Optional[MemOS] = None,
    memories_per_category: int = 10,
    extra_noise: int = 50,
    top_k: int = 5,
    seed: int = 42,
    run_decay: bool = True,
    run_scalability: bool = False,
    scalability_sizes: Optional[list[int]] = None,
    backend: str = "memory",
) -> QualityReport:
    """Run a full recall quality benchmark."""
    started = datetime.now(timezone.utc).isoformat()

    if memos is None:
        memos = MemOS(backend=backend, sanitize=True)

    dataset_memories, queries = generate_dataset(
        memories_per_category=memories_per_category,
        extra_noise=extra_noise,
        seed=seed,
    )

    for memory in dataset_memories:
        memos.learn(
            memory["content"],
            tags=memory["tags"],
            importance=memory["importance"],
        )

    total_memories = memos.stats().total_memories
    query_results = _run_recall_queries(memos, queries, top_k)
    n = len(query_results)

    recall_at_k = sum(1 for result in query_results if result.hit) / n if n > 0 else 0.0
    mrr = _mean_reciprocal_rank(query_results)
    precision_at_k = sum(result.precision_at_k for result in query_results) / n if n > 0 else 0.0
    ndcg_at_k = _mean_ndcg(query_results, top_k)
    zero_result_rate = sum(1 for result in query_results if len(result.returned_ids) == 0) / n if n > 0 else 0.0

    latencies = sorted(result.latency_ms for result in query_results)
    avg_latency = statistics.mean(latencies) if latencies else 0.0
    p50_latency = _percentile(latencies, 50)
    p95_latency = _percentile(latencies, 95)

    decay_impact = None
    if run_decay:
        decay_impact = _run_decay_benchmark(memos, dataset_memories, queries, top_k, seed)

    scalability_results = None
    if run_scalability and scalability_sizes:
        scalability_results = _run_scalability_benchmark(
            scalability_sizes,
            queries,
            top_k,
            seed,
            backend,
        )

    finished = datetime.now(timezone.utc).isoformat()

    return QualityReport(
        version=__version__,
        backend=backend,
        total_memories=total_memories,
        total_queries=n,
        top_k=top_k,
        recall_at_k=recall_at_k,
        mrr=mrr,
        precision_at_k=precision_at_k,
        ndcg_at_k=ndcg_at_k,
        zero_result_rate=zero_result_rate,
        avg_latency_ms=avg_latency,
        p50_latency_ms=p50_latency,
        p95_latency_ms=p95_latency,
        decay_impact_score=decay_impact,
        scalability_results=scalability_results,
        query_results=query_results,
        started_at=started,
        finished_at=finished,
        total_seconds=0.0,
    )


def _run_recall_queries(memos: MemOS, queries: list[dict[str, Any]], top_k: int) -> list[QualityQueryResult]:
    query_results: list[QualityQueryResult] = []
    for query in queries:
        start = time.perf_counter()
        results: list[RecallResult] = memos.recall(query["query"], top=top_k)
        latency = (time.perf_counter() - start) * 1000

        returned_ids = [result.item.id for result in results]
        returned_contents = [result.item.content for result in results]
        scores = [result.score for result in results]

        relevances = [_is_relevant_for(query, content) for content in returned_contents]
        hit = any(relevances)
        hit_rank = None
        for index, relevant in enumerate(relevances):
            if relevant:
                hit_rank = index + 1
                break

        relevant_count = sum(relevances)
        precision = relevant_count / top_k if top_k > 0 else 0.0

        query_results.append(
            QualityQueryResult(
                query=query["query"],
                expected_category=query["category"],
                expected_keywords=query["expected_keywords"],
                returned_ids=returned_ids,
                returned_contents=returned_contents,
                scores=scores,
                hit=hit,
                hit_rank=hit_rank,
                precision_at_k=precision,
                latency_ms=latency,
            )
        )
    return query_results


def _mean_reciprocal_rank(query_results: list[QualityQueryResult]) -> float:
    if not query_results:
        return 0.0
    reciprocal_sum = 0.0
    for result in query_results:
        if result.hit_rank is not None:
            reciprocal_sum += 1.0 / result.hit_rank
    return reciprocal_sum / len(query_results)


def _mean_ndcg(query_results: list[QualityQueryResult], top_k: int) -> float:
    ndcg_scores = []
    for result in query_results:
        relevances = [_is_relevant_for(result, content) for content in result.returned_contents]
        ndcg_scores.append(_ndcg_at_k(relevances, top_k))
    return statistics.mean(ndcg_scores) if ndcg_scores else 0.0


def _run_decay_benchmark(
    memos: MemOS,
    dataset_memories: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    top_k: int,
    seed: int,
) -> float:
    """Measure how decay affects recall ranking."""
    sample_queries = queries[:5]

    before_scores: list[float] = []
    for query in sample_queries:
        results = memos.recall(query["query"], top=top_k)
        before_scores.append(max((result.score for result in results), default=0.0))

    try:
        all_items = memos._store.list_all(namespace=memos._namespace)
        memos._decay.run_decay(
            items=all_items,
            min_age_days=0,
            floor=0.01,
            dry_run=False,
        )
        for item in all_items:
            memos._store.upsert(item, namespace=memos._namespace)
    except Exception:
        try:
            all_items = memos._store.list_all(namespace=memos._namespace)
            for item in all_items:
                item.importance = max(0.01, item.importance * 0.5)
                memos._store.upsert(item, namespace=memos._namespace)
        except Exception:
            return -1.0

    after_scores: list[float] = []
    for query in sample_queries:
        results = memos.recall(query["query"], top=top_k)
        after_scores.append(max((result.score for result in results), default=0.0))

    deltas = [before - after for before, after in zip(before_scores, after_scores)]
    return statistics.mean(deltas) if deltas else 0.0


def _run_scalability_benchmark(
    sizes: list[int],
    queries: list[dict[str, Any]],
    top_k: int,
    seed: int,
    backend: str,
) -> list[dict[str, Any]]:
    """Measure recall quality at different dataset sizes."""
    results = []
    for size in sizes:
        memos = MemOS(backend=backend, sanitize=True)
        noise_ratio = 0.3
        signal_count = max(10, int(size * (1 - noise_ratio)))
        noise_count = size - signal_count

        dataset, _ = generate_dataset(
            memories_per_category=max(1, signal_count // 5),
            extra_noise=noise_count,
            seed=seed,
        )

        for memory in dataset[:size]:
            memos.learn(memory["content"], tags=memory["tags"], importance=memory["importance"])

        hits = 0
        latencies = []
        sample = queries[:10]
        for query in sample:
            start = time.perf_counter()
            recall_results = memos.recall(query["query"], top=top_k)
            latencies.append((time.perf_counter() - start) * 1000)
            if recall_results:
                contents = [result.item.content for result in recall_results]
                if any(_is_relevant_for(query, content) for content in contents):
                    hits += 1

        results.append(
            {
                "memories": size,
                "recall_at_k": hits / len(sample) if sample else 0.0,
                "avg_latency_ms": statistics.mean(latencies) if latencies else 0.0,
            }
        )

    return results


__all__ = ["run_quality_benchmark", "_run_decay_benchmark", "_run_scalability_benchmark"]
