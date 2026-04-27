"""Tests for the recall quality benchmark suite."""

import json
import unittest

from memos._benchmark_quality_data import CATEGORIES as SplitCategories
from memos._benchmark_quality_data import QUERY_TEMPLATES as SplitQueryTemplates
from memos._benchmark_quality_data import generate_dataset as split_generate_dataset
from memos._benchmark_quality_metrics import _ndcg_at_k as split_ndcg_at_k
from memos._benchmark_quality_models import QualityReport as SplitQualityReport
from memos._benchmark_quality_runner import run_quality_benchmark as split_run_quality_benchmark
from memos.benchmark_quality import (
    CATEGORIES,
    QUERY_TEMPLATES,
    QualityQueryResult,
    QualityReport,
    _is_relevant_for,
    _ndcg_at_k,
    _percentile,
    generate_dataset,
    run_quality_benchmark,
)


class TestDatasetGeneration(unittest.TestCase):
    """Tests for synthetic dataset generation."""

    def test_split_modules_preserve_public_facade(self):
        self.assertIs(CATEGORIES, SplitCategories)
        self.assertIs(QUERY_TEMPLATES, SplitQueryTemplates)
        self.assertIs(generate_dataset, split_generate_dataset)
        self.assertIs(QualityReport, SplitQualityReport)
        self.assertIs(_ndcg_at_k, split_ndcg_at_k)
        self.assertIs(run_quality_benchmark, split_run_quality_benchmark)

    def test_generate_default_dataset(self):
        """Default dataset has correct structure and sizes."""
        memories, queries = generate_dataset()
        # 5 categories * 10 templates = 50 signal memories + 50 noise = 100
        self.assertEqual(len(memories), 100)
        self.assertGreater(len(queries), 0)

    def test_custom_sizes(self):
        """Custom sizes are respected."""
        memories, queries = generate_dataset(
            memories_per_category=5,
            extra_noise=20,
            seed=123,
        )
        # 5 categories * 5 = 25 signal + 20 noise = 45
        self.assertEqual(len(memories), 45)

    def test_categories_complete(self):
        """All categories have templates."""
        for cat, templates in CATEGORIES.items():
            self.assertGreater(len(templates), 0)
            for t in templates:
                self.assertIsInstance(t, str)
                self.assertGreater(len(t), 10)

    def test_queries_have_required_fields(self):
        """Each query has query, category, expected_keywords."""
        for q in QUERY_TEMPLATES:
            self.assertIn("query", q)
            self.assertIn("category", q)
            self.assertIn("expected_keywords", q)
            self.assertIsInstance(q["expected_keywords"], list)

    def test_reproducibility(self):
        """Same seed produces same dataset."""
        m1, q1 = generate_dataset(seed=42)
        m2, q2 = generate_dataset(seed=42)
        self.assertEqual(
            [m["content"] for m in m1],
            [m["content"] for m in m2],
        )

    def test_different_seeds_differ(self):
        """Different seeds produce different importance values."""
        m1, _ = generate_dataset(seed=42)
        m2, _ = generate_dataset(seed=99)
        # Content should be the same
        self.assertEqual(
            [m["content"] for m in m1],
            [m["content"] for m in m2],
        )
        # Importance values should differ due to different random seeds
        imp1 = [m["importance"] for m in m1]
        imp2 = [m["importance"] for m in m2]
        self.assertNotEqual(imp1, imp2)

    def test_memories_have_required_fields(self):
        """Each memory dict has content, tags, importance, category."""
        memories, _ = generate_dataset()
        for m in memories:
            self.assertIn("content", m)
            self.assertIn("tags", m)
            self.assertIn("importance", m)
            self.assertIn("category", m)
            self.assertGreater(len(m["content"]), 0)
            self.assertGreater(len(m["tags"]), 0)


