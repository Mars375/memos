"""Memory lifecycle maintenance routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..errors import not_found
from ..schemas import CompressRequest, DecayRunRequest, PruneRequest, ReinforceRequest


def register_memory_lifecycle_routes(router: APIRouter, memos) -> None:
    """Register prune, decay, reinforce, and compression endpoints."""

    @router.post("/api/v1/prune")
    async def api_prune(req: PruneRequest) -> dict:
        pruned = memos.prune(threshold=req.threshold, max_age_days=req.max_age_days, dry_run=req.dry_run)
        return {"status": "ok", "pruned_count": len(pruned), "pruned_ids": [item.id for item in pruned]}

    @router.post("/api/v1/decay/run")
    async def api_decay_run(req: DecayRunRequest | None = None) -> dict:
        req = req or DecayRunRequest()
        report = memos.decay(min_age_days=req.min_age_days, floor=req.floor, dry_run=req.dry_run)
        return {
            "status": "ok",
            "total": report.total,
            "decayed": report.decayed,
            "avg_importance_before": round(report.avg_importance_before, 4),
            "avg_importance_after": round(report.avg_importance_after, 4),
            "details": report.details[:50],
        }

    @router.post("/api/v1/memories/{memory_id}/reinforce", response_model=None)
    async def api_reinforce(memory_id: str, req: ReinforceRequest | None = None) -> dict | JSONResponse:
        req = req or ReinforceRequest()
        item = memos.get(memory_id)
        if item is None:
            return not_found(f"Memory {memory_id} not found")
        old_imp = item.importance
        new_imp = memos.reinforce_memory(memory_id, strength=req.strength)
        return {
            "status": "ok",
            "id": memory_id,
            "importance_before": round(old_imp, 4),
            "importance_after": round(new_imp, 4),
        }

    @router.post("/api/v1/compress")
    async def api_compress(req: CompressRequest | None = None) -> dict:
        req = req or CompressRequest()
        result = memos.compress(threshold=req.threshold, dry_run=req.dry_run)
        return {
            "status": "ok",
            "compressed_count": result.compressed_count,
            "summary_count": result.summary_count,
            "freed_bytes": result.freed_bytes,
            "groups_considered": result.groups_considered,
            "details": result.details,
        }
