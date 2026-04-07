"""Tests for the benchmark module."""

import json
import pytest

from memos.benchmark import run_benchmark, BenchmarkReport, BenchmarkResult, _percentile
from memos.core import MemOS


class TestPercentile:
    """Tests for the _percentile helper."""

    def test_single_value(self):
        assert _percentile([5.0], 50) == 5.0

    def test_p50_even(self):
        data = [1.0, 2.0, 3.0, 4.0]
        result = _percentile(data, 50)
        assert 2.0 <= result <= 3.0

    def test_p0(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(data, 0) == 1.0

    def test_p100(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(data, 100) == 5.0

    def test_empty(self):
        assert _percentile([], 50) == 0.0


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_creation(self):
        r = BenchmarkResult(
            operation="learn",
            count=100,
            total_seconds=1.5,
            ops_per_second=66.7,
            latency_min_ms=10.0,
            latency_max_ms=50.0,
            latency_mean_ms=15.0,
            latency_p50_ms=14.0,
            latency_p95_ms=40.0,
            latency_p99_ms=48.0,
        )
        assert r.operation == "learn"
        assert r.count == 100
        assert r.errors == 0


class TestBenchmarkReport:
    """Tests for BenchmarkReport."""

    def _make_report(self) -> BenchmarkReport:
        return BenchmarkReport(
            version="0.15.0",
            backend="memory",
            total_memories=1000,
            results=[
                BenchmarkResult(
                    operation="learn",
                    count=100,
                    total_seconds=1.0,
                    ops_per_second=100.0,
                    latency_min_ms=5.0,
                    latency_max_ms=20.0,
                    latency_mean_ms=10.0,
                    latency_p50_ms=9.0,
                    latency_p95_ms=18.0,
                    latency_p99_ms=19.0,
                ),
            ],
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:01:00Z",
            total_seconds=1.0,
        )

    def test_to_dict(self):
        report = self._make_report()
        d = report.to_dict()
        assert d["version"] == "0.15.0"
        assert d["backend"] == "memory"
        assert len(d["results"]) == 1
        assert d["results"][0]["operation"] == "learn"
        assert "latency_ms" in d["results"][0]
        assert d["results"][0]["latency_ms"]["p50"] == 9.0

    def test_to_dict_json_serializable(self):
        report = self._make_report()
        json_str = json.dumps(report.to_dict())
        assert json_str is not None
        parsed = json.loads(json_str)
        assert parsed["version"] == "0.15.0"

    def test_to_text(self):
        report = self._make_report()
        text = report.to_text()
        assert "MemOS Benchmark Report" in text
        assert "LEARN" in text
        assert "ops/s" in text
        assert "p50=" in text
        assert "p95=" in text


class TestRunBenchmark:
    """Integration tests for run_benchmark."""

    def test_small_benchmark(self):
        """Run a small benchmark to verify it completes."""
        memos = MemOS(backend="memory")
        report = run_benchmark(
            memos=memos,
            memories=50,
            recall_queries=10,
            search_queries=10,
            warmup=5,
        )
        assert report.backend == "memory"
        assert len(report.results) >= 4  # learn, recall, search, stats, prune
        assert report.total_seconds > 0
        assert report.started_at != ""
        assert report.finished_at != ""

    def test_benchmark_learn_result(self):
        """Verify learn benchmark has valid metrics."""
        memos = MemOS(backend="memory")
        report = run_benchmark(memos=memos, memories=20, warmup=2)
        learn = next(r for r in report.results if r.operation == "learn")
        assert learn.count == 20
        assert learn.ops_per_second > 0
        assert learn.latency_min_ms > 0
        assert learn.latency_p50_ms >= learn.latency_min_ms
        assert learn.latency_p99_ms >= learn.latency_p95_ms

    def test_benchmark_recall_result(self):
        """Verify recall benchmark has valid metrics."""
        memos = MemOS(backend="memory")
        report = run_benchmark(memos=memos, memories=30, recall_queries=5, warmup=2)
        recall = next(r for r in report.results if r.operation == "recall")
        assert recall.count == 5
        assert recall.ops_per_second > 0

    def test_benchmark_creates_instance(self):
        """Run without providing an instance."""
        report = run_benchmark(memories=10, warmup=2)
        assert report.results is not None
        assert len(report.results) >= 1

    def test_benchmark_report_serialization(self):
        """Full roundtrip: run → dict → JSON."""
        memos = MemOS(backend="memory")
        report = run_benchmark(memos=memos, memories=15, warmup=2)
        data = report.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["total_memories"] > 0
        # At least learn and recall should have valid latencies
        learn = next(r for r in parsed["results"] if r["operation"] == "learn")
        assert learn["ops_per_second"] > 0
        assert learn["latency_ms"]["p50"] > 0
        recall = next(r for r in parsed["results"] if r["operation"] == "recall")
        assert recall["ops_per_second"] > 0
