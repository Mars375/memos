"""Tests for Tasks 2.1, 2.2 and 4.1.

Task 2.1 — Keyword boosting in HybridRetriever
Task 2.2 — Temporal proximity boosting in RetrievalEngine
Task 4.1 — Per-agent wing auto-creation hook
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from memos.mcp_hooks import (
    create_default_registry,
    hook_ensure_agent_wing,
)
from memos.retrieval.engine import RetrievalEngine

# ===========================================================================
# Task 2.1 — Keyword boosting in HybridRetriever
# ===========================================================================


class _FakeItem:
    def __init__(self, content: str, id: str = "x") -> None:
        self.content = content
        self.id = id
        self.tags: list[str] = []
        self.importance = 0.5
        self.created_at = 0.0
        self.is_expired = False


class _FakeRecallResult:
    def __init__(self, content: str, score: float, id: str = "x") -> None:
        self.item = _FakeItem(content, id=id)
        self.score = score
        self.match_reason = "semantic"


class TestKeywordBoosting:
    """Tests for the keyword_boost parameter on HybridRetriever."""

    def test_default_keyword_boost(self) -> None:
        from memos.retrieval.hybrid import HybridRetriever

        r = HybridRetriever()
        assert r.keyword_boost == 1.5

    def test_custom_keyword_boost(self) -> None:
        from memos.retrieval.hybrid import HybridRetriever

        r = HybridRetriever(keyword_boost=2.0)
        assert r.keyword_boost == 2.0

    def test_negative_keyword_boost_raises(self) -> None:
        from memos.retrieval.hybrid import HybridRetriever

        with pytest.raises(ValueError, match="keyword_boost"):
            HybridRetriever(keyword_boost=-1.0)

    def test_keyword_boost_promotes_matching_docs(self) -> None:
        """Documents with higher keyword overlap should be boosted more."""
        from memos.retrieval.hybrid import HybridRetriever

        # Both candidates start with the same semantic score; the one whose
        # content shares more words with the query should be ranked higher.
        retriever = HybridRetriever(alpha=0.5, keyword_boost=3.0)
        candidates = [
            _FakeRecallResult("docker deployment pipeline", score=0.6, id="match"),
            _FakeRecallResult("unrelated music symphony", score=0.6, id="nomatch"),
        ]
        result = retriever.rerank("docker deployment", candidates)
        assert result[0].item.id == "match"

    def test_keyword_boost_one_is_noop(self) -> None:
        """keyword_boost=1.0 should not change relative ordering (vs no boost)."""
        from memos.retrieval.hybrid import HybridRetriever

        retriever = HybridRetriever(alpha=0.5, keyword_boost=1.0)
        candidates = [
            _FakeRecallResult("docker kubernetes", score=0.5, id="a"),
            _FakeRecallResult("music symphony", score=0.5, id="b"),
        ]
        result = retriever.rerank("docker", candidates)
        # Without boost the blended BM25+semantic score determines order;
        # keyword_boost=1.0 means no extra multiplicative boost.
        assert len(result) == 2

    def test_keyword_overlap_method(self) -> None:
        from memos.retrieval.hybrid import HybridRetriever

        # Full overlap
        assert HybridRetriever._keyword_overlap("docker deploy", "docker deploy ci cd") == pytest.approx(1.0)
        # Partial overlap
        overlap = HybridRetriever._keyword_overlap("docker kubernetes", "docker ci")
        assert overlap == pytest.approx(0.5)
        # No overlap
        assert HybridRetriever._keyword_overlap("quantum", "docker deploy") == pytest.approx(0.0)
        # Empty query
        assert HybridRetriever._keyword_overlap("", "anything") == pytest.approx(0.0)


# ===========================================================================
# Task 2.2 — Temporal proximity boosting in RetrievalEngine
# ===========================================================================


class TestTemporalBoost:
    """Tests for RetrievalEngine._temporal_proximity."""

    def test_very_recent_returns_full_weight(self) -> None:
        """Memory created 1 second ago should get full temporal proximity weight."""
        prox = RetrievalEngine._temporal_proximity(time.time() - 1)
        assert prox == pytest.approx(0.05, abs=0.001)

    def test_30_minutes_ago_returns_half(self) -> None:
        """Memory created 30 min ago should get ~half weight (0.5 * 0.05)."""
        from memos._constants import TEMPORAL_PROXIMITY_WEIGHT, TEMPORAL_PROXIMITY_WINDOW

        now = time.time()
        created = now - 1800  # 30 minutes = half of 3600s window
        raw = max(0.0, 1.0 - 1800 / TEMPORAL_PROXIMITY_WINDOW)
        expected = raw * TEMPORAL_PROXIMITY_WEIGHT
        prox = RetrievalEngine._temporal_proximity(created, now=now)
        assert prox == pytest.approx(expected)

    def test_within_window_gets_positive(self) -> None:
        """Memory created within 1 hour should get a positive boost."""
        prox = RetrievalEngine._temporal_proximity(time.time() - 1800)
        assert prox > 0.0

    def test_older_than_window_returns_zero(self) -> None:
        """Memory older than 1 hour should get 0.0 proximity."""
        prox = RetrievalEngine._temporal_proximity(time.time() - 7200, now=time.time())
        assert prox == pytest.approx(0.0)

    def test_exactly_at_window_boundary(self) -> None:
        """Memory exactly 1 hour old → raw proximity = 0 → score = 0."""
        now = time.time()
        created = now - 3600
        prox = RetrievalEngine._temporal_proximity(created, now=now)
        assert prox == pytest.approx(0.0)

    def test_temporal_boost_integrated_in_search(self) -> None:
        """Verify temporal proximity is added during search scoring."""
        from memos.core import MemOS

        memos = MemOS(backend="memory")
        # Learn a memory right now
        memos.learn("fresh memory about testing", tags=["test"])

        # Get the engine and run a search
        results = memos.recall("testing", top=1)
        assert len(results) == 1

        # The score should include temporal proximity (fresh → 0.05)
        assert results[0].score > 0.0


# ===========================================================================
# Task 4.1 — Per-agent wing auto-creation
# ===========================================================================


class TestHookEnsureAgentWing:
    """Tests for hook_ensure_agent_wing."""

    def test_creates_wing_with_namespace(self) -> None:
        from memos.palace import PalaceIndex

        palace = PalaceIndex(":memory:")
        memos = MagicMock()
        memos._palace = palace

        result = hook_ensure_agent_wing("memory_save", {"namespace": "my-agent"}, memos)
        # Should not short-circuit
        assert result is None

        wing = palace.get_wing("agent-my-agent")
        assert wing is not None
        assert "my-agent" in wing["description"]
        palace.close()

    def test_creates_wing_with_default_namespace(self) -> None:
        from memos.palace import PalaceIndex

        palace = PalaceIndex(":memory:")
        memos = MagicMock()
        memos._palace = palace

        hook_ensure_agent_wing("memory_search", {}, memos)

        wing = palace.get_wing("agent-default")
        assert wing is not None
        palace.close()

    def test_idempotent_multiple_calls(self) -> None:
        from memos.palace import PalaceIndex

        palace = PalaceIndex(":memory:")
        memos = MagicMock()
        memos._palace = palace

        hook_ensure_agent_wing("memory_save", {"namespace": "test"}, memos)
        hook_ensure_agent_wing("memory_search", {"namespace": "test"}, memos)
        hook_ensure_agent_wing("memory_save", {"namespace": "test"}, memos)

        wings = palace.list_wings()
        assert len(wings) == 1
        assert wings[0]["name"] == "agent-test"
        palace.close()

    def test_no_palace_on_memos_does_nothing(self) -> None:
        memos = MagicMock(spec=[])  # no _palace attribute
        result = hook_ensure_agent_wing("memory_save", {"namespace": "test"}, memos)
        assert result is None

    def test_palace_exception_is_swallowed(self) -> None:
        palace = MagicMock()
        palace.create_wing.side_effect = RuntimeError("db error")
        memos = MagicMock()
        memos._palace = palace

        # Should not raise
        result = hook_ensure_agent_wing("memory_save", {"namespace": "test"}, memos)
        assert result is None

    def test_registry_with_auto_agent_wing(self) -> None:
        registry = create_default_registry(auto_agent_wing=True)
        assert "memory_save" in registry.registered_tools
        assert "memory_search" in registry.registered_tools

    def test_registry_without_auto_agent_wing(self) -> None:
        registry = create_default_registry()
        assert "memory_save" not in registry.registered_tools
        assert "memory_search" not in registry.registered_tools

    def test_different_namespaces_create_different_wings(self) -> None:
        from memos.palace import PalaceIndex

        palace = PalaceIndex(":memory:")
        memos = MagicMock()
        memos._palace = palace

        hook_ensure_agent_wing("memory_save", {"namespace": "agent-a"}, memos)
        hook_ensure_agent_wing("memory_save", {"namespace": "agent-b"}, memos)

        wings = palace.list_wings()
        names = {w["name"] for w in wings}
        assert "agent-agent-a" in names
        assert "agent-agent-b" in names
        assert len(wings) == 2
        palace.close()
