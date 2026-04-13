"""Recall quality benchmark suite for MemOS.

Measures recall accuracy, relevance, and decay behavior using synthetic
datasets with known ground truth. Inspired by LongMemEval / MemPalace benchmarks.

Usage:
    # CLI
    memos benchmark-quality
    memos benchmark-quality --size 500 --top 5 --json
    memos benchmark-quality --suite recall,decay,scalability

    # Programmatic
    from memos.benchmark_quality import run_quality_benchmark
    report = run_quality_benchmark(memories=200)
"""

from __future__ import annotations

import math
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .core import MemOS
from .models import RecallResult

# ── Synthetic Dataset ─────────────────────────────────────────────────────────

CATEGORIES: dict[str, list[str]] = {
    "person": [
        "Alice Chen is a senior ML engineer specializing in NLP",
        "Bob Martinez leads the infrastructure team at Acme Corp",
        "Carol Williams designed the microservices architecture",
        "David Park manages customer success operations",
        "Eva Schmidt researches reinforcement learning at DeepMind",
        "Frank Lee built the real-time data pipeline",
        "Grace Kim oversees security compliance audits",
        "Henry Zhang developed the recommendation engine",
        "Iris Johnson coordinates cross-team sprints",
        "Jack Brown maintains the CI/CD pipeline",
    ],
    "project": [
        "Project Phoenix migrates legacy Java services to Go microservices",
        "Project Atlas builds a unified data platform across teams",
        "Project Beacon implements real-time monitoring dashboards",
        "Project Catalyst upgrades the ML inference pipeline to GPU",
        "Project Delta redesigns the customer onboarding flow",
        "Project Echo adds end-to-end encryption to all API endpoints",
        "Project Falcon deploys edge computing nodes in 5 regions",
        "Project Gamma refactors the billing system for multi-currency",
        "Project Helios integrates solar panel telemetry data",
        "Project Ion develops quantum-resistant cryptography modules",
    ],
    "decision": [
        "Decided to use PostgreSQL over MongoDB for transactional data integrity",
        "Chose Kubernetes over Nomad for container orchestration standardization",
        "Adopted TypeScript instead of JavaScript for type safety at scale",
        "Selected gRPC for internal services, REST for external APIs",
        "Moved from Jenkins to GitHub Actions for CI/CD modernization",
        "Switched to RUST for the performance-critical data parser module",
        "Approved React Server Components for the new dashboard frontend",
        "Decided on event-driven architecture using Apache Kafka",
        "Chose Terraform over CloudFormation for multi-cloud IaC",
        "Adopted OIDC with SSO for unified authentication across services",
    ],
    "preference": [
        "Prefer dark mode interfaces with monospace fonts for readability",
        "Always use conventional commits with scope prefixes",
        "Prefer async communication over synchronous meetings",
        "Code reviews should be completed within 24 hours maximum",
        "Use semantic versioning with prerelease tags for beta features",
        "Prefer horizontal scaling over vertical for all stateless services",
        "Documentation should live alongside code in docs/ directories",
        "Prefer managed services over self-hosted for non-core infrastructure",
        "All APIs must have OpenAPI specs generated at build time",
        "Use feature flags for gradual rollouts to production",
    ],
    "incident": [
        "Outage on 2025-03-15: Redis cluster failed over, 12min downtime",
        "Memory leak in auth-service caused OOM kills every 6 hours",
        "SSL certificate expired on staging, blocking deploys for 4 hours",
        "Database migration locked production users table for 8 minutes",
        "CDN misconfiguration served stale assets to 30% of users",
        "DNS propagation delay caused regional outage in APAC zone",
        "Rate limiter bug blocked legitimate traffic at 1000 req/s",
        "Backup restore took 3 hours due to uncompressed snapshots",
        "Load balancer health check timeout too aggressive during peak",
        "Third-party API deprecation broke payment processing module",
    ],
}

