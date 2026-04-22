"""Stats and analytics admin routes."""

from __future__ import annotations

from fastapi import APIRouter


def register_admin_analytics_routes(router: APIRouter, memos) -> None:
    """Register stats and analytics endpoints."""

    @router.get("/api/v1/stats")
    async def api_stats():
        s = memos.stats()
        return {
            "total_memories": s.total_memories,
            "total_tags": s.total_tags,
            "avg_relevance": round(s.avg_relevance, 3),
            "avg_importance": round(s.avg_importance, 3),
            "oldest_memory_days": round(s.oldest_memory_days, 1),
            "newest_memory_days": round(s.newest_memory_days, 1),
            "decay_candidates": s.decay_candidates,
            "top_tags": s.top_tags,
        }

    @router.get("/api/v1/analytics/summary")
    async def api_analytics_summary(days: int = 7):
        return {"status": "ok", **memos.analytics.summary(days=days)}

    @router.get("/api/v1/analytics/top")
    async def api_analytics_top(n: int = 20):
        return {"status": "ok", "results": memos.analytics.top_recalled(n=n)}

    @router.get("/api/v1/analytics/patterns")
    async def api_analytics_patterns(n: int = 20):
        return {"status": "ok", "results": memos.analytics.query_patterns(n=n)}

    @router.get("/api/v1/analytics/latency")
    async def api_analytics_latency():
        return {"status": "ok", "results": memos.analytics.latency_stats()}

    @router.get("/api/v1/analytics/success-rate")
    async def api_analytics_success_rate(days: int = 7):
        return {"status": "ok", **memos.analytics.recall_success_rate_stats(days=days)}

    @router.get("/api/v1/analytics/daily")
    async def api_analytics_daily(days: int = 30):
        return {"status": "ok", "results": memos.analytics.daily_activity(days=days)}

    @router.get("/api/v1/analytics/zero-result")
    async def api_analytics_zero_result(n: int = 20):
        return {"status": "ok", "results": memos.analytics.zero_result_queries(n=n)}
