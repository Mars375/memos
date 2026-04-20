"""Learn-oriented memory routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...sanitizer import MemorySanitizer
from ..errors import error_response, handle_exception
from ..schemas import BatchLearnRequest, LearnExtractRequest, LearnRequest
from ._memory_common import _ENFORCE_SANITIZATION


def register_memory_learn_routes(router: APIRouter, memos, kg_bridge) -> None:
    """Register learn and batch-learn endpoints on the provided router."""

    @router.post("/api/v1/learn", response_model=None)
    async def api_learn(req: LearnRequest) -> dict | JSONResponse:
        if _ENFORCE_SANITIZATION and not MemorySanitizer.is_safe(req.content):
            return error_response("Content failed safety checks", code="UNSAFE_CONTENT", status_code=400)
        try:
            item = memos.learn(
                content=req.content,
                tags=req.tags,
                importance=req.importance,
                metadata=req.metadata,
            )
            return {"status": "ok", "id": item.id, "tags": item.tags}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)

    @router.post("/api/v1/learn/extract", response_model=None)
    async def api_learn_extract(req: LearnExtractRequest) -> dict | JSONResponse:
        if _ENFORCE_SANITIZATION and not MemorySanitizer.is_safe(req.content):
            return error_response("Content failed safety checks", code="UNSAFE_CONTENT", status_code=400)
        try:
            payload = kg_bridge.learn_and_extract(
                req.content,
                tags=req.tags,
                importance=req.importance,
                metadata=req.metadata,
            )
            return {"status": "ok", **payload}
        except Exception as exc:
            return handle_exception(exc, context="api_learn_extract")

    @router.post("/api/v1/learn/batch", response_model=None)
    async def api_batch_learn(req: BatchLearnRequest) -> dict | JSONResponse:
        if _ENFORCE_SANITIZATION:
            unsafe = [i for i, item in enumerate(req.items) if not MemorySanitizer.is_safe(item.content)]
            if unsafe:
                return error_response(
                    f"Items failed safety checks: indexes {unsafe[:10]}",
                    code="UNSAFE_CONTENT",
                    status_code=400,
                )
        try:
            result = memos.batch_learn(
                items=[item.model_dump() for item in req.items],
                continue_on_error=req.continue_on_error,
            )
            return {"status": "ok", **result}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