QUERY_TEMPLATES: list[dict[str, Any]] = [
    # (query, expected_category, relevance_checker)
    {"query": "Who works on machine learning?", "category": "person", "expected_keywords": ["Alice", "ML", "NLP", "Eva", "reinforcement"]},
    {"query": "What is Project Phoenix about?", "category": "project", "expected_keywords": ["Phoenix", "Java", "Go", "microservices", "migrate"]},
    {"query": "Why did we choose PostgreSQL?", "category": "decision", "expected_keywords": ["PostgreSQL", "MongoDB", "transactional", "integrity"]},
    {"query": "What are the coding preferences?", "category": "preference", "expected_keywords": ["commits", "code review", "dark mode", "monospace"]},
    {"query": "What was the Redis incident?", "category": "incident", "expected_keywords": ["Redis", "outage", "downtime", "cluster", "failover"]},
    {"query": "Who built the data pipeline?", "category": "person", "expected_keywords": ["Frank", "data pipeline", "real-time"]},
    {"query": "Tell me about Project Atlas", "category": "project", "expected_keywords": ["Atlas", "data platform", "unified"]},
    {"query": "Why gRPC for internal services?", "category": "decision", "expected_keywords": ["gRPC", "REST", "internal", "external"]},
    {"query": "How do we handle code reviews?", "category": "preference", "expected_keywords": ["code review", "24 hours", "review"]},
    {"query": "What happened with the SSL certificate?", "category": "incident", "expected_keywords": ["SSL", "certificate", "staging", "expired"]},
    {"query": "Who handles security?", "category": "person", "expected_keywords": ["Grace", "security", "compliance", "audit"]},
    {"query": "What does Project Echo do?", "category": "project", "expected_keywords": ["Echo", "encryption", "API"]},
    {"query": "Why Kubernetes over Nomad?", "category": "decision", "expected_keywords": ["Kubernetes", "Nomad", "orchestration"]},
    {"query": "What is our scaling strategy?", "category": "preference", "expected_keywords": ["horizontal", "scaling", "stateless"]},
    {"query": "What caused the database migration issue?", "category": "incident", "expected_keywords": ["database", "migration", "locked", "users"]},
    {"query": "Who designed the architecture?", "category": "person", "expected_keywords": ["Carol", "microservices", "architecture"]},
    {"query": "Project Beacon monitoring", "category": "project", "expected_keywords": ["Beacon", "monitoring", "dashboard"]},
    {"query": "Why did we adopt TypeScript?", "category": "decision", "expected_keywords": ["TypeScript", "JavaScript", "type safety"]},
    {"query": "What CI/CD tool do we use?", "category": "decision", "expected_keywords": ["GitHub Actions", "Jenkins", "CI/CD"]},
    {"query": "DNS outage in Asia Pacific", "category": "incident", "expected_keywords": ["DNS", "APAC", "outage", "propagation"]},
]


@dataclass
class QualityQueryResult:
    """Result of a single quality benchmark query."""
    query: str
    expected_category: str
    expected_keywords: list[str]
    returned_ids: list[str]
    returned_contents: list[str]
    scores: list[float]
    hit: bool  # At least one expected memory in results
    hit_rank: Optional[int]  # Rank of first relevant result (1-based)
    precision_at_k: float
    latency_ms: float


