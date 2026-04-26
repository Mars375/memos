"""Time-travel recall memory routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..sse import sse_stream


def register_memory_time_travel_routes(router: APIRouter, memos) -> None:
    """Register time-travel recall endpoints."""

    @router.get("/api/v1/recall/at")
    async def api_recall_at(q: str, at: float, top: int = 5, min_score: float = 0.0) -> dict:
        results = memos.recall_at(q, at, top=top, min_score=min_score)
        return {
            "query": q,
            "timestamp": at,
            "total": len(results),
            "results": [
                {
                    "id": result.item.id,
                    "content": result.item.content,
                    "score": round(result.score, 4),
                    "tags": result.item.tags,
                    "match_reason": result.match_reason,
                }
                for result in results
            ],
        }

    @router.get("/api/v1/recall/at/stream", response_model=None)
    async def api_recall_at_stream(q: str, at: float, top: int = 5, min_score: float = 0.0) -> StreamingResponse:
        import asyncio as _asyncio

        results = memos.recall_at(q, at, top=top, min_score=min_score)

        async def _gen():
            for result in results:
                yield result
                await _asyncio.sleep(0)

        return StreamingResponse(
            sse_stream(_gen(), q),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
