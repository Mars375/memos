"""Memory consolidation routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..errors import not_found
from ..schemas import ConsolidateRequest


def register_memory_consolidation_routes(router: APIRouter, memos) -> None:
    """Register consolidation endpoints."""

    @router.post("/api/v1/consolidate")
    async def api_consolidate(req: ConsolidateRequest) -> dict:
        if req.async_:
            handle = await memos.consolidate_async(
                similarity_threshold=req.similarity_threshold,
                merge_content=req.merge_content,
                dry_run=req.dry_run,
            )
            return {"status": "started", "task_id": handle.task_id}
        result = memos.consolidate(
            similarity_threshold=req.similarity_threshold,
            merge_content=req.merge_content,
            dry_run=req.dry_run,
        )
        return {
            "status": "completed",
            "groups_found": result.groups_found,
            "memories_merged": result.memories_merged,
            "space_freed": result.space_freed,
        }

    @router.get("/api/v1/consolidate/{task_id}", response_model=None)
    async def api_consolidate_status(task_id: str) -> dict | JSONResponse:
        status = memos.consolidation_status(task_id)
        if status:
            return status
        return not_found(f"Consolidation task {task_id} not found")

    @router.get("/api/v1/consolidate")
    async def api_consolidate_list() -> dict:
        return {"tasks": memos.consolidation_tasks()}
