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


# ---------------------------------------------------------------------------
# Temporal proximity boosting in RetrievalEngine
# ---------------------------------------------------------------------------


class TestTemporalProximityConstants:
    """Tests for temporal proximity weight and window constants."""

    def test_weight_value(self) -> None:
        from memos._constants import TEMPORAL_PROXIMITY_WEIGHT

        assert TEMPORAL_PROXIMITY_WEIGHT == 0.05

    def test_window_value(self) -> None:
        from memos._constants import TEMPORAL_PROXIMITY_WINDOW

        assert TEMPORAL_PROXIMITY_WINDOW == 3600


class TestTemporalProximityScoring:
    """Tests for RetrievalEngine._temporal_proximity method."""

    def test_recent_memory_gets_boost(self) -> None:
        """Memory created seconds ago should get a positive proximity score."""
        import time

        from memos.retrieval.engine import RetrievalEngine

        now = time.time()
        created = now - 10  # 10 seconds ago
        prox = RetrievalEngine._temporal_proximity(created, now=now)
        assert prox > 0.0
        # Should be close to full weight: (1 - 10/3600) * 0.05
        assert prox == pytest.approx(0.05 * (1 - 10 / 3600), abs=0.001)

    def test_very_old_memory_gets_no_boost(self) -> None:
        """Memory created 24 hours ago should get 0.0 proximity."""
        import time

        from memos.retrieval.engine import RetrievalEngine

        now = time.time()
        created = now - 86400  # 1 day ago — well outside 1-hour window
        prox = RetrievalEngine._temporal_proximity(created, now=now)
        assert prox == 0.0

    def test_half_window_returns_half_weight(self) -> None:
        """Memory at exactly half the window should get ~half the max weight."""
        import time

        from memos._constants import TEMPORAL_PROXIMITY_WEIGHT, TEMPORAL_PROXIMITY_WINDOW
        from memos.retrieval.engine import RetrievalEngine

        now = time.time()
        created = now - TEMPORAL_PROXIMITY_WINDOW / 2  # 30 minutes ago
        prox = RetrievalEngine._temporal_proximity(created, now=now)
        expected = 0.5 * TEMPORAL_PROXIMITY_WEIGHT
        assert prox == pytest.approx(expected)

    def test_score_breakdown_includes_temporal_proximity(self) -> None:
        """Verify ScoreBreakdown has a temporal_proximity field."""
        from memos.models import ScoreBreakdown

        sb = ScoreBreakdown(temporal_proximity=0.025, total=0.5)
        assert sb.temporal_proximity == 0.025
        d = sb.to_dict()
        assert "temporal_proximity" in d
        assert d["temporal_proximity"] == 0.025


# ---------------------------------------------------------------------------
# Targeted exception handling — engine.py
# ---------------------------------------------------------------------------


class _CrashingEmbedder:
    """Embedder that raises a specific exception on encode()."""

    def __init__(self, exc: type[BaseException]) -> None:
        self._exc = exc

    def encode(self, text: str):
        raise self._exc("boom")

    @property
    def model_name(self) -> str:
        return "crash-test"


class _WorkingEmbedder:
    """Embedder that returns a fixed vector."""

    def encode(self, text: str):
        return [1.0, 0.0, 0.0]

    @property
    def model_name(self) -> str:
        return "test-model"


