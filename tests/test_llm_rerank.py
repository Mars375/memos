"""Tests for LLM reranking (Task 2.4) and recall API rerank parameter."""

from __future__ import annotations

from types import SimpleNamespace

from memos.retrieval import HybridRetriever

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(idx: int, content: str, score: float = 0.5) -> SimpleNamespace:
    """Create a mock RecallResult-like object."""
    return SimpleNamespace(
        item=SimpleNamespace(id=f"c-{idx}", content=content, tags=[]),
        score=score,
        match_reason="semantic",
    )


class MockLLMClient:
    """Mock LLM client with a configurable response."""

    def __init__(self, response: str = "[0, 1, 2]"):
        self.response = response
        self.last_prompt: str | None = None

    def chat(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


class FailingLLMClient:
    """LLM client that always raises."""

    def chat(self, prompt: str) -> str:
        raise RuntimeError("LLM unavailable")


# ---------------------------------------------------------------------------
# llm_rerank — basic behavior
# ---------------------------------------------------------------------------


def test_llm_rerank_no_client_returns_as_is() -> None:
    retriever = HybridRetriever()
    candidates = [_make_candidate(i, f"doc {i}") for i in range(5)]

    result = retriever.llm_rerank("test query", candidates, top_k=3)

    # Should return first 3 candidates unchanged
    assert len(result) == 3
    assert result[0].item.id == "c-0"
    assert result[1].item.id == "c-1"
    assert result[2].item.id == "c-2"


def test_llm_rerank_empty_candidates() -> None:
    retriever = HybridRetriever()
    assert retriever.llm_rerank("query", [], top_k=5) == []


def test_llm_rerank_with_mock_llm_reorders() -> None:
    retriever = HybridRetriever()

    candidates = [
        _make_candidate(0, "Document about cats", score=0.9),
        _make_candidate(1, "Document about dogs", score=0.8),
        _make_candidate(2, "Document about birds", score=0.7),
    ]

    # LLM says: birds first, then cats, then dogs
    mock = MockLLMClient(response="[2, 0, 1]")
    result = retriever.llm_rerank("birds", candidates, top_k=3, llm_client=mock)

    assert len(result) == 3
    assert result[0].item.id == "c-2"  # birds
    assert result[1].item.id == "c-0"  # cats
    assert result[2].item.id == "c-1"  # dogs


def test_llm_rerank_top_k_limits_output() -> None:
    retriever = HybridRetriever()
    candidates = [_make_candidate(i, f"doc {i}") for i in range(5)]

    mock = MockLLMClient(response="[3, 1, 4, 0, 2]")
    result = retriever.llm_rerank("query", candidates, top_k=2, llm_client=mock)

    assert len(result) == 2
    assert result[0].item.id == "c-3"
    assert result[1].item.id == "c-1"


def test_llm_rerank_appends_unmentioned_candidates() -> None:
    retriever = HybridRetriever()
    candidates = [_make_candidate(i, f"doc {i}") for i in range(4)]

    # LLM only mentions indices 2 and 0
    mock = MockLLMClient(response="[2, 0]")
    result = retriever.llm_rerank("query", candidates, top_k=10, llm_client=mock)

    # Should still include all 4 candidates (2, 0 first, then 1, 3)
    assert len(result) == 4
    assert result[0].item.id == "c-2"
    assert result[1].item.id == "c-0"
    # Remaining in original order
    ids = [r.item.id for r in result[2:]]
    assert "c-1" in ids
    assert "c-3" in ids


def test_llm_rerank_failing_llm_falls_back() -> None:
    retriever = HybridRetriever()
    candidates = [_make_candidate(i, f"doc {i}") for i in range(3)]

    result = retriever.llm_rerank(
        "query", candidates, top_k=3, llm_client=FailingLLMClient()
    )

    # Should fall back to original order
    assert len(result) == 3
    assert result[0].item.id == "c-0"


def test_llm_rerank_builds_correct_prompt() -> None:
    retriever = HybridRetriever()
    candidates = [
        _make_candidate(0, "short doc"),
        _make_candidate(1, "another doc"),
    ]

    mock = MockLLMClient(response="[0, 1]")
    retriever.llm_rerank("my query", candidates, top_k=2, llm_client=mock)

    assert mock.last_prompt is not None
    assert "my query" in mock.last_prompt
    assert "[0]" in mock.last_prompt
    assert "short doc" in mock.last_prompt
    assert "[1]" in mock.last_prompt


# ---------------------------------------------------------------------------
# _parse_llm_ordering
# ---------------------------------------------------------------------------


def test_parse_llm_ordering_json_array() -> None:
    result = HybridRetriever._parse_llm_ordering("[2, 0, 3, 1]", max_idx=4)
    assert result == [2, 0, 3, 1]


def test_parse_llm_ordering_json_in_text() -> None:
    result = HybridRetriever._parse_llm_ordering(
        "Here is my ranking: [1, 3, 0, 2] for the query.", max_idx=4
    )
    assert result == [1, 3, 0, 2]


def test_parse_llm_ordering_fallback_integers() -> None:
    result = HybridRetriever._parse_llm_ordering(
        "2 0 3 1", max_idx=4
    )
    assert result == [2, 0, 3, 1]


def test_parse_llm_ordering_invalid_returns_empty() -> None:
    # All indices out of range
    result = HybridRetriever._parse_llm_ordering("[99, 100]", max_idx=3)
    assert result == []


def test_parse_llm_ordering_empty_response() -> None:
    result = HybridRetriever._parse_llm_ordering("", max_idx=5)
    assert result == []


def test_parse_llm_ordering_deduplicates() -> None:
    result = HybridRetriever._parse_llm_ordering("1 1 0 0 2", max_idx=3)
    assert result == [1, 0, 2]


# ---------------------------------------------------------------------------
# API integration test (recall with rerank=true)
# ---------------------------------------------------------------------------


def test_recall_api_rerank_parameter_accepted(tmp_path) -> None:
    """Test that RecallRequest accepts rerank field."""
    from memos.api.schemas import RecallRequest

    req = RecallRequest(query="test", rerank=True)
    assert req.rerank is True

    req2 = RecallRequest(query="test")
    assert req2.rerank is False
