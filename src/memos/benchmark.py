"""Performance benchmarking for MemOS.

Measures throughput and latency of core operations (learn, recall, search, prune)
with configurable dataset sizes. Outputs structured results for CI integration.

Usage:
    # CLI
    memos benchmark
    memos benchmark --size 5000 --json

    # Programmatic
    from memos.benchmark import run_benchmark
    results = run_benchmark(memories=1000)
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .core import MemOS


@dataclass
class BenchmarkResult:
    """Result of a single benchmark operation."""

    operation: str
    count: int
    total_seconds: float
    ops_per_second: float
    latency_min_ms: float
    latency_max_ms: float
    latency_mean_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    errors: int = 0


@dataclass
class BenchmarkReport:
    """Full benchmark report."""

    version: str
    backend: str
    total_memories: int
    results: list[BenchmarkResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    total_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "backend": self.backend,
            "total_memories": self.total_memories,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_seconds": round(self.total_seconds, 3),
            "results": [
                {
                    "operation": r.operation,
                    "count": r.count,
                    "total_seconds": round(r.total_seconds, 3),
                    "ops_per_second": round(r.ops_per_second, 1),
                    "latency_ms": {
                        "min": round(r.latency_min_ms, 2),
                        "max": round(r.latency_max_ms, 2),
                        "mean": round(r.latency_mean_ms, 2),
                        "p50": round(r.latency_p50_ms, 2),
                        "p95": round(r.latency_p95_ms, 2),
                        "p99": round(r.latency_p99_ms, 2),
                    },
                    "errors": r.errors,
                }
                for r in self.results
            ],
        }

    def to_text(self) -> str:
        """Human-readable benchmark report."""
        lines = [
            f"{'=' * 60}",
            "  MemOS Benchmark Report",
            f"{'=' * 60}",
            f"  Version:  {self.version}",
            f"  Backend:  {self.backend}",
            f"  Memories: {self.total_memories}",
            f"  Duration: {self.total_seconds:.2f}s",
            f"{'=' * 60}",
            "",
        ]
        for r in self.results:
            lines.extend(
                [
                    f"  {r.operation.upper()}",
                    f"    {r.count} ops in {r.total_seconds:.3f}s → {r.ops_per_second:.1f} ops/s",
                    f"    Latency: p50={r.latency_p50_ms:.2f}ms  p95={r.latency_p95_ms:.2f}ms  p99={r.latency_p99_ms:.2f}ms",
                    f"    Range:   min={r.latency_min_ms:.2f}ms  max={r.latency_max_ms:.2f}ms  mean={r.latency_mean_ms:.2f}ms",
                    "",
                ]
            )
        return "\n".join(lines)


def _percentile(sorted_data: list[float], p: float) -> float:
    """Calculate percentile from sorted data."""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return d0 + d1


def _measure_operation(
    operation: str,
    func,
    count: int,
) -> BenchmarkResult:
    """Measure an operation's performance."""
    latencies: list[float] = []
    errors = 0

    for _ in range(count):
        start = time.perf_counter()
        try:
            func()
        except Exception:
            errors += 1
        elapsed = (time.perf_counter() - start) * 1000  # ms
        latencies.append(elapsed)

    total_time = sum(latencies) / 1000.0  # seconds
    ops_per_sec = count / total_time if total_time > 0 else 0
    sorted_lat = sorted(latencies)

    return BenchmarkResult(
        operation=operation,
        count=count,
        total_seconds=total_time,
        ops_per_second=ops_per_sec,
        latency_min_ms=sorted_lat[0] if sorted_lat else 0,
        latency_max_ms=sorted_lat[-1] if sorted_lat else 0,
        latency_mean_ms=statistics.mean(latencies) if latencies else 0,
        latency_p50_ms=_percentile(sorted_lat, 50),
        latency_p95_ms=_percentile(sorted_lat, 95),
        latency_p99_ms=_percentile(sorted_lat, 99),
        errors=errors,
    )


