"""Memory feedback routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..errors import error_response
from ..schemas import FeedbackRequest


def register_memory_feedback_routes(router: APIRouter, memos) -> None:
    """Register feedback endpoints."""

    @router.post("/api/v1/feedback", response_model=None)
    async def api_record_feedback(req: FeedbackRequest) -> dict | JSONResponse:
        try:
            entry = memos.record_feedback(
                item_id=req.item_id,
                feedback=req.feedback,
                query=req.query,
                score_at_recall=req.score_at_recall,
                agent_id=req.agent_id,
            )
            return {"status": "ok", "feedback": entry.to_dict()}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)

    @router.get("/api/v1/feedback")
    async def api_list_feedback(item_id: str | None = None, limit: int = 100) -> dict:
        entries = memos.get_feedback(item_id=item_id, limit=limit)
        return {"feedback": [entry.to_dict() for entry in entries], "total": len(entries)}

    @router.get("/api/v1/feedback/stats")
    async def api_feedback_stats() -> dict:
        return memos.feedback_stats().to_dict()
