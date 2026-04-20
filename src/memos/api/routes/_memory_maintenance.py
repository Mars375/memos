"""Maintenance, tags, feedback, and lifecycle memory routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..errors import error_response, not_found
from ..schemas import (
    CompressRequest,
    ConsolidateRequest,
    DecayRunRequest,
    DedupCheckRequest,
    DedupScanRequest,
    FeedbackRequest,
    PruneRequest,
    ReinforceRequest,
    TagDeleteRequest,
    TagRenameRequest,
)


def register_memory_maintenance_routes(router: APIRouter, memos) -> None:
    """Register maintenance-oriented memory routes."""

    @router.post("/api/v1/prune")
    async def api_prune(req: PruneRequest) -> dict:
        pruned = memos.prune(threshold=req.threshold, max_age_days=req.max_age_days, dry_run=req.dry_run)
        return {"status": "ok", "pruned_count": len(pruned), "pruned_ids": [item.id for item in pruned]}

    @router.get("/api/v1/classify")
    async def api_classify(text: str) -> dict:
        from ...tagger import AutoTagger

        tagger = AutoTagger()
        return {"status": "ok", "tags": tagger.tag(text), "matches": tagger.tag_detailed(text)}

    @router.get("/api/v1/tags", response_model=None)
    async def api_tags(sort: str = "count", limit: int = 0) -> list[dict]:
        tags = memos.list_tags(sort=sort, limit=limit)
        return [{"tag": tag, "count": count} for tag, count in tags]

    @router.post("/api/v1/tags/rename")
    async def api_tags_rename(req: TagRenameRequest) -> dict:
        return {"status": "ok", "renamed": memos.rename_tag(req.old, req.new), "old_tag": req.old, "new_tag": req.new}

    @router.post("/api/v1/tags/delete")
    async def api_tags_delete(req: TagDeleteRequest) -> dict:
        return {"status": "ok", "deleted": memos.delete_tag(req.tag), "tag": req.tag}

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