class TestMetricCalculators(unittest.TestCase):
    """Tests for individual metric functions."""

    def test_percentile_empty(self):
        self.assertEqual(_percentile([], 50), 0.0)

    def test_percentile_single(self):
        self.assertAlmostEqual(_percentile([5.0], 50), 5.0)

    def test_percentile_p50(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertAlmostEqual(_percentile(data, 50), 3.0)

    def test_percentile_p95(self):
        data = list(range(1, 101))
        p95 = _percentile(data, 95)
        self.assertGreater(p95, 90)
        self.assertLess(p95, 100)

    def test_ndcg_perfect(self):
        """NDCG for perfect ranking is 1.0."""
        relevances = [True, True, True, True, True]
        self.assertAlmostEqual(_ndcg_at_k(relevances, 5), 1.0)

    def test_ndcg_worst(self):
        """NDCG for no relevant results is 0.0."""
        relevances = [False, False, False, False, False]
        self.assertAlmostEqual(_ndcg_at_k(relevances, 5), 0.0)

    def test_ndcg_partial(self):
        """NDCG for mixed results is between 0 and 1."""
        relevances = [True, False, True, False, False]
        ndcg = _ndcg_at_k(relevances, 5)
        self.assertGreater(ndcg, 0.0)
        self.assertLess(ndcg, 1.0)

    def test_ndcg_empty(self):
        self.assertEqual(_ndcg_at_k([], 5), 0.0)

    def test_is_relevant_dict(self):
        """_is_relevant_for works with dict query spec."""
        spec = {"expected_keywords": ["Alice", "ML", "NLP"]}
        self.assertTrue(_is_relevant_for(spec, "Alice Chen is a senior ML engineer"))
        self.assertFalse(_is_relevant_for(spec, "weather forecast shows rain"))

    def test_is_relevant_dataclass(self):
        """_is_relevant_for works with QualityQueryResult."""
        qr = QualityQueryResult(
            query="test",
            expected_category="person",
            expected_keywords=["Alice", "ML"],
            returned_ids=[],
            returned_contents=[],
            scores=[],
            hit=False,
            hit_rank=None,
            precision_at_k=0.0,
            latency_ms=0.0,
        )
        self.assertTrue(_is_relevant_for(qr, "Alice works on ML models"))
        self.assertFalse(_is_relevant_for(qr, "Bob manages operations"))

    def test_is_relevant_case_insensitive(self):
        spec = {"expected_keywords": ["Alice", "NLP"]}
        self.assertTrue(_is_relevant_for(spec, "alice is an nlp specialist"))


class TestQualityReport(unittest.TestCase):
    """Tests for QualityReport serialization."""

    def _make_report(self) -> QualityReport:
        return QualityReport(
            version="0.31.0",
            backend="memory",
            total_memories=100,
            total_queries=20,
            top_k=5,
            recall_at_k=0.85,
            mrr=0.57,
            precision_at_k=0.20,
            ndcg_at_k=0.62,
            zero_result_rate=0.0,
            avg_latency_ms=100.0,
            p50_latency_ms=95.0,
            p95_latency_ms=150.0,
        )

    def test_to_dict_keys(self):
        report = self._make_report()
        d = report.to_dict()
        self.assertIn("version", d)
        self.assertIn("metrics", d)
        self.assertIn("latency", d)
        self.assertIn("recall_at_k", d["metrics"])
        self.assertIn("mrr", d["metrics"])
        self.assertIn("precision_at_k", d["metrics"])
        self.assertIn("ndcg_at_k", d["metrics"])

    def test_to_dict_json_serializable(self):
        report = self._make_report()
        d = report.to_dict()
        text = json.dumps(d)
        self.assertIsInstance(text, str)

    def test_to_text_contains_metrics(self):
        report = self._make_report()
        text = report.to_text()
        self.assertIn("Recall@5", text)
        self.assertIn("MRR", text)
        self.assertIn("NDCG@5", text)
        self.assertIn("85.0%", text)

    def test_to_dict_with_decay(self):
        report = self._make_report()
        report.decay_impact_score = 0.05
        d = report.to_dict()
        self.assertIn("decay_impact_score", d)

    def test_to_dict_with_scalability(self):
        report = self._make_report()
        report.scalability_results = [
            {"memories": 50, "recall_at_k": 0.9, "avg_latency_ms": 80.0},
            {"memories": 200, "recall_at_k": 0.8, "avg_latency_ms": 120.0},
        ]
        d = report.to_dict()
        self.assertIn("scalability", d)
        self.assertEqual(len(d["scalability"]), 2)

    def test_to_text_with_scalability(self):
        report = self._make_report()
        report.scalability_results = [
            {"memories": 50, "recall_at_k": 0.9, "avg_latency_ms": 80.0},
        ]
        text = report.to_text()
        self.assertIn("Scalability", text)


class TestRunQualityBenchmark(unittest.TestCase):
    """Integration tests for run_quality_benchmark."""

    def test_basic_run(self):
        """Benchmark completes with reasonable metrics."""
        report = run_quality_benchmark(
            memories_per_category=2,
            extra_noise=5,
            top_k=3,
            seed=42,
            run_decay=False,
            backend="memory",
        )
        self.assertIsInstance(report, QualityReport)
        self.assertGreater(report.total_memories, 0)
        self.assertGreater(report.total_queries, 0)
        self.assertGreaterEqual(report.recall_at_k, 0.0)
        self.assertLessEqual(report.recall_at_k, 1.0)
        self.assertGreaterEqual(report.mrr, 0.0)
        self.assertLessEqual(report.mrr, 1.0)
        self.assertGreaterEqual(report.ndcg_at_k, 0.0)
        self.assertLessEqual(report.ndcg_at_k, 1.0)
        self.assertGreater(report.avg_latency_ms, 0.0)

    def test_metrics_with_hits(self):
        """With known small dataset, some queries should hit."""
        report = run_quality_benchmark(
            memories_per_category=10,
            extra_noise=0,  # No noise → higher accuracy expected
            top_k=5,
            seed=42,
            run_decay=False,
            backend="memory",
        )
        self.assertGreater(report.recall_at_k, 0.0)

    def test_zero_noise_high_recall(self):
        """Without noise, recall should be relatively high."""
        report = run_quality_benchmark(
            memories_per_category=10,
            extra_noise=0,
            top_k=10,
            seed=42,
            run_decay=False,
            backend="memory",
        )
        # With no noise and top-10, recall should be meaningful
        self.assertGreater(report.recall_at_k, 0.3)

    def test_with_decay(self):
        """Decay benchmark runs and returns a score."""
        report = run_quality_benchmark(
            memories_per_category=3,
            extra_noise=5,
            top_k=3,
            seed=42,
            run_decay=True,
            backend="memory",
        )
        # Decay impact should be a number (not None)
        self.assertIsNotNone(report.decay_impact_score)

    def test_json_serializable_full_report(self):
        """Full report (with query_results) serializes to JSON."""
        report = run_quality_benchmark(
            memories_per_category=2,
            extra_noise=3,
            top_k=3,
            seed=42,
            run_decay=False,
            backend="memory",
        )
        d = report.to_dict()
        text = json.dumps(d, indent=2)
        parsed = json.loads(text)
        self.assertIn("metrics", parsed)

    def test_report_has_timing(self):
        report = run_quality_benchmark(
            memories_per_category=2,
            extra_noise=2,
            top_k=3,
            seed=42,
            run_decay=False,
            backend="memory",
        )
        self.assertNotEqual(report.started_at, "")
        self.assertNotEqual(report.finished_at, "")

    def test_precision_within_bounds(self):
        report = run_quality_benchmark(
            memories_per_category=5,
            extra_noise=10,
            top_k=5,
            seed=42,
            run_decay=False,
            backend="memory",
        )
        self.assertGreaterEqual(report.precision_at_k, 0.0)
        self.assertLessEqual(report.precision_at_k, 1.0)

    def test_zero_result_rate_within_bounds(self):
        report = run_quality_benchmark(
            memories_per_category=5,
            extra_noise=10,
            top_k=5,
            seed=42,
            run_decay=False,
            backend="memory",
        )
        self.assertGreaterEqual(report.zero_result_rate, 0.0)
        self.assertLessEqual(report.zero_result_rate, 1.0)


class TestQualityQueryResult(unittest.TestCase):
    """Tests for QualityQueryResult dataclass."""

    def test_fields(self):
        qr = QualityQueryResult(
            query="Who is Alice?",
            expected_category="person",
            expected_keywords=["Alice", "ML"],
            returned_ids=["abc", "def"],
            returned_contents=["Alice is ML engineer", "Bob manages ops"],
            scores=[0.9, 0.3],
            hit=True,
            hit_rank=1,
            precision_at_k=0.5,
            latency_ms=42.5,
        )
        self.assertEqual(qr.query, "Who is Alice?")
        self.assertTrue(qr.hit)
        self.assertEqual(qr.hit_rank, 1)
        self.assertEqual(qr.precision_at_k, 0.5)

    def test_no_hit(self):
        qr = QualityQueryResult(
            query="unknown topic",
            expected_category="person",
            expected_keywords=["Nobody"],
            returned_ids=[],
            returned_contents=[],
            scores=[],
            hit=False,
            hit_rank=None,
            precision_at_k=0.0,
            latency_ms=10.0,
        )
        self.assertFalse(qr.hit)
        self.assertIsNone(qr.hit_rank)


if __name__ == "__main__":
    unittest.main()