def run_benchmark(
    memos: Optional[MemOS] = None,
    memories: int = 1000,
    recall_queries: int = 100,
    search_queries: int = 100,
    backend: str = "memory",
    warmup: int = 50,
) -> BenchmarkReport:
    """Run a full benchmark suite.

    Args:
        memos: Existing MemOS instance (creates one if None).
        memories: Number of memories to insert for the benchmark.
        recall_queries: Number of recall queries to run.
        search_queries: Number of search queries to run.
        backend: Backend to use if creating a new instance.
        warmup: Number of warmup operations before measuring.

    Returns:
        BenchmarkReport with detailed results.
    """
    from . import __version__

    started = datetime.now(timezone.utc).isoformat()

    if memos is None:
        memos = MemOS(backend=backend, sanitize=True)

    results: list[BenchmarkResult] = []

    # ── Phase 1: Warmup ──────────────────────────────────────
    for i in range(warmup):
        memos.learn(f"warmup memory {i}", tags=["warmup"])

    # ── Phase 2: LEARN benchmark ─────────────────────────────
    sample_tags = [
        ["preference"],
        ["infra", "config"],
        ["decision", "project-x"],
        ["bug", "urgent"],
        ["research", "ai"],
        ["meeting", "notes"],
    ]

    def learn_op():
        idx = len(latencies_ref[0]) if latencies_ref[0] else 0
        tags = sample_tags[idx % len(sample_tags)]
        memos.learn(
            f"Benchmark memory entry {idx}: machine learning model training results "
            f"showed {idx}% accuracy improvement on test dataset",
            tags=tags,
            importance=0.3 + (idx % 7) * 0.1,
        )

    # Use a list-of-lists hack for closure access
    latencies_ref: list[list[float]] = [[]]
    learn_result = _measure_operation("learn", learn_op, memories)
    results.append(learn_result)

    # ── Phase 3: RECALL benchmark ────────────────────────────
    recall_queries_list = [
        "machine learning accuracy",
        "model training configuration",
        "project infrastructure setup",
        "bug fix deployment strategy",
        "research paper findings",
        "meeting action items",
        "preference for code style",
        "urgent task priorities",
        "test dataset performance",
        "AI model selection criteria",
    ]

    recall_idx = [0]

    def recall_op():
        q = recall_queries_list[recall_idx[0] % len(recall_queries_list)]
        recall_idx[0] += 1
        memos.recall(q, top=5)

    recall_result = _measure_operation("recall", recall_op, recall_queries)
    results.append(recall_result)

    # ── Phase 4: SEARCH benchmark ────────────────────────────
    search_terms = [
        "benchmark",
        "accuracy",
        "training",
        "model",
        "config",
        "deployment",
        "strategy",
        "preference",
        "urgent",
        "test",
    ]

    search_idx = [0]

    def search_op():
        q = search_terms[search_idx[0] % len(search_terms)]
        search_idx[0] += 1
        memos.search(q=q, limit=20)

    search_result = _measure_operation("search", search_op, search_queries)
    results.append(search_result)

    # ── Phase 5: STATS benchmark ─────────────────────────────
    stats_count = 50

    def stats_op():
        memos.stats()

    stats_result = _measure_operation("stats", stats_op, stats_count)
    results.append(stats_result)

    # ── Phase 6: PRUNE (dry-run) benchmark ───────────────────
    def prune_op():
        memos.prune(threshold=0.1, dry_run=True)

    prune_result = _measure_operation("prune (dry-run)", prune_op, 20)
    results.append(prune_result)

    finished = datetime.now(timezone.utc).isoformat()
    total_time = sum(r.total_seconds for r in results)

    return BenchmarkReport(
        version=__version__,
        backend=backend,
        total_memories=memos.stats().total_memories,
        results=results,
        started_at=started,
        finished_at=finished,
        total_seconds=total_time,
    )