@dataclass
class QualityReport:
    """Full quality benchmark report."""
    version: str
    backend: str
    total_memories: int
    total_queries: int
    top_k: int
    recall_at_k: float  # Hit rate
    mrr: float  # Mean Reciprocal Rank
    precision_at_k: float
    ndcg_at_k: float
    zero_result_rate: float
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    decay_impact_score: Optional[float] = None
    scalability_results: Optional[list[dict[str, Any]]] = None
    query_results: list[QualityQueryResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    total_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "version": self.version,
            "backend": self.backend,
            "total_memories": self.total_memories,
            "total_queries": self.total_queries,
            "top_k": self.top_k,
            "metrics": {
                "recall_at_k": round(self.recall_at_k, 4),
                "mrr": round(self.mrr, 4),
                "precision_at_k": round(self.precision_at_k, 4),
                "ndcg_at_k": round(self.ndcg_at_k, 4),
                "zero_result_rate": round(self.zero_result_rate, 4),
            },
            "latency": {
                "avg_ms": round(self.avg_latency_ms, 2),
                "p50_ms": round(self.p50_latency_ms, 2),
                "p95_ms": round(self.p95_latency_ms, 2),
            },
        }
        if self.decay_impact_score is not None:
            d["decay_impact_score"] = round(self.decay_impact_score, 4)
        if self.scalability_results is not None:
            d["scalability"] = self.scalability_results
        d["timing"] = {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_seconds": round(self.total_seconds, 3),
        }
        return d

    def to_text(self) -> str:
        """Human-readable quality benchmark report."""
        lines = [
            f"{'='*60}",
            "  MemOS Recall Quality Benchmark",
            f"{'='*60}",
            f"  Version:     {self.version}",
            f"  Backend:     {self.backend}",
            f"  Memories:    {self.total_memories}",
            f"  Queries:     {self.total_queries}",
            f"  Top-K:       {self.top_k}",
            f"{'='*60}",
            "",
            f"  Recall@{self.top_k}:    {self.recall_at_k:.1%}  (hit rate)",
            f"  MRR:          {self.mrr:.4f}   (mean reciprocal rank)",
            f"  Precision@{self.top_k}: {self.precision_at_k:.1%}",
            f"  NDCG@{self.top_k}:      {self.ndcg_at_k:.4f}",
            f"  Zero-result:  {self.zero_result_rate:.1%}",
            "",
            f"  Latency avg:  {self.avg_latency_ms:.1f}ms",
            f"  Latency p50:  {self.p50_latency_ms:.1f}ms",
            f"  Latency p95:  {self.p95_latency_ms:.1f}ms",
        ]
        if self.decay_impact_score is not None:
            lines.append(f"  Decay impact: {self.decay_impact_score:.4f}")
        if self.scalability_results:
            lines.append("")
            lines.append("  Scalability:")
            for sr in self.scalability_results:
                lines.append(
                    f"    {sr['memories']} memories → "
                    f"recall@{self.top_k}={sr['recall_at_k']:.1%}, "
                    f"avg_latency={sr['avg_latency_ms']:.1f}ms"
                )
        lines.extend(["", f"{'='*60}"])
        return "\n".join(lines)


# ── Metric Calculators ────────────────────────────────────────────────────────

def _is_relevant(query_result: QualityQueryResult, content: str) -> bool:
    """Check if a returned memory is relevant to the query."""
    content_lower = content.lower()
    kw_hits = sum(1 for kw in query_result.expected_keywords if kw.lower() in content_lower)
    return kw_hits >= 1


def _ndcg_at_k(relevances: list[bool], k: int) -> float:
    """Compute NDCG@K."""
    def dcg(rels: list[float]) -> float:
        return sum(rel / math.log2(i + 2) for i, rel in enumerate(rels))

    actual = [1.0 if r else 0.0 for r in relevances[:k]]
    ideal = sorted(actual, reverse=True)
    if not ideal or sum(ideal) == 0:
        return 0.0
    return dcg(actual) / dcg(ideal)


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


# ── Dataset Generator ─────────────────────────────────────────────────────────