class TestEngineEmbedderFallback:
    """Verify local embedder failures fall through gracefully."""

    @pytest.fixture()
    def engine_no_store(self):
        from memos.retrieval.engine import RetrievalEngine
        from memos.storage.memory_backend import InMemoryBackend

        return RetrievalEngine(
            store=InMemoryBackend(),
            embedder=_CrashingEmbedder(RuntimeError),
            embed_host="http://127.0.0.1:0",  # unreachable
        )

    def test_runtime_error_falls_through(self, engine_no_store) -> None:
        """RuntimeError from local embedder should be caught, result is None."""
        vec = engine_no_store._get_embedding("test")
        assert vec is None  # both embedder and Ollama fail gracefully

    def test_os_error_caught(self) -> None:
        from memos.retrieval.engine import RetrievalEngine
        from memos.storage.memory_backend import InMemoryBackend

        eng = RetrievalEngine(
            store=InMemoryBackend(),
            embedder=_CrashingEmbedder(OSError),
            embed_host="http://127.0.0.1:0",
        )
        assert eng._get_embedding("test") is None

    def test_import_error_caught(self) -> None:
        from memos.retrieval.engine import RetrievalEngine
        from memos.storage.memory_backend import InMemoryBackend

        eng = RetrievalEngine(
            store=InMemoryBackend(),
            embedder=_CrashingEmbedder(ImportError),
            embed_host="http://127.0.0.1:0",
        )
        assert eng._get_embedding("test") is None

    def test_unexpected_exception_propagates(self) -> None:
        """Non-targeted exceptions (e.g. KeyboardInterrupt) must NOT be swallowed."""
        from memos.retrieval.engine import RetrievalEngine
        from memos.storage.memory_backend import InMemoryBackend

        eng = RetrievalEngine(
            store=InMemoryBackend(),
            embedder=_CrashingEmbedder(KeyboardInterrupt),
            embed_host="http://127.0.0.1:0",
        )
        with pytest.raises(KeyboardInterrupt):
            eng._get_embedding("test")

    def test_working_embedder_returns_vector(self) -> None:
        from memos.retrieval.engine import RetrievalEngine
        from memos.storage.memory_backend import InMemoryBackend

        eng = RetrievalEngine(
            store=InMemoryBackend(),
            embedder=_WorkingEmbedder(),
            embed_host="http://127.0.0.1:0",
        )
        vec = eng._get_embedding("test")
        assert vec == [1.0, 0.0, 0.0]


class TestEngineOllamaFallback:
    """Verify Ollama HTTP failures fall through gracefully."""

    def test_connection_refused_keyword_only(self) -> None:
        """When no embedder and Ollama is unreachable, search falls back to keyword-only."""
        from memos.retrieval.engine import RetrievalEngine
        from memos.storage.memory_backend import InMemoryBackend

        eng = RetrievalEngine(
            store=InMemoryBackend(),
            embed_host="http://127.0.0.1:0",  # nothing there
        )
        results = eng.search("test query", top=5)
        assert isinstance(results, list)  # no crash, returns empty


# ---------------------------------------------------------------------------
# Targeted exception handling — hybrid.py llm_rerank
# ---------------------------------------------------------------------------


class _CrashingLLMClient:
    """LLM client that raises a specific exception on chat()."""

    def __init__(self, exc: type[BaseException]) -> None:
        self._exc = exc

    def chat(self, prompt: str) -> str:
        raise self._exc("llm boom")


class TestLLMRerankFallback:
    """Verify LLM client failures in llm_rerank fall through gracefully."""

    def test_connection_error_returns_original_order(self) -> None:
        retriever = HybridRetriever()
        candidates = [_FakeRecallResult("docker deployment", score=0.8)]
        result = retriever.llm_rerank("docker", candidates, llm_client=_CrashingLLMClient(ConnectionError))
        assert result == candidates[:5]

    def test_timeout_error_returns_original_order(self) -> None:
        retriever = HybridRetriever()
        candidates = [_FakeRecallResult("docker deployment", score=0.8)]
        result = retriever.llm_rerank("docker", candidates, llm_client=_CrashingLLMClient(TimeoutError))
        assert result == candidates[:5]

    def test_runtime_error_returns_original_order(self) -> None:
        retriever = HybridRetriever()
        candidates = [_FakeRecallResult("docker deployment", score=0.8)]
        result = retriever.llm_rerank("docker", candidates, llm_client=_CrashingLLMClient(RuntimeError))
        assert result == candidates[:5]

    def test_attribute_error_returns_original_order(self) -> None:
        """AttributeError (e.g. client missing .chat) should be caught."""
        retriever = HybridRetriever()
        candidates = [_FakeRecallResult("docker deployment", score=0.8)]
        result = retriever.llm_rerank("docker", candidates, llm_client=_CrashingLLMClient(AttributeError))
        assert result == candidates[:5]

    def test_unexpected_exception_propagates(self) -> None:
        """Non-targeted exceptions (e.g. KeyboardInterrupt) must NOT be swallowed."""
        retriever = HybridRetriever()
        candidates = [_FakeRecallResult("docker deployment", score=0.8)]
        with pytest.raises(KeyboardInterrupt):
            retriever.llm_rerank("docker", candidates, llm_client=_CrashingLLMClient(KeyboardInterrupt))

    def test_no_llm_client_passes_through(self) -> None:
        """Without an LLM client, candidates are returned as-is."""
        retriever = HybridRetriever()
        candidates = [_FakeRecallResult("docker deployment", score=0.8)]
        result = retriever.llm_rerank("docker", candidates, llm_client=None, top_k=3)
        assert result == candidates[:3]
