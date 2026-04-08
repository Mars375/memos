"""Tests for recall analytics."""

from __future__ import annotations

from types import SimpleNamespace

from memos.analytics import RecallAnalytics


def test_recall_analytics_tracks_core_metrics(tmp_path):
    analytics = RecallAnalytics(path=tmp_path / "analytics.db", retention_days=365)

    analytics.track_recall(
        "alpha query",
        [SimpleNamespace(item=SimpleNamespace(id="mem-1")), SimpleNamespace(item=SimpleNamespace(id="mem-2"))],
        latency_ms=12.5,
    )
    analytics.track_recall(
        "alpha query",
        [SimpleNamespace(item=SimpleNamespace(id="mem-1"))],
        latency_ms=7.5,
    )
    analytics.track_recall("zero query", [], latency_ms=3.0)

    top = analytics.top_recalled(n=5)
    assert top[0]["memory_id"] == "mem-1"
    assert top[0]["count"] == 2

    patterns = analytics.query_patterns(n=5)
    assert patterns[0]["query"] == "alpha query"
    assert patterns[0]["count"] == 2

    latency = analytics.latency_stats()
    assert latency["count"] == 3
    assert latency["p50"] > 0
    assert latency["p95"] >= latency["p50"]

    success = analytics.recall_success_rate_stats(days=7)
    assert success["successful_recalls"] == 2
    assert success["failed_recalls"] == 1
    assert success["success_rate"] > 0

    daily = analytics.daily_activity(days=3)
    assert len(daily) == 3
    assert sum(day["count"] for day in daily) == 3

    zero = analytics.zero_result_queries(n=5)
    assert zero[0]["query"] == "zero query"
    assert zero[0]["count"] == 1
