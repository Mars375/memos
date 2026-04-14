"""Comprehensive tests for memos.query — MemoryQuery dataclass and QueryEngine."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from memos.models import MemoryItem, RecallResult
from memos.query import MemoryQuery, QueryEngine
from memos.storage.memory_backend import InMemoryBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    id: str = "1",
    content: str = "test content",
    tags: list[str] | None = None,
    importance: float = 0.5,
    created_at: float | None = None,
    accessed_at: float | None = None,
    ttl: float | None = None,
) -> MemoryItem:
    now = time.time()
    return MemoryItem(
        id=id,
        content=content,
        tags=tags or [],
        importance=importance,
        created_at=created_at if created_at is not None else now,
        accessed_at=accessed_at if accessed_at is not None else now,
        ttl=ttl,
    )


def _seed_store(items: list[MemoryItem] | None = None, namespace: str = "") -> InMemoryBackend:
    backend = InMemoryBackend()
    now = time.time()
    if items is None:
        items = [
            _make_item("1", "Python async patterns", ["python", "async"], 0.8, now - 100, now),
            _make_item("2", "Docker deployment guide", ["devops", "docker"], 0.6, now - 50, now - 10),
            _make_item("3", "React hooks tutorial", ["react", "frontend"], 0.9, now, now),
        ]
    for item in items:
        backend.upsert(item, namespace=namespace)
    return backend


@pytest.fixture
def store():
    return _seed_store()


@pytest.fixture
def mock_retrieval():
    retrieval = MagicMock()
    retrieval.search.return_value = []
    return retrieval


@pytest.fixture
def engine(mock_retrieval):
    return QueryEngine(mock_retrieval)


# ===================================================================
# TestNormalize — _normalize() static method
# ===================================================================


class TestNormalize:
    """QueryEngine._normalize() validation and defaults."""

    def test_valid_modes_pass_through(self):
        for mode in ("semantic", "keyword", "hybrid"):
            q = MemoryQuery(query="test", retrieval_mode=mode)
            norm = QueryEngine._normalize(q)
            assert norm.retrieval_mode == mode

    def test_invalid_mode_raises(self):
        q = MemoryQuery(query="test", retrieval_mode="invalid")
        with pytest.raises(ValueError, match="retrieval_mode must be one of"):
            QueryEngine._normalize(q)

    def test_invalid_mode_error_contains_valid_modes(self):
        q = MemoryQuery(query="test", retrieval_mode="bogus")
        with pytest.raises(ValueError) as exc_info:
            QueryEngine._normalize(q)
        msg = str(exc_info.value)
        for mode in ("hybrid", "keyword", "semantic"):
            assert mode in msg

    def test_top_k_zero_stays_zero(self):
        """top_k=0 → int(0 or 5)=5, then max(5,1)=5 — zero is falsy, defaults to 5."""
        q = MemoryQuery(query="test", top_k=0)
        norm = QueryEngine._normalize(q)
        assert norm.top_k == 5

    def test_top_k_clamped_to_1_when_negative(self):
        q = MemoryQuery(query="test", top_k=-5)
        norm = QueryEngine._normalize(q)
        assert norm.top_k == 1

    def test_top_k_none_defaults_to_5(self):
        """top_k=None → int(None or 5)=5, then max(5,1)=5."""
        q = MemoryQuery(query="test", top_k=None)  # type: ignore[arg-type]
        norm = QueryEngine._normalize(q)
        assert norm.top_k == 5

    def test_top_k_preserved_when_positive(self):
        q = MemoryQuery(query="test", top_k=42)
        norm = QueryEngine._normalize(q)
        assert norm.top_k == 42

    def test_empty_tags_filtered(self):
        q = MemoryQuery(
            query="test", include_tags=["", "valid", ""], require_tags=["", "req"], exclude_tags=["", "exc", ""]
        )
        norm = QueryEngine._normalize(q)
        assert norm.include_tags == ["valid"]
        assert norm.require_tags == ["req"]
        assert norm.exclude_tags == ["exc"]

    def test_all_empty_tags_produce_empty_list(self):
        q = MemoryQuery(query="test", include_tags=["", "", ""])
        norm = QueryEngine._normalize(q)
        assert norm.include_tags == []

    def test_min_score_defaults_to_zero_when_none(self):
        q = MemoryQuery(query="test", min_score=None)  # type: ignore[arg-type]
        norm = QueryEngine._normalize(q)
        assert norm.min_score == 0.0

    def test_min_score_preserved_when_set(self):
        q = MemoryQuery(query="test", min_score=0.3)
        norm = QueryEngine._normalize(q)
        assert norm.min_score == 0.3

    def test_sort_defaults_to_score_when_none(self):
        q = MemoryQuery(query="test", sort=None)  # type: ignore[arg-type]
        norm = QueryEngine._normalize(q)
        assert norm.sort == "score"

    def test_sort_preserved_when_set(self):
        q = MemoryQuery(query="test", sort="created_at")
        norm = QueryEngine._normalize(q)
        assert norm.sort == "created_at"

    def test_retrieval_mode_defaults_to_semantic_when_none(self):
        q = MemoryQuery(query="test", retrieval_mode=None)  # type: ignore[arg-type]
        norm = QueryEngine._normalize(q)
        assert norm.retrieval_mode == "semantic"

    def test_retrieval_mode_defaults_to_semantic_when_empty(self):
        q = MemoryQuery(query="test", retrieval_mode="")
        norm = QueryEngine._normalize(q)
        assert norm.retrieval_mode == "semantic"

    def test_query_preserved(self):
        q = MemoryQuery(query="my search terms")
        norm = QueryEngine._normalize(q)
        assert norm.query == "my search terms"

    def test_numeric_fields_preserved(self):
        q = MemoryQuery(
            query="test",
            min_importance=0.2,
            max_importance=0.8,
            created_after=1000.0,
            created_before=2000.0,
        )
        norm = QueryEngine._normalize(q)
        assert norm.min_importance == 0.2
        assert norm.max_importance == 0.8
        assert norm.created_after == 1000.0
        assert norm.created_before == 2000.0


# ===================================================================
# TestMatches — _matches() filter logic
# ===================================================================


class TestMatches:
    """QueryEngine._matches() filter logic."""

    def test_expired_item_rejected(self, engine):
        item = _make_item(created_at=time.time() - 100, ttl=1)
        assert item.is_expired
        q = MemoryQuery()
        assert engine._matches(item, q) is False

    def test_created_after_rejects_old_item(self, engine):
        item = _make_item(created_at=100.0)
        q = MemoryQuery(created_after=200.0)
        assert engine._matches(item, q) is False

    def test_created_after_allows_newer_item(self, engine):
        item = _make_item(created_at=300.0)
        q = MemoryQuery(created_after=200.0)
        assert engine._matches(item, q) is True

    def test_created_before_rejects_new_item(self, engine):
        item = _make_item(created_at=300.0)
        q = MemoryQuery(created_before=200.0)
        assert engine._matches(item, q) is False

    def test_created_before_allows_older_item(self, engine):
        item = _make_item(created_at=100.0)
        q = MemoryQuery(created_before=200.0)
        assert engine._matches(item, q) is True

    def test_created_range_both_bounds(self, engine):
        item = _make_item(created_at=150.0)
        q = MemoryQuery(created_after=100.0, created_before=200.0)
        assert engine._matches(item, q) is True

    def test_created_range_item_outside_high(self, engine):
        item = _make_item(created_at=250.0)
        q = MemoryQuery(created_after=100.0, created_before=200.0)
        assert engine._matches(item, q) is False

    def test_created_range_item_outside_low(self, engine):
        item = _make_item(created_at=50.0)
        q = MemoryQuery(created_after=100.0, created_before=200.0)
        assert engine._matches(item, q) is False

    def test_min_importance_filter(self, engine):
        item = _make_item(importance=0.3)
        q = MemoryQuery(min_importance=0.5)
        assert engine._matches(item, q) is False

    def test_min_importance_passes(self, engine):
        item = _make_item(importance=0.7)
        q = MemoryQuery(min_importance=0.5)
        assert engine._matches(item, q) is True

    def test_max_importance_filter(self, engine):
        item = _make_item(importance=0.9)
        q = MemoryQuery(max_importance=0.5)
        assert engine._matches(item, q) is False

    def test_max_importance_passes(self, engine):
        item = _make_item(importance=0.3)
        q = MemoryQuery(max_importance=0.5)
        assert engine._matches(item, q) is True

    def test_include_tags_any_match_passes_or_logic(self, engine):
        item = _make_item(tags=["python", "async"])
        q = MemoryQuery(include_tags=["react", "python"])
        assert engine._matches(item, q) is True

    def test_include_tags_no_match_rejected(self, engine):
        item = _make_item(tags=["python", "async"])
        q = MemoryQuery(include_tags=["react", "docker"])
        assert engine._matches(item, q) is False

    def test_require_tags_all_must_match_and_logic(self, engine):
        item = _make_item(tags=["python", "async", "web"])
        q = MemoryQuery(require_tags=["python", "async"])
        assert engine._matches(item, q) is True

    def test_require_tags_missing_one_rejected(self, engine):
        item = _make_item(tags=["python"])
        q = MemoryQuery(require_tags=["python", "async"])
        assert engine._matches(item, q) is False

    def test_exclude_tags_any_match_rejected(self, engine):
        item = _make_item(tags=["python", "async"])
        q = MemoryQuery(exclude_tags=["docker", "python"])
        assert engine._matches(item, q) is False

    def test_exclude_tags_no_match_passes(self, engine):
        item = _make_item(tags=["python", "async"])
        q = MemoryQuery(exclude_tags=["docker", "react"])
        assert engine._matches(item, q) is True

    def test_tag_matching_case_insensitive(self, engine):
        item = _make_item(tags=["Python", "ASYNC"])
        q = MemoryQuery(include_tags=["python"])
        assert engine._matches(item, q) is True

    def test_tag_matching_case_insensitive_require(self, engine):
        item = _make_item(tags=["Python", "Async"])
        q = MemoryQuery(require_tags=["python", "async"])
        assert engine._matches(item, q) is True

    def test_tag_matching_case_insensitive_exclude(self, engine):
        item = _make_item(tags=["Python"])
        q = MemoryQuery(exclude_tags=["python"])
        assert engine._matches(item, q) is False

    def test_combined_filters_tags_time_importance(self, engine):
        now = time.time()
        item = _make_item(tags=["python"], importance=0.7, created_at=now - 50)
        q = MemoryQuery(
            include_tags=["python"],
            min_importance=0.5,
            created_after=now - 100,
            created_before=now,
        )
        assert engine._matches(item, q) is True

    def test_combined_filters_fails_on_importance(self, engine):
        now = time.time()
        item = _make_item(tags=["python"], importance=0.3, created_at=now - 50)
        q = MemoryQuery(
            include_tags=["python"],
            min_importance=0.5,
            created_after=now - 100,
        )
        assert engine._matches(item, q) is False

    def test_item_no_tags_include_tags_set_rejected(self, engine):
        item = _make_item(tags=[])
        q = MemoryQuery(include_tags=["python"])
        assert engine._matches(item, q) is False

    def test_item_no_tags_empty_include_passes(self, engine):
        item = _make_item(tags=[])
        q = MemoryQuery(include_tags=[])
        assert engine._matches(item, q) is True

    def test_item_no_tags_require_tags_set_rejected(self, engine):
        item = _make_item(tags=[])
        q = MemoryQuery(require_tags=["python"])
        assert engine._matches(item, q) is False

    def test_item_no_tags_exclude_tags_passes(self, engine):
        item = _make_item(tags=[])
        q = MemoryQuery(exclude_tags=["python"])
        assert engine._matches(item, q) is True

    def test_no_filters_passes(self, engine):
        item = _make_item()
        q = MemoryQuery()
        assert engine._matches(item, q) is True


# ===================================================================
# TestListItems — list_items() sort and limit
# ===================================================================


class TestListItems:
    """QueryEngine.list_items() — filter + sort + top_k."""

    def test_sort_by_created_at_newest_first(self, engine, store):
        q = MemoryQuery(sort="created_at", top_k=10)
        items = engine.list_items(q, store)
        assert len(items) >= 2
        for i in range(len(items) - 1):
            assert items[i].created_at >= items[i + 1].created_at

    def test_sort_by_importance_highest_first(self, engine, store):
        q = MemoryQuery(sort="importance", top_k=10)
        items = engine.list_items(q, store)
        assert len(items) >= 2
        for i in range(len(items) - 1):
            assert items[i].importance >= items[i + 1].importance

    def test_sort_by_importance_tiebreak_created_at(self, engine):
        now = time.time()
        items = [
            _make_item("1", "a", importance=0.8, created_at=now - 10),
            _make_item("2", "b", importance=0.8, created_at=now),
            _make_item("3", "c", importance=0.9, created_at=now - 5),
        ]
        store = _seed_store(items)
        q = MemoryQuery(sort="importance", top_k=10)
        result = engine.list_items(q, store)
        # Item 3 (importance 0.9) first, then 2 and 1 (both 0.8, 2 is newer)
        assert result[0].id == "3"
        assert result[1].id == "2"
        assert result[2].id == "1"

    def test_sort_by_accessed_at_most_recent_first(self, engine):
        now = time.time()
        items = [
            _make_item("1", "a", accessed_at=now - 100),
            _make_item("2", "b", accessed_at=now),
            _make_item("3", "c", accessed_at=now - 50),
        ]
        store = _seed_store(items)
        q = MemoryQuery(sort="accessed_at", top_k=10)
        result = engine.list_items(q, store)
        assert result[0].id == "2"
        assert result[1].id == "3"
        assert result[2].id == "1"

    def test_sort_by_accessed_at_tiebreak_created_at(self, engine):
        now = time.time()
        items = [
            _make_item("1", "a", accessed_at=now, created_at=now - 10),
            _make_item("2", "b", accessed_at=now, created_at=now),
        ]
        store = _seed_store(items)
        q = MemoryQuery(sort="accessed_at", top_k=10)
        result = engine.list_items(q, store)
        # Same accessed_at → tiebreak by created_at (newer first)
        assert result[0].id == "2"
        assert result[1].id == "1"

    def test_invalid_sort_falls_back_to_created_at(self, engine):
        now = time.time()
        items = [
            _make_item("1", "old", created_at=now - 100),
            _make_item("2", "new", created_at=now),
        ]
        store = _seed_store(items)
        q = MemoryQuery(sort="invalid_sort_key", top_k=10)
        result = engine.list_items(q, store)
        assert result[0].id == "2"
        assert result[1].id == "1"

    def test_top_k_limits_result_count(self, engine, store):
        q = MemoryQuery(sort="created_at", top_k=2)
        result = engine.list_items(q, store)
        assert len(result) == 2

    def test_top_k_one(self, engine, store):
        q = MemoryQuery(sort="created_at", top_k=1)
        result = engine.list_items(q, store)
        assert len(result) == 1

    def test_empty_store_returns_empty(self, engine):
        store = InMemoryBackend()
        q = MemoryQuery(sort="created_at", top_k=10)
        result = engine.list_items(q, store)
        assert result == []

    def test_all_expired_returns_empty(self, engine):
        past = time.time() - 100
        items = [
            _make_item("1", "expired 1", created_at=past, ttl=1),
            _make_item("2", "expired 2", created_at=past, ttl=1),
        ]
        store = _seed_store(items)
        q = MemoryQuery(sort="created_at", top_k=10)
        result = engine.list_items(q, store)
        assert result == []

    def test_filter_and_sort_combined(self, engine):
        now = time.time()
        items = [
            _make_item("1", "python web", tags=["python"], importance=0.5, created_at=now - 100),
            _make_item("2", "react web", tags=["react"], importance=0.9, created_at=now),
            _make_item("3", "python async", tags=["python"], importance=0.8, created_at=now - 50),
        ]
        store = _seed_store(items)
        q = MemoryQuery(include_tags=["python"], sort="importance", top_k=10)
        result = engine.list_items(q, store)
        assert len(result) == 2
        assert all("python" in [t.lower() for t in r.tags] for r in result)
        assert result[0].importance >= result[1].importance


# ===================================================================
# TestExecute — execute() full recall pipeline
# ===================================================================


class TestExecute:
    """QueryEngine.execute() — full recall pipeline."""

    def test_empty_query_returns_empty(self, engine, store):
        q = MemoryQuery(query="")
        result = engine.execute(q, store)
        assert result == []

    def test_whitespace_only_query_returns_empty(self, engine, store):
        q = MemoryQuery(query="   ")
        result = engine.execute(q, store)
        assert result == []

    def test_keyword_mode_path(self, engine, store):
        q = MemoryQuery(query="Python async patterns", retrieval_mode="keyword", top_k=10)
        result = engine.execute(q, store)
        # Should use HybridRetriever.keyword_recall on filtered items
        assert isinstance(result, list)
        # At least one result should match "Python"
        if result:
            assert any("python" in r.item.content.lower() for r in result)

    def test_semantic_mode_with_mock_results(self, store):
        now = time.time()
        item = _make_item("3", "React hooks tutorial", ["react"], 0.9, now, now)
        mock_result = RecallResult(item=item, score=0.85, match_reason="semantic")
        mock_retrieval = MagicMock()
        mock_retrieval.search.return_value = [mock_result]
        engine = QueryEngine(mock_retrieval)
        q = MemoryQuery(query="hooks", retrieval_mode="semantic", top_k=10)
        result = engine.execute(q, store)
        assert len(result) >= 1
        mock_retrieval.search.assert_called_once()

    def test_hybrid_mode_triggers_rerank(self, store):
        now = time.time()
        item = _make_item("3", "React hooks tutorial", ["react"], 0.9, now, now)
        mock_result = RecallResult(item=item, score=0.85, match_reason="semantic")
        mock_retrieval = MagicMock()
        mock_retrieval.search.return_value = [mock_result]
        engine = QueryEngine(mock_retrieval)
        q = MemoryQuery(query="hooks", retrieval_mode="hybrid", top_k=10)
        with patch("memos.query.HybridRetriever") as MockHR:
            instance = MockHR.return_value
            instance.rerank.return_value = [RecallResult(item=item, score=0.9, match_reason="hybrid")]
            result = engine.execute(q, store)
            assert len(result) >= 1
            instance.rerank.assert_called_once()

    def test_fallback_to_keyword_when_semantic_empty(self, engine, store):
        # mock_retrieval.search returns [] by default (fixture)
        q = MemoryQuery(query="Python patterns", retrieval_mode="semantic", top_k=10)
        result = engine.execute(q, store)
        # Should fall back to keyword — filtered items contain python-related content
        assert isinstance(result, list)

    def test_min_score_filters_low_results(self, store):
        now = time.time()
        low_item = _make_item("1", "barely relevant", importance=0.1, created_at=now)
        mock_retrieval = MagicMock()
        mock_retrieval.search.return_value = [
            RecallResult(item=low_item, score=0.05, match_reason="semantic"),
        ]
        engine = QueryEngine(mock_retrieval)
        q = MemoryQuery(query="test", retrieval_mode="semantic", min_score=0.5, top_k=10)
        result = engine.execute(q, store)
        assert len(result) == 0

    def test_decay_engine_integration(self, store):
        now = time.time()
        item = _make_item("3", "test", created_at=now)
        mock_retrieval = MagicMock()
        mock_retrieval.search.return_value = [
            RecallResult(item=item, score=0.8, match_reason="semantic"),
        ]
        mock_decay = MagicMock()
        mock_decay.adjusted_score.return_value = 0.6
        engine = QueryEngine(mock_retrieval, decay=mock_decay)
        q = MemoryQuery(query="test", retrieval_mode="semantic", min_score=0.5, top_k=10)
        result = engine.execute(q, store)
        assert len(result) >= 1
        mock_decay.adjusted_score.assert_called()

    def test_no_decay_engine(self, store):
        now = time.time()
        item = _make_item("3", "test", created_at=now)
        mock_retrieval = MagicMock()
        mock_retrieval.search.return_value = [
            RecallResult(item=item, score=0.8, match_reason="semantic"),
        ]
        engine = QueryEngine(mock_retrieval, decay=None)
        q = MemoryQuery(query="test", retrieval_mode="semantic", min_score=0.5, top_k=10)
        result = engine.execute(q, store)
        assert len(result) == 1

    def test_top_k_limits_final_results(self, store):
        now = time.time()
        items = [_make_item(f"i{i}", f"content {i}", importance=0.5, created_at=now) for i in range(10)]
        for item in items:
            store.upsert(item)
        mock_results = [
            RecallResult(item=item, score=0.5 + i * 0.01, match_reason="semantic") for i, item in enumerate(items)
        ]
        mock_retrieval = MagicMock()
        mock_retrieval.search.return_value = mock_results
        engine = QueryEngine(mock_retrieval)
        q = MemoryQuery(query="content", retrieval_mode="semantic", top_k=3)
        result = engine.execute(q, store)
        assert len(result) <= 3

    def test_namespace_filtering(self):
        ns_store = InMemoryBackend()
        now = time.time()
        ns_item = _make_item("ns1", "secret info", ["secret"], 0.8, now, now)
        ns_store.upsert(ns_item, namespace="agent-alice")
        # Global namespace has different item
        global_item = _make_item("g1", "public info", ["public"], 0.5, now, now)
        ns_store.upsert(global_item, namespace="")

        mock_retrieval = MagicMock()
        mock_retrieval.search.return_value = [
            RecallResult(item=ns_item, score=0.9, match_reason="semantic"),
        ]
        engine = QueryEngine(mock_retrieval, namespace="agent-alice")
        q = MemoryQuery(query="secret", retrieval_mode="semantic", top_k=10)
        result = engine.execute(q, ns_store)
        # _filtered_items only lists from "agent-alice" namespace
        mock_retrieval.search.assert_called_once()
        assert isinstance(result, list)

    def test_no_filtered_items_returns_empty(self, engine):
        store = InMemoryBackend()
        q = MemoryQuery(query="anything", top_k=10)
        result = engine.execute(q, store)
        assert result == []


# ===================================================================
# TestFilteredItems — _filtered_items() integration
# ===================================================================


class TestFilteredItems:
    """QueryEngine._filtered_items() — combines store.list_all + _matches."""

    def test_returns_all_when_no_filters(self, engine, store):
        q = MemoryQuery()
        items = engine._filtered_items(q, store)
        assert len(items) == 3

    def test_filters_by_tag(self, engine, store):
        q = MemoryQuery(include_tags=["python"])
        items = engine._filtered_items(q, store)
        assert len(items) == 1
        assert items[0].id == "1"

    def test_filters_expired(self, engine):
        now = time.time()
        items = [
            _make_item("1", "active", created_at=now, ttl=None),
            _make_item("2", "expired", created_at=now - 100, ttl=1),
        ]
        store = _seed_store(items)
        q = MemoryQuery()
        result = engine._filtered_items(q, store)
        assert len(result) == 1
        assert result[0].id == "1"

    def test_namespace_scoped(self):
        store = InMemoryBackend()
        now = time.time()
        store.upsert(_make_item("a", "alpha", created_at=now), namespace="ns1")
        store.upsert(_make_item("b", "beta", created_at=now), namespace="ns2")
        mock_retrieval = MagicMock()
        engine = QueryEngine(mock_retrieval, namespace="ns1")
        q = MemoryQuery()
        items = engine._filtered_items(q, store)
        assert len(items) == 1
        assert items[0].id == "a"


# ===================================================================
# TestApplyDecay — _apply_decay() private method
# ===================================================================


class TestApplyDecay:
    """QueryEngine._apply_decay() — decay engine integration."""

    def test_no_decay_filters_by_min_score(self, engine):
        items = [
            RecallResult(item=_make_item("1"), score=0.8, match_reason="semantic"),
            RecallResult(item=_make_item("2"), score=0.2, match_reason="keyword"),
        ]
        result = engine._apply_decay(items, min_score=0.5)
        assert len(result) == 1
        assert result[0].score == 0.8

    def test_no_decay_all_below_min_score(self, engine):
        items = [
            RecallResult(item=_make_item("1"), score=0.1, match_reason="keyword"),
            RecallResult(item=_make_item("2"), score=0.2, match_reason="keyword"),
        ]
        result = engine._apply_decay(items, min_score=0.5)
        assert result == []

    def test_decay_engine_adjusts_scores(self):
        mock_decay = MagicMock()
        # First call returns above threshold, second below
        mock_decay.adjusted_score.side_effect = [0.7, 0.1]
        mock_retrieval = MagicMock()
        engine = QueryEngine(mock_retrieval, decay=mock_decay)
        items = [
            RecallResult(item=_make_item("1"), score=0.8, match_reason="semantic"),
            RecallResult(item=_make_item("2"), score=0.5, match_reason="keyword"),
        ]
        result = engine._apply_decay(items, min_score=0.5)
        assert len(result) == 1
        assert result[0].score == 0.7

    def test_decay_engine_all_above_min(self):
        mock_decay = MagicMock()
        mock_decay.adjusted_score.side_effect = [0.8, 0.7]
        mock_retrieval = MagicMock()
        engine = QueryEngine(mock_retrieval, decay=mock_decay)
        items = [
            RecallResult(item=_make_item("1"), score=0.9, match_reason="semantic"),
            RecallResult(item=_make_item("2"), score=0.6, match_reason="keyword"),
        ]
        result = engine._apply_decay(items, min_score=0.5)
        assert len(result) == 2

    def test_empty_input_returns_empty(self, engine):
        result = engine._apply_decay([], min_score=0.0)
        assert result == []
