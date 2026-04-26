"""Memory deduplication routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import DedupCheckRequest, DedupScanRequest


def register_memory_dedup_routes(router: APIRouter, memos) -> None:
    """Register duplicate detection endpoints."""

    @router.post("/api/v1/dedup/check")
    async def api_dedup_check(req: DedupCheckRequest) -> dict:
        result = memos.dedup_check(req.content, threshold=req.threshold)
        response = {"is_duplicate": result.is_duplicate, "reason": result.reason, "similarity": result.similarity}
        if result.match:
            response["match"] = {
                "id": result.match.id,
                "content": result.match.content[:500],
                "tags": result.match.tags,
                "importance": result.match.importance,
            }
        return response

    @router.post("/api/v1/dedup/scan")
    async def api_dedup_scan(req: DedupScanRequest) -> dict:
        result = memos.dedup_scan(fix=req.fix, threshold=req.threshold)
        return {
            "total_scanned": result.total_scanned,
            "exact_duplicates": result.exact_duplicates,
            "near_duplicates": result.near_duplicates,
            "total_duplicates": result.total_duplicates,
            "fixed": result.fixed,
            "groups": result.groups[:50],
        }
