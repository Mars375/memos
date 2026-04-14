"""Memory CRUD, recall, search, versioning, dedup, feedback, decay, export routes."""

from __future__ import annotations

import os
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ...sanitizer import MemorySanitizer
from ...utils import parse_date as _parse_date
from ..errors import error_response, handle_exception, not_found
from ..schemas import (
    BatchLearnRequest,
    CompressRequest,
    ConsolidateRequest,
    DecayRunRequest,
    DedupCheckRequest,
    DedupScanRequest,
    FeedbackRequest,
    LearnExtractRequest,
    LearnRequest,
    PruneRequest,
    RecallRequest,
    ReinforceRequest,
    RollbackRequest,
    SyncApplyRequest,
    SyncCheckRequest,
    TagDeleteRequest,
    TagRenameRequest,
    VersioningGCRequest,
)

_ENFORCE_SANITIZATION = os.environ.get("MEMOS_ENFORCE_SANITIZATION", "true").lower() in ("true", "1", "yes")


def create_memory_router(memos, _kg_bridge) -> APIRouter:
    """Create the memory-related API router."""
    router = APIRouter()

    # ── Learn ────────────────────────────────────────────────

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
        except ValueError as e:
            return error_response(str(e), status_code=400)

    @router.post("/api/v1/learn/extract", response_model=None)
    async def api_learn_extract(req: LearnExtractRequest) -> dict | JSONResponse:
        """Learn a memory and extract simple KG facts."""
        if _ENFORCE_SANITIZATION and not MemorySanitizer.is_safe(req.content):
            return error_response("Content failed safety checks", code="UNSAFE_CONTENT", status_code=400)
        try:
            payload = _kg_bridge.learn_and_extract(
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
        """Batch learn — store multiple memories in one call."""
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
        except ValueError as e:
            return error_response(str(e), status_code=400)

    # ── Recall ───────────────────────────────────────────────

    @router.post("/api/v1/recall")
    async def api_recall(req: RecallRequest) -> dict:
        def _as_list(value: Any) -> list[str]:
            if not value:
                return []
            if isinstance(value, str):
                return [value]
            return [str(item) for item in value if item]

        tags_payload = req.tags
        filter_tags = req.filter_tags
        tag_filter = None
        if isinstance(tags_payload, dict):
            tag_filter = {
                "include": _as_list(tags_payload.get("include")),
                "require": _as_list(tags_payload.get("require")),
                "exclude": _as_list(tags_payload.get("exclude")),
                "mode": tags_payload.get("mode", "ANY"),
            }
            filter_tags = None
        elif isinstance(tags_payload, list):
            filter_tags = tags_payload

        importance_payload = req.importance.model_dump()

        explain = req.explain
        results = memos.recall(
            query=req.query,
            top=req.top_k,
            filter_tags=filter_tags,
            min_score=req.min_score,
            filter_after=_parse_date(req.created_after or req.filter_after),
            filter_before=_parse_date(req.created_before or req.filter_before),
            retrieval_mode=req.retrieval_mode,
            tag_filter=tag_filter,
            min_importance=importance_payload.get("min"),
            max_importance=importance_payload.get("max"),
        )
        serialized = []
        for r in results:
            entry = {
                "id": r.item.id,
                "content": r.item.content,
                "score": round(r.score, 4),
                "tags": r.item.tags,
                "match_reason": r.match_reason,
                "importance": r.item.importance,
                "created_at": r.item.created_at,
                "age_days": round((time.time() - r.item.created_at) / 86400, 1),
            }
            if explain and r.score_breakdown:
                entry["score_breakdown"] = r.score_breakdown.to_dict()
            serialized.append(entry)
        return {"status": "ok", "results": serialized}

    @router.get("/api/v1/memories")
    async def api_list_memories(
        tag: list[str] | None = Query(default=None),
        require_tag: list[str] | None = Query(default=None),
        exclude_tag: list[str] | None = Query(default=None),
        min_importance: float | None = None,
        max_importance: float | None = None,
        after: str | None = None,
        before: str | None = None,
        sort: str = "created_at",
        limit: int = 50,
    ) -> dict:
        after_ts = datetime.fromisoformat(after).timestamp() if after else None
        before_ts = datetime.fromisoformat(before).timestamp() if before else None
        items = memos.list_memories(
            tags=tag,
            require_tags=require_tag,
            exclude_tags=exclude_tag,
            min_importance=min_importance,
            max_importance=max_importance,
            created_after=after_ts,
            created_before=before_ts,
            sort=sort,
            limit=limit,
        )
        return {
            "status": "ok",
            "results": [
                {
                    "id": item.id,
                    "content": item.content,
                    "tags": item.tags,
                    "importance": item.importance,
                    "created_at": item.created_at,
                    "accessed_at": item.accessed_at,
                }
                for item in items
            ],
            "total": len(items),
        }

    @router.get("/api/v1/recall/enriched")
    async def api_recall_enriched(
        q: str,
        top: int = 10,
        filter_tags: str | None = None,
        min_score: float = 0.0,
        filter_after: str | None = None,
        filter_before: str | None = None,
    ) -> dict:
        """Recall memories and augment them with KG facts."""
        tags = [t.strip() for t in filter_tags.split(",") if t.strip()] if filter_tags else None
        after_ts = datetime.fromisoformat(filter_after).timestamp() if filter_after else None
        before_ts = datetime.fromisoformat(filter_before).timestamp() if filter_before else None
        payload = _kg_bridge.recall_enriched(
            q,
            top=top,
            filter_tags=tags,
            min_score=min_score,
            filter_after=after_ts,
            filter_before=before_ts,
        )
        return {"status": "ok", **payload}

    @router.get("/api/v1/recall/stream", response_model=None)
    async def api_recall_stream(
        q: str,
        top: int = 5,
        filter_tags: str | None = None,
        min_score: float = 0.0,
    ) -> StreamingResponse:
        """Stream recall results as Server-Sent Events (SSE)."""
        from ..sse import sse_stream

        tags = [t.strip() for t in filter_tags.split(",") if t.strip()] if filter_tags else None
        recall_gen = memos.recall_stream(query=q, top=top, filter_tags=tags, min_score=min_score)
        return StreamingResponse(
            sse_stream(recall_gen, q),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # ── Search / Get / Delete ─────────────────────────────────

    @router.get("/api/v1/search")
    async def api_search(q: str, limit: int = 20) -> dict:
        items = memos.search(q=q, limit=limit)
        return {
            "status": "ok",
            "results": [
                {"id": item.id, "content": item.content[:200], "tags": item.tags, "importance": item.importance}
                for item in items
            ],
        }

    @router.delete("/api/v1/memory/{item_id}", response_model=None)
    async def api_delete(item_id: str) -> dict | JSONResponse:
        success = memos.forget(item_id)
        if success:
            return {"status": "deleted"}
        return not_found(f"Memory {item_id} not found")

    @router.get("/api/v1/memory/{item_id}")
    async def api_get_memory(item_id: str) -> dict:
        item = memos.get(item_id)
        if item is None:
            return not_found(f"Memory {item_id} not found")
        result = {
            "id": item.id,
            "content": item.content,
            "tags": item.tags,
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
            "relevance_score": item.relevance_score,
        }
        if item.ttl is not None:
            result.update({"ttl": item.ttl, "expires_at": item.expires_at, "is_expired": item.is_expired})
        if item.metadata:
            public_meta = {k: v for k, v in item.metadata.items() if not k.startswith("_")}
            if public_meta:
                result["metadata"] = public_meta
        return {"status": "ok", "item": result}

    # ── Prune ─────────────────────────────────────────────────

    @router.post("/api/v1/prune")
    async def api_prune(req: PruneRequest) -> dict:
        pruned = memos.prune(
            threshold=req.threshold,
            max_age_days=req.max_age_days,
            dry_run=req.dry_run,
        )
        return {"status": "ok", "pruned_count": len(pruned), "pruned_ids": [item.id for item in pruned]}

    # ── Tags & Classify ───────────────────────────────────────

    @router.get("/api/v1/classify")
    async def api_classify(text: str) -> dict:
        """Classify text into memory type tags (zero-LLM)."""
        from ...tagger import AutoTagger

        tagger = AutoTagger()
        return {"status": "ok", "tags": tagger.tag(text), "matches": tagger.tag_detailed(text)}

    @router.get("/api/v1/tags", response_model=None)
    async def api_tags(sort: str = "count", limit: int = 0) -> list[dict]:
        tags = memos.list_tags(sort=sort, limit=limit)
        return [{"tag": t, "count": c} for t, c in tags]

    @router.post("/api/v1/tags/rename")
    async def api_tags_rename(req: TagRenameRequest) -> dict:
        return {
            "status": "ok",
            "renamed": memos.rename_tag(req.old, req.new),
            "old_tag": req.old,
            "new_tag": req.new,
        }

    @router.post("/api/v1/tags/delete")
    async def api_tags_delete(req: TagDeleteRequest) -> dict:
        return {"status": "ok", "deleted": memos.delete_tag(req.tag), "tag": req.tag}

    # ── Consolidation ─────────────────────────────────────────

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

    # ── Versioning ────────────────────────────────────────────

    @router.get("/api/v1/memory/{item_id}/history")
    async def api_version_history(item_id: str) -> dict:
        versions = memos.history(item_id)
        return {"item_id": item_id, "versions": [v.to_dict() for v in versions], "total": len(versions)}

    @router.get("/api/v1/memory/{item_id}/version/{version_number}", response_model=None)
    async def api_version_get(item_id: str, version_number: int) -> dict | JSONResponse:
        v = memos.get_version(item_id, version_number)
        if v is None:
            return not_found(f"Version {version_number} of memory {item_id} not found")
        return {"status": "ok", "version": v.to_dict()}

    @router.get("/api/v1/memory/{item_id}/diff", response_model=None)
    async def api_version_diff(
        item_id: str, v1: int, v2: int | None = None, latest: bool = False
    ) -> dict | JSONResponse:
        if latest:
            result = memos.diff_latest(item_id)
        else:
            if v2 is None:
                return error_response("Provide v2 or use ?latest=true", status_code=400)
            result = memos.diff(item_id, v1, v2)
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
    async def api_snapshot(at: float) -> dict:
        versions = memos.snapshot_at(at)
        return {"timestamp": at, "total": len(versions), "memories": [v.to_dict() for v in versions[:200]]}

    @router.get("/api/v1/recall/at")
    async def api_recall_at(q: str, at: float, top: int = 5, min_score: float = 0.0) -> dict:
        results = memos.recall_at(q, at, top=top, min_score=min_score)
        return {
            "query": q,
            "timestamp": at,
            "total": len(results),
            "results": [
                {
                    "id": r.item.id,
                    "content": r.item.content,
                    "score": round(r.score, 4),
                    "tags": r.item.tags,
                    "match_reason": r.match_reason,
                }
                for r in results
            ],
        }

    @router.get("/api/v1/versioning/stats")
    async def api_versioning_stats() -> dict:
        return memos.versioning_stats()

    @router.post("/api/v1/versioning/gc")
    async def api_versioning_gc(req: VersioningGCRequest | None = None) -> dict:
        req = req or VersioningGCRequest()
        removed = memos.versioning_gc(
            max_age_days=req.max_age_days,
            keep_latest=req.keep_latest,
        )
        return {"status": "ok", "removed": removed}

    @router.get("/api/v1/recall/at/stream", response_model=None)
    async def api_recall_at_stream(q: str, at: float, top: int = 5, min_score: float = 0.0) -> StreamingResponse:
        """Stream time-travel recall results as SSE events."""
        import asyncio as _asyncio

        from ..sse import sse_stream

        results = memos.recall_at(q, at, top=top, min_score=min_score)

        async def _gen():
            for r in results:
                yield r
                await _asyncio.sleep(0)

        return StreamingResponse(
            sse_stream(_gen(), q),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # ── Feedback ─────────────────────────────────────────────

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
        except ValueError as e:
            return error_response(str(e), status_code=400)

    @router.get("/api/v1/feedback")
    async def api_list_feedback(item_id: str | None = None, limit: int = 100) -> dict:
        entries = memos.get_feedback(item_id=item_id, limit=limit)
        return {"feedback": [e.to_dict() for e in entries], "total": len(entries)}

    @router.get("/api/v1/feedback/stats")
    async def api_feedback_stats() -> dict:
        return memos.feedback_stats().to_dict()

    # ── Decay & Reinforce ─────────────────────────────────────

    @router.post("/api/v1/decay/run")
    async def api_decay_run(req: DecayRunRequest | None = None) -> dict:
        req = req or DecayRunRequest()
        items = memos._store.list_all(namespace=memos._namespace)
        report = memos._decay.run_decay(items, min_age_days=req.min_age_days, floor=req.floor, dry_run=req.dry_run)
        if not req.dry_run:
            for item in items:
                memos._store.upsert(item, namespace=memos._namespace)
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
        item = memos._store.get(memory_id, namespace=memos._namespace)
        if item is None:
            return not_found(f"Memory {memory_id} not found")
        old_imp = item.importance
        new_imp = memos._decay.reinforce(item, strength=req.strength)
        memos._store.upsert(item, namespace=memos._namespace)
        return {
            "status": "ok",
            "id": item.id,
            "importance_before": round(old_imp, 4),
            "importance_after": round(new_imp, 4),
        }

    # ── Compress ──────────────────────────────────────────────

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

    # ── Dedup ─────────────────────────────────────────────────

    @router.post("/api/v1/dedup/check")
    async def api_dedup_check(req: DedupCheckRequest) -> dict:
        result = memos.dedup_check(req.content, threshold=req.threshold)
        resp = {"is_duplicate": result.is_duplicate, "reason": result.reason, "similarity": result.similarity}
        if result.match:
            resp["match"] = {
                "id": result.match.id,
                "content": result.match.content[:500],
                "tags": result.match.tags,
                "importance": result.match.importance,
            }
        return resp

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

    # ── Sync & Conflict ───────────────────────────────────────

    @router.post("/api/v1/sync/check", response_model=None)
    async def api_sync_check(req: SyncCheckRequest) -> dict | JSONResponse:
        from ...conflict import ConflictDetector
        from ...sharing.models import MemoryEnvelope

        try:
            envelope = MemoryEnvelope.from_dict(req.envelope)
        except (KeyError, ValueError):
            return error_response("Invalid envelope format", status_code=400)
        if not envelope.validate():
            return error_response("Envelope checksum validation failed", status_code=400)
        detector = ConflictDetector()
        return {"status": "ok", **detector.detect(memos, envelope).to_dict()}

    @router.post("/api/v1/sync/apply", response_model=None)
    async def api_sync_apply(req: SyncApplyRequest) -> dict | JSONResponse:
        from ...conflict import ConflictDetector, ResolutionStrategy
        from ...sharing.models import MemoryEnvelope

        try:
            envelope = MemoryEnvelope.from_dict(req.envelope)
        except (KeyError, ValueError):
            return error_response("Invalid envelope format", status_code=400)
        if not envelope.validate():
            return error_response("Envelope checksum validation failed", status_code=400)
        try:
            strategy = ResolutionStrategy(req.strategy)
        except ValueError:
            return error_response("Invalid strategy. Use: local_wins, remote_wins, merge, manual", status_code=400)
        detector = ConflictDetector()
        report = detector.detect(memos, envelope)
        if req.dry_run:
            detector.resolve(report.conflicts, strategy)
            return {"status": "ok", "dry_run": True, **report.to_dict()}
        return {"status": "ok", **detector.apply(memos, report, strategy).to_dict()}

    # ── Export ────────────────────────────────────────────────

    @router.get("/api/v1/export/markdown", response_model=None)
    async def api_export_markdown(
        output_dir: str | None = None, update: bool = False, wiki_dir: str | None = None
    ) -> FileResponse:
        """Export MemOS knowledge as a downloadable markdown ZIP."""
        from ...export_markdown import MarkdownExporter

        export_root = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="memos-markdown-export-"))
        MarkdownExporter(memos, kg=_kg_bridge._kg if hasattr(_kg_bridge, "_kg") else None, wiki_dir=wiki_dir).export(
            str(export_root), update=update
        )
        zip_path = export_root.parent / f"{export_root.name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for file_path in sorted(export_root.rglob("*")):
                if file_path.is_file():
                    bundle.write(file_path, arcname=str(file_path.relative_to(export_root)))
        return FileResponse(
            str(zip_path), media_type="application/zip", filename=f"memos-markdown-export-{int(time.time())}.zip"
        )

    @router.get("/api/v1/export/parquet", response_model=None)
    async def api_export_parquet(include_metadata: bool = True, compression: str = "zstd") -> FileResponse:
        """Export all memories as a downloadable Parquet file."""
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            result = memos.export_parquet(tmp.name, include_metadata=include_metadata, compression=compression)
            return FileResponse(
                tmp.name,
                media_type="application/octet-stream",
                filename=f"memos-export-{int(time.time())}.parquet",
                headers={"X-Memos-Total": str(result["total"]), "X-Memos-Size": str(result["size_bytes"])},
            )

    return router
