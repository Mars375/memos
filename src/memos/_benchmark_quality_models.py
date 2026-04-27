"""Report models for recall quality benchmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class QualityQueryResult:
    """Result of a single quality benchmark query."""

    query: str
    expected_category: str
    expected_keywords: list[str]
    returned_ids: list[str]
    returned_contents: list[str]
    scores: list[float]
    hit: bool
    hit_rank: Optional[int]
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
    recall_at_k: float
    mrr: float
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
        """Return a JSON-serializable summary report."""
        data: dict[str, Any] = {
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
            data["decay_impact_score"] = round(self.decay_impact_score, 4)
        if self.scalability_results is not None:
            data["scalability"] = self.scalability_results
        data["timing"] = {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_seconds": round(self.total_seconds, 3),
        }
        return data

    def to_text(self) -> str:
        """Human-readable quality benchmark report."""
        lines = [
            f"{'=' * 60}",
            "  MemOS Recall Quality Benchmark",
            f"{'=' * 60}",
            f"  Version:     {self.version}",
            f"  Backend:     {self.backend}",
            f"  Memories:    {self.total_memories}",
            f"  Queries:     {self.total_queries}",
            f"  Top-K:       {self.top_k}",
            f"{'=' * 60}",
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
            for result in self.scalability_results:
                lines.append(
                    f"    {result['memories']} memories → "
                    f"recall@{self.top_k}={result['recall_at_k']:.1%}, "
                    f"avg_latency={result['avg_latency_ms']:.1f}ms"
                )
        lines.extend(["", f"{'=' * 60}"])
        return "\n".join(lines)


__all__ = ["QualityQueryResult", "QualityReport"]