def generate_dataset(
    memories_per_category: int = 10,
    extra_noise: int = 50,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate a synthetic dataset with ground truth.

    Returns:
        (memories, queries) — lists of dicts with known expected results.
    """
    rng = random.Random(seed)
    memories: list[dict[str, Any]] = []

    for category, templates in CATEGORIES.items():
        for i, template in enumerate(templates[:memories_per_category]):
            memories.append({
                "content": template,
                "tags": [category],
                "importance": 0.3 + rng.random() * 0.6,
                "category": category,
                "idx": i,
            })

    # Add noise memories (should NOT be recalled for our queries)
    noise_topics = [
        "weather forecast shows rain tomorrow afternoon",
        "grocery list: milk, eggs, bread, avocados, cheese",
        "the movie starts at 8pm at the downtown theater",
        "flight UA-456 departs from gate B12 at terminal 2",
        "restaurant reservation for 7 people on Saturday evening",
        "yoga class is cancelled this week due to renovation",
        "car oil change scheduled for next Tuesday morning",
        "book club meeting discusses chapter 5 of the novel",
        "garden tomatoes are ready for harvest this weekend",
        "local park has a new running trail about 3km long",
    ]
    for i in range(extra_noise):
        topic = noise_topics[i % len(noise_topics)]
        memories.append({
            "content": f"{topic} — note #{i+1}",
            "tags": ["noise"],
            "importance": 0.2 + rng.random() * 0.3,
            "category": "noise",
            "idx": i,
        })

    return memories, QUERY_TEMPLATES


# ── Main Benchmark Runner ─────────────────────────────────────────────────────

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
    """Run a full recall quality benchmark.

    Args:
        memos: Existing MemOS instance (creates one if None).
        memories_per_category: Memories per category in dataset.
        extra_noise: Noise memories to add.
        top_k: Number of results per recall query.
        seed: Random seed for reproducibility.
        run_decay: Whether to run decay behavior test.
        run_scalability: Whether to run scalability test.
        scalability_sizes: Dataset sizes for scalability test.
        backend: Backend to use if creating a new instance.

    Returns:
        QualityReport with detailed metrics.
    """
    from datetime import datetime, timezone

    from . import __version__

    started = datetime.now(timezone.utc).isoformat()

    if memos is None:
        memos = MemOS(backend=backend, sanitize=True)

    # ── Generate and load dataset ────────────────────────────
    dataset_memories, queries = generate_dataset(
        memories_per_category=memories_per_category,
        extra_noise=extra_noise,
        seed=seed,
    )

    # Learn all memories
    id_to_meta: dict[str, dict[str, Any]] = {}
    for m in dataset_memories:
        item = memos.learn(
            m["content"],
            tags=m["tags"],
            importance=m["importance"],
        )
        id_to_meta[item.id] = m

    total_memories = memos.stats().total_memories

    # ── Run recall queries ───────────────────────────────────
    query_results: list[QualityQueryResult] = []
    for q in queries:
        start = time.perf_counter()
        results: list[RecallResult] = memos.recall(q["query"], top=top_k)
        latency = (time.perf_counter() - start) * 1000

        returned_ids = [r.item.id for r in results]
        returned_contents = [r.item.content for r in results]
        scores = [r.score for r in results]

        # Check relevance
        relevances = [_is_relevant_for(q, c) for c in returned_contents]
        hit = any(relevances)
        hit_rank = None
        for i, rel in enumerate(relevances):
            if rel:
                hit_rank = i + 1
                break

        relevant_count = sum(relevances)
        prec_k = relevant_count / top_k if top_k > 0 else 0.0

        query_results.append(QualityQueryResult(
            query=q["query"],
            expected_category=q["category"],
            expected_keywords=q["expected_keywords"],
            returned_ids=returned_ids,
            returned_contents=returned_contents,
            scores=scores,
            hit=hit,
            hit_rank=hit_rank,
            precision_at_k=prec_k,
            latency_ms=latency,
        ))

    # ── Compute aggregate metrics ────────────────────────────
    n = len(query_results)
    recall_at_k = sum(1 for qr in query_results if qr.hit) / n if n > 0 else 0.0

    mrr_sum = 0.0
    for qr in query_results:
        if qr.hit_rank is not None:
            mrr_sum += 1.0 / qr.hit_rank
    mrr = mrr_sum / n if n > 0 else 0.0

    precision_at_k = sum(qr.precision_at_k for qr in query_results) / n if n > 0 else 0.0

    ndcg_scores = []
    for qr in query_results:
        relevances = [_is_relevant_for(qr, c) for c in qr.returned_contents]
        ndcg_scores.append(_ndcg_at_k(relevances, top_k))
    ndcg_at_k = statistics.mean(ndcg_scores) if ndcg_scores else 0.0

    zero_result_rate = sum(1 for qr in query_results if len(qr.returned_ids) == 0) / n if n > 0 else 0.0

    latencies = sorted(qr.latency_ms for qr in query_results)
    avg_latency = statistics.mean(latencies) if latencies else 0.0
    p50_latency = _percentile(latencies, 50)
    p95_latency = _percentile(latencies, 95)

    # ── Decay behavior test ──────────────────────────────────
    decay_impact = None
    if run_decay:
        decay_impact = _run_decay_benchmark(memos, dataset_memories, queries, top_k, seed)

    # ── Scalability test ─────────────────────────────────────
    scalability_results = None
    if run_scalability and scalability_sizes:
        scalability_results = _run_scalability_benchmark(
            scalability_sizes, queries, top_k, seed, backend,
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


def _is_relevant_for(query_spec, content: str) -> bool:
    """Check if content is relevant to a query specification."""
    content_lower = content.lower()
    keywords = getattr(query_spec, "expected_keywords", None) or (query_spec.get("expected_keywords", []) if isinstance(query_spec, dict) else [])
    hits = sum(1 for kw in keywords if kw.lower() in content_lower)
    return hits >= 1


def _run_decay_benchmark(
    memos: MemOS,
    dataset_memories: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    top_k: int,
    seed: int,
) -> float:
    """Measure how decay affects recall ranking.

    Strategy: Pick 5 queries, record their scores, decay all memories,
    then re-run queries and measure score delta.
    """
    sample_queries = queries[:5]

    before_scores: list[float] = []
    for q in sample_queries:
        results = memos.recall(q["query"], top=top_k)
        before_scores.append(max((r.score for r in results), default=0.0))

    # Run decay on actual items with aggressive params
    try:
        all_items = memos._store.list_all(namespace=memos._namespace)
        memos._decay.run_decay(
            items=all_items,
            min_age_days=0,
            floor=0.01,
            dry_run=False,
        )
        # Persist decayed items
        for item in all_items:
            memos._store.upsert(item, namespace=memos._namespace)
    except Exception:
        # Fallback: manual decay
        try:
            all_items = memos._store.list_all(namespace=memos._namespace)
            for item in all_items:
                item.importance = max(0.01, item.importance * 0.5)
                memos._store.upsert(item, namespace=memos._namespace)
        except Exception:
            return -1.0

    after_scores: list[float] = []
    for q in sample_queries:
        results = memos.recall(q["query"], top=top_k)
        after_scores.append(max((r.score for r in results), default=0.0))

    # Decay impact = average score reduction (positive = decay reduced scores)
    deltas = [b - a for b, a in zip(before_scores, after_scores)]
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

        # Generate dataset scaled to target size
        noise_ratio = 0.3
        signal_count = max(10, int(size * (1 - noise_ratio)))
        noise_count = size - signal_count

        ds, _ = generate_dataset(
            memories_per_category=max(1, signal_count // 5),
            extra_noise=noise_count,
            seed=seed,
        )

        for m in ds[:size]:
            memos.learn(m["content"], tags=m["tags"], importance=m["importance"])

        # Run queries
        hits = 0
        latencies = []
        sample = queries[:10]
        for q in sample:
            start = time.perf_counter()
            res = memos.recall(q["query"], top=top_k)
            latencies.append((time.perf_counter() - start) * 1000)
            if res:
                contents = [r.item.content for r in res]
                if any(_is_relevant_for(q, c) for c in contents):
                    hits += 1

        results.append({
            "memories": size,
            "recall_at_k": hits / len(sample) if sample else 0.0,
            "avg_latency_ms": statistics.mean(latencies) if latencies else 0.0,
        })

    return results
