"""Versioning and time-travel memory routes."""

from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..errors import error_response, not_found
from ..schemas import RollbackRequest, VersioningGCRequest


def register_memory_versioning_routes(router: APIRouter, memos) -> None:
    """Register versioning endpoints."""

    @router.get("/api/v1/memory/{item_id}/history")
    async def api_version_history(item_id: str) -> dict:
        versions = memos.history(item_id)
        return {"item_id": item_id, "versions": [version.to_dict() for version in versions], "total": len(versions)}

    @router.get("/api/v1/memory/{item_id}/version/{version_number}", response_model=None)
    async def api_version_get(item_id: str, version_number: int) -> dict | JSONResponse:
        version = memos.get_version(item_id, version_number)
        if version is None:
            return not_found(f"Version {version_number} of memory {item_id} not found")
        return {"status": "ok", "version": version.to_dict()}

    @router.get("/api/v1/memory/{item_id}/diff", response_model=None)
    async def api_version_diff(
        item_id: str, v1: int, v2: int | None = None, latest: bool = False
    ) -> dict | JSONResponse:
        result = memos.diff_latest(item_id) if latest else memos.diff(item_id, v1, v2) if v2 is not None else None
        if not latest and v2 is None:
            return error_response("Provide v2 or use ?latest=true", status_code=400)
        if result is None:
            return not_found(f"Memory {item_id} not found")
        return {"status": "ok", "diff": result.to_dict()}

    @router.post("/api/v1/memory/{item_id}/rollback", response_model=None)
    async def api_version_rollback(item_id: str, req: RollbackRequest) -> dict | JSONResponse:
        result = memos.rollback(item_id, req.version)
        if result is None:
            return not_found(f"Memory {item_id} version {req.version} not found")
        return {
            "status": "ok",
            "item_id": result.id,
            "content": result.content[:200],
            "tags": result.tags,
            "rolled_back_to": req.version,
        }

    @router.get("/api/v1/snapshot")
    async def api_snapshot(at: float | None = None) -> dict:
        ts = at if at is not None else time.time()
        versions = memos.snapshot_at(ts)
        return {"timestamp": ts, "total": len(versions), "memories": [version.to_dict() for version in versions[:200]]}

    @router.get("/api/v1/versioning/stats")
    async def api_versioning_stats() -> dict:
        return memos.versioning_stats()

    @router.post("/api/v1/versioning/gc")
    async def api_versioning_gc(req: VersioningGCRequest | None = None) -> dict:
        req = req or VersioningGCRequest()
        max_age_days = req.max_age_days
        keep_latest = req.keep_latest
        removed = memos.versioning_gc(max_age_days=max_age_days, keep_latest=keep_latest)
        return {"status": "ok", "removed": removed}
