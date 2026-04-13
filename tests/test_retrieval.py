"""Tests for HybridRetriever and BM25 (P20)."""

from __future__ import annotations

import pytest

from memos.retrieval import BM25, HybridRetriever, _normalize, _tokenize, keyword_score

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def test_tokenize_basic() -> None:
    tokens = _tokenize("Hello World, this is a test!")
    assert "hello" in tokens
    assert "world" in tokens
    assert "test" in tokens


def test_tokenize_strips_short_words() -> None:
    # Single-char words are excluded (min length 2)
    tokens = _tokenize("I am a developer")
    assert "i" not in tokens
    assert "a" not in tokens
    assert "am" in tokens
    assert "developer" in tokens


def test_tokenize_empty() -> None:
    assert _tokenize("") == []


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


def test_normalize_all_same() -> None:
    result = _normalize([3.0, 3.0, 3.0])
    assert all(v == 0.5 for v in result)


def test_normalize_range() -> None:
    result = _normalize([0.0, 5.0, 10.0])
    assert result[0] == pytest.approx(0.0)
    assert result[1] == pytest.approx(0.5)
    assert result[2] == pytest.approx(1.0)


def test_normalize_empty() -> None:
    assert _normalize([]) == []


# ---------------------------------------------------------------------------
# keyword_score
# ---------------------------------------------------------------------------


def test_keyword_score_full_match() -> None:
    score = keyword_score("docker deployment pipeline", "docker deployment pipeline ci cd")
    assert score == pytest.approx(1.0)


def test_keyword_score_partial_match() -> None:
    score = keyword_score("docker kubernetes", "docker container")
    assert 0.0 < score < 1.0


def test_keyword_score_no_match() -> None:
    score = keyword_score("quantum physics", "docker deployment pipeline")
    assert score == 0.0


def test_keyword_score_empty_query() -> None:
    assert keyword_score("", "some content") == 0.0


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------


@pytest.fixture()
def corpus() -> list[str]:
    return [
        "Docker deployment pipeline for kubernetes and helm charts",
        "Python FastAPI backend REST endpoint authentication",
        "React Vue frontend component UI tailwind CSS",
        "Docker container image build registry push",
        "Authentication JWT token OAuth session security",
    ]


def test_bm25_scores_length(corpus: list[str]) -> None:
    bm25 = BM25(corpus)
    scores = bm25.scores("docker")
    assert len(scores) == len(corpus)


def test_bm25_docker_scores_docker_docs_higher(corpus: list[str]) -> None:
    bm25 = BM25(corpus)
    scores = bm25.scores("docker deployment")
    # Docs 0 and 3 mention docker — should score higher than doc 1 (python only)
    assert scores[0] > scores[1]
    assert scores[3] > scores[1]


def test_bm25_auth_scores_auth_docs_higher(corpus: list[str]) -> None:
    bm25 = BM25(corpus)
    scores = bm25.scores("authentication token")
    assert scores[1] > scores[0]
    assert scores[4] > scores[0]


def test_bm25_no_match_returns_zero(corpus: list[str]) -> None:
    bm25 = BM25(corpus)
    scores = bm25.scores("zxqwerty123")
    assert all(s == 0.0 for s in scores)


def test_bm25_empty_corpus() -> None:
    bm25 = BM25([])
    assert bm25.scores("query") == []


def test_bm25_single_doc() -> None:
    bm25 = BM25(["hello world"])
    scores = bm25.scores("hello")
    assert len(scores) == 1
    assert scores[0] > 0.0


# ---------------------------------------------------------------------------
# HybridRetriever
# ---------------------------------------------------------------------------


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


def test_hybridretriever_invalid_alpha() -> None:
    with pytest.raises(ValueError):
        HybridRetriever(alpha=1.5)
    with pytest.raises(ValueError):
        HybridRetriever(alpha=-0.1)


def test_hybridretriever_rerank_empty() -> None:
    retriever = HybridRetriever()
    assert retriever.rerank("query", []) == []


def test_hybridretriever_rerank_single() -> None:
    retriever = HybridRetriever()
    candidates = [_FakeRecallResult("docker deployment pipeline", score=0.8, id="a")]
    result = retriever.rerank("docker", candidates)
    assert len(result) == 1


def test_hybridretriever_rerank_orders_by_relevance() -> None:
    """Hybrid reranker boosts docs that match both semantically and by keyword."""
    # alpha=0.2 → BM25 dominates (weight 0.8)
    retriever = HybridRetriever(alpha=0.2)
    candidates = [
        _FakeRecallResult("completely unrelated music symphony orchestra", score=0.9, id="a"),
        _FakeRecallResult("docker deployment pipeline kubernetes helm", score=0.5, id="b"),
    ]
    result = retriever.rerank("docker deployment", candidates)
    # Doc b scores much higher on BM25; with alpha=0.2, BM25 dominates → b first
    assert result[0].item.id == "b"


def test_hybridretriever_rerank_preserves_count() -> None:
    retriever = HybridRetriever()
    candidates = [_FakeRecallResult(f"content about topic {i}", score=float(i) / 10, id=str(i)) for i in range(10)]
    result = retriever.rerank("topic", candidates)
    assert len(result) == 10


def test_hybridretriever_keyword_recall_returns_top_k() -> None:
    retriever = HybridRetriever()
    candidates = [
        _FakeRecallResult("docker deployment pipeline", score=0.0, id="a"),
        _FakeRecallResult("react frontend component", score=0.0, id="b"),
        _FakeRecallResult("docker kubernetes helm", score=0.0, id="c"),
        _FakeRecallResult("python fastapi backend", score=0.0, id="d"),
    ]
    result = retriever.keyword_recall("docker", candidates, top=2)
    assert len(result) == 2
    ids = {r.item.id for r in result}
    assert "a" in ids or "c" in ids  # docker docs should win


def test_hybridretriever_keyword_recall_min_score() -> None:
    retriever = HybridRetriever()
    candidates = [
        _FakeRecallResult("completely irrelevant text here", score=0.0, id="a"),
        _FakeRecallResult("docker deployment pipeline", score=0.0, id="b"),
    ]
    result = retriever.keyword_recall("docker", candidates, top=5, min_score=0.1)
    ids = {r.item.id for r in result}
    assert "b" in ids
    assert "a" not in ids


def test_hybridretriever_alpha_zero_pure_bm25() -> None:
    """alpha=0 means scores are purely BM25."""
    retriever = HybridRetriever(alpha=0.0)
    candidates = [
        _FakeRecallResult("docker deployment kubernetes", score=0.99, id="a"),
        _FakeRecallResult("docker docker docker helm", score=0.01, id="b"),
    ]
    result = retriever.rerank("docker", candidates)
    # Doc b has higher term frequency → should rank first with alpha=0
    assert result[0].item.id == "b"


def test_hybridretriever_alpha_one_pure_semantic() -> None:
    """alpha=1 means scores are purely semantic (original order preserved if BM25 normalized equally)."""
    retriever = HybridRetriever(alpha=1.0)
    candidates = [
        _FakeRecallResult("unrelated text", score=0.9, id="a"),
        _FakeRecallResult("also unrelated", score=0.1, id="b"),
    ]
    result = retriever.rerank("query", candidates)
    # With alpha=1, semantic score dominates → a should remain first
    assert result[0].item.id == "a"
