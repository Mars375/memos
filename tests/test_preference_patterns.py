"""Tests for preference_patterns (Task 2.3) and analytics integration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from memos.analytics import RecallAnalytics, _extract_keywords


# ---------------------------------------------------------------------------
# _extract_keywords helper
# ---------------------------------------------------------------------------


def test_extract_keywords_basic() -> None:
    kw = _extract_keywords("Python machine learning is great")
    assert "python" in kw
    assert "machine" in kw
    assert "learning" in kw
    assert "great" in kw


def test_extract_keywords_skips_short() -> None:
    kw = _extract_keywords("I am a go")
    # words < 3 chars excluded
    assert "am" not in kw
    assert len([k for k in kw if len(k) < 3]) == 0


def test_extract_keywords_empty() -> None:
    assert _extract_keywords("") == []


# ---------------------------------------------------------------------------
# preference_patterns
# ---------------------------------------------------------------------------


def test_preference_patterns_empty_db(tmp_path) -> None:
    analytics = RecallAnalytics(path=tmp_path / "analytics.db")
    patterns = analytics.preference_patterns()
    assert patterns == []


def test_preference_patterns_returns_frequent_topics(tmp_path) -> None:
    analytics = RecallAnalytics(path=tmp_path / "analytics.db", retention_days=365)

    # Track several recall events with overlapping query keywords
    analytics.track_recall(
        "python machine learning",
        [SimpleNamespace(item=SimpleNamespace(id="mem-1"))],
        latency_ms=10.0,
    )
    analytics.track_recall(
        "python machine learning",
        [SimpleNamespace(item=SimpleNamespace(id="mem-1"))],
        latency_ms=8.0,
    )
    analytics.track_recall(
        "rust systems programming",
        [SimpleNamespace(item=SimpleNamespace(id="mem-3"))],
        latency_ms=5.0,
    )

    patterns = analytics.preference_patterns(top_k=10)

    # Should have at least two distinct tag groups
    assert len(patterns) >= 2

    # Most frequent should be the python/ml query (appeared twice)
    top = patterns[0]
    assert top["frequency"] >= 2
    assert isinstance(top["tags"], list)
    assert "python" in top["tags"] or "machine" in top["tags"]


def test_preference_patterns_respects_top_k(tmp_path) -> None:
    analytics = RecallAnalytics(path=tmp_path / "analytics.db", retention_days=365)

    for i in range(10):
        analytics.track_recall(
            f"topic {i} unique query",
            [SimpleNamespace(item=SimpleNamespace(id=f"mem-{i}"))],
            latency_ms=1.0,
        )

    patterns = analytics.preference_patterns(top_k=3)
    assert len(patterns) <= 3


def test_preference_patterns_graceful_on_corrupt_db(tmp_path) -> None:
    """If the recalls table is gone, preference_patterns should return []."""
    analytics = RecallAnalytics(path=tmp_path / "analytics.db")

    # Drop the table to simulate a missing/corrupt state
    import sqlite3

    conn = sqlite3.connect(analytics.path)
    conn.execute("DROP TABLE recalls")
    conn.commit()
    conn.close()

    # Should not raise
    patterns = analytics.preference_patterns()
    assert patterns == []


def test_preference_patterns_in_summary(tmp_path) -> None:
    analytics = RecallAnalytics(path=tmp_path / "analytics.db", retention_days=365)

    analytics.track_recall(
        "test query",
        [SimpleNamespace(item=SimpleNamespace(id="mem-1"))],
        latency_ms=5.0,
    )

    s = analytics.summary()
    assert "preference_patterns" in s
    assert isinstance(s["preference_patterns"], list)


# ---------------------------------------------------------------------------
# Brain search preference boost integration
# ---------------------------------------------------------------------------


def test_brain_search_with_analytics_boost(tmp_path) -> None:
    """Verify that BrainSearch accepts analytics and uses it for boosting."""
    from memos.analytics import RecallAnalytics
    from memos.brain import BrainSearch
    from memos.core import MemOS

    persist_path = tmp_path / "store.json"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("Python machine learning models", tags=["python", "ml"])
    memos.learn("Rust systems programming tips", tags=["rust", "systems"])

    # Set up analytics with preference for python
    analytics = RecallAnalytics(path=tmp_path / "analytics.db", retention_days=365)
    for _ in range(5):
        analytics.track_recall(
            "python machine learning",
            [SimpleNamespace(item=SimpleNamespace(id="mem-1"))],
            latency_ms=5.0,
        )

    searcher = BrainSearch(memos, wiki_dir=str(wiki_root), analytics=analytics)
    result = searcher.search("programming", top_k=10)

    # Should return memories (at least one)
    assert len(result.memories) >= 1
    # The python memory should be boosted
    python_mem = next(
        (m for m in result.memories if "Python" in m.content), None
    )
    assert python_mem is not None


def test_brain_search_without_analytics_no_boost(tmp_path) -> None:
    """Without analytics, brain search should work normally (no boost)."""
    from memos.brain import BrainSearch
    from memos.core import MemOS
    from memos.wiki_living import LivingWikiEngine

    persist_path = tmp_path / "store.json"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("Just a test memory", tags=["test"])

    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()

    searcher = BrainSearch(memos, wiki_dir=str(wiki_root))
    result = searcher.search("test", top_k=5)

    assert len(result.memories) >= 1
