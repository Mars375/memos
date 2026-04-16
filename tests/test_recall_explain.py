"""Tests for P35 — Recall Explainability (score breakdown)."""

from memos.core import MemOS
from memos.models import MemoryItem, RecallResult, ScoreBreakdown


class TestScoreBreakdownModel:
    """Test ScoreBreakdown dataclass."""

    def test_defaults(self):
        bd = ScoreBreakdown()
        assert bd.semantic == 0.0
        assert bd.keyword == 0.0
        assert bd.importance == 0.0
        assert bd.recency == 0.0
        assert bd.tag_bonus == 0.0
        assert bd.total == 0.0
        assert bd.backend == ""

    def test_to_dict(self):
        bd = ScoreBreakdown(
            semantic=0.3,
            keyword=0.2,
            importance=0.05,
            recency=0.02,
            tag_bonus=0.1,
            total=0.67,
            backend="hybrid",
        )
        d = bd.to_dict()
        assert d["semantic"] == 0.3
        assert d["keyword"] == 0.2
        assert d["importance"] == 0.05
        assert d["recency"] == 0.02
        assert d["tag_bonus"] == 0.1
        assert d["total"] == 0.67
        assert d["backend"] == "hybrid"

    def test_to_dict_rounding(self):
        bd = ScoreBreakdown(semantic=0.12345, total=0.98765)
        d = bd.to_dict()
        assert d["semantic"] == 0.1235  # rounded to 4 decimals
        assert d["total"] == 0.9877


class TestRecallResultBreakdown:
    """Test RecallResult with optional score_breakdown."""

    def test_no_breakdown(self):
        item = MemoryItem(id="test1", content="hello")
        r = RecallResult(item=item, score=0.5, match_reason="keyword")
        assert r.score_breakdown is None

    def test_with_breakdown(self):
        item = MemoryItem(id="test2", content="world")
        bd = ScoreBreakdown(keyword=0.4, total=0.4, backend="keyword-only")
        r = RecallResult(item=item, score=0.4, match_reason="keyword", score_breakdown=bd)
        assert r.score_breakdown.keyword == 0.4
        assert r.score_breakdown.backend == "keyword-only"


class TestRecallExplainIntegration:
    """Integration: recall results contain score_breakdown."""

    def setup_method(self):
        self.memos = MemOS(backend="memory")
        self.memos.learn("Alice works on infrastructure at Acme Corp", tags=["project", "person"], importance=0.8)
        self.memos.learn("Deployed new monitoring stack yesterday", tags=["deployment", "monitoring"], importance=0.6)
        self.memos.learn("The quick brown fox jumps over the lazy dog", tags=["test"], importance=0.3)

    def test_recall_has_breakdown(self):
        results = self.memos.recall("Alice infrastructure", top=5)
        assert len(results) > 0
        for r in results:
            assert r.score_breakdown is not None
            assert isinstance(r.score_breakdown, ScoreBreakdown)

    def test_breakdown_components_sum(self):
        results = self.memos.recall("Alice infrastructure", top=5)
        for r in results:
            bd = r.score_breakdown
            # Components should add up to approximately the total
            component_sum = bd.semantic + bd.keyword + bd.importance + bd.recency + bd.tag_bonus + bd.temporal_proximity
            assert abs(component_sum - bd.total) < 0.01, f"Components {component_sum} != total {bd.total}"

    def test_breakdown_semantic_dominant(self):
        # When using keyword match, keyword score should be > 0
        results = self.memos.recall("quick brown fox", top=1)
        assert len(results) > 0
        bd = results[0].score_breakdown
        assert bd.keyword > 0 or bd.semantic > 0  # at least one signal

    def test_breakdown_importance_reflected(self):
        results = self.memos.recall("Alice infrastructure", top=5)
        # High importance memory should have higher importance boost
        alice_result = next((r for r in results if "Alice" in r.item.content), None)
        if alice_result:
            assert alice_result.score_breakdown.importance > 0

    def test_breakdown_backend_set(self):
        results = self.memos.recall("test query", top=5)
        for r in results:
            assert r.score_breakdown.backend in ("hybrid", "keyword-only", "qdrant")


class TestRecallExplainCLI:
    """Test CLI --explain flag."""

    def test_explain_flag_in_parser(self):
        """Parser accepts --explain."""
        from memos.cli import build_parser

        parser = build_parser()
        # Should not raise
        args = parser.parse_args(["recall", "test", "--explain"])
        assert args.explain is True

    def test_no_explain_default(self):
        from memos.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["recall", "test"])
        assert args.explain is False


class TestRecallExplainAPI:
    """Test REST API explain parameter."""

    def test_api_explain_param(self):
        """API recall endpoint accepts explain field."""
        from fastapi.testclient import TestClient

        from memos.api import create_fastapi_app
        from memos.core import MemOS

        mem = MemOS(backend="memory")
        mem.learn("Test memory for explain", tags=["test"], importance=0.7)

        client = TestClient(create_fastapi_app(memos=mem))
        resp = client.post(
            "/api/v1/recall",
            json={
                "query": "test",
                "top_k": 5,
                "explain": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["results"]) > 0
        for r in data["results"]:
            assert "score_breakdown" in r
            bd = r["score_breakdown"]
            assert "semantic" in bd
            assert "keyword" in bd
            assert "importance" in bd
            assert "recency" in bd
            assert "tag_bonus" in bd
            assert "total" in bd
            assert "backend" in bd

    def test_api_no_explain_default(self):
        """Without explain, no breakdown in response."""
        from fastapi.testclient import TestClient

        from memos.api import create_fastapi_app
        from memos.core import MemOS

        mem = MemOS(backend="memory")
        mem.learn("Another test memory", tags=["test"])

        client = TestClient(create_fastapi_app(memos=mem))
        resp = client.post(
            "/api/v1/recall",
            json={
                "query": "test",
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert "score_breakdown" not in r
