"""Memory CRUD, recall, search, versioning, dedup, feedback, decay, export routes."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse


def create_memory_router(memos, _kg_bridge) -> APIRouter:
    """Create the memory-related API router."""
    router = APIRouter()

    # ── Learn ────────────────────────────────────────────────

    @router.post("/api/v1/learn")
    async def api_learn(body: dict):
        try:
            item = memos.learn(
                content=body["content"],
                tags=body.get("tags"),
                importance=body.get("importance", 0.5),
                metadata=body.get("metadata"),
            )
            return {"status": "ok", "id": item.id, "tags": item.tags}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/v1/learn/extract")
    async def api_learn_extract(body: dict):
        """Learn a memory and extract simple KG facts."""
        content = body.get("content", "").strip()
        if not content:
            return {"status": "error", "message": "content is required"}
        try:
            payload = _kg_bridge.learn_and_extract(
                content,
                tags=body.get("tags"),
                importance=float(body.get("importance", 0.5)),
                metadata=body.get("metadata"),
            )
            return {"status": "ok", **payload}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.post("/api/v1/learn/batch")
    async def api_batch_learn(body: dict):
        """Batch learn — store multiple memories in one call."""
        items = body.get("items", [])
        if not items:
            return {"status": "error", "message": "No items provided"}
        if len(items) > 1000:
            return {"status": "error", "message": "Batch size exceeds 1000 items"}
        try:
            result = memos.batch_learn(
                items=items,
                continue_on_error=body.get("continue_on_error", True),
            )
            return {"status": "ok", **result}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    # ── Recall ───────────────────────────────────────────────

    @router.post("/api/v1/recall")
    async def api_recall(body: dict):
        from datetime import datetime as _dt

        def _parse_date(value: Any) -> float | None:
            if not value:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            return _dt.fromisoformat(str(value)).timestamp()

        def _as_list(value: Any) -> list[str]:
            if not value:
                return []
            if isinstance(value, str):
                return [value]
            return [str(item) for item in value if item]

        tags_payload = body.get("tags")
        filter_tags = body.get("filter_tags")
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

        importance_payload = body.get("importance") or {}
        retrieval_mode = body.get("retrieval_mode", "semantic")
        if retrieval_mode not in ("semantic", "keyword", "hybrid"):
            return {"status": "error", "message": "Invalid retrieval_mode. Must be semantic, keyword, or hybrid."}

        explain = body.get("explain", False)
        results = memos.recall(
            query=body["query"],
            top=body.get("top_k", body.get("top", 5)),
            filter_tags=filter_tags,
            min_score=body.get("min_score", 0.0),
            filter_after=_parse_date(body.get("created_after") or body.get("filter_after")),
            filter_before=_parse_date(body.get("created_before") or body.get("filter_before")),
            retrieval_mode=retrieval_mode,
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
    ):
        from datetime import datetime as _dt
        after_ts = _dt.fromisoformat(after).timestamp() if after else None
        before_ts = _dt.fromisoformat(before).timestamp() if before else None
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
    ):
        """Recall memories and augment them with KG facts."""
        from datetime import datetime as _dt
        tags = [t.strip() for t in filter_tags.split(",") if t.strip()] if filter_tags else None
        after_ts = _dt.fromisoformat(filter_after).timestamp() if filter_after else None
        before_ts = _dt.fromisoformat(filter_before).timestamp() if filter_before else None
        payload = _kg_bridge.recall_enriched(
            q, top=top, filter_tags=tags, min_score=min_score,
            filter_after=after_ts, filter_before=before_ts,
        )
        return {"status": "ok", **payload}

    @router.get("/api/v1/recall/stream")
    async def api_recall_stream(
        q: str, top: int = 5, filter_tags: str | None = None, min_score: float = 0.0,
    ):
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
    async def api_search(q: str, limit: int = 20):
        items = memos.search(q=q, limit=limit)
        return {
            "status": "ok",
            "results": [
                {"id": item.id, "content": item.content[:200], "tags": item.tags, "importance": item.importance}
                for item in items
            ],
        }

    @router.delete("/api/v1/memory/{item_id}")
    async def api_delete(item_id: str):
        success = memos.forget(item_id)
        return {"status": "deleted" if success else "not_found"}

    @router.get("/api/v1/memory/{item_id}")
    async def api_get_memory(item_id: str):
        item = memos.get(item_id)
        if item is None:
            return {"status": "not_found", "message": f"Memory {item_id} not found"}
        result = {
            "id": item.id, "content": item.content, "tags": item.tags,
            "importance": item.importance, "created_at": item.created_at,
            "accessed_at": item.accessed_at, "access_count": item.access_count,
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
    async def api_prune(body: dict):
        pruned = memos.prune(
            threshold=body.get("threshold", 0.1),
            max_age_days=body.get("max_age_days", 90.0),
            dry_run=body.get("dry_run", False),
        )
        return {"status": "ok", "pruned_count": len(pruned), "pruned_ids": [item.id for item in pruned]}

    # ── Tags & Classify ───────────────────────────────────────

    @router.get("/api/v1/classify")
    async def api_classify(text: str):
        """Classify text into memory type tags (zero-LLM)."""
        from ...tagger import AutoTagger
        tagger = AutoTagger()
        return {"status": "ok", "tags": tagger.tag(text), "matches": tagger.tag_detailed(text)}

    @router.get("/api/v1/tags")
    async def api_tags(sort: str = "count", limit: int = 0):
        tags = memos.list_tags(sort=sort, limit=limit)
        return [{"tag": t, "count": c} for t, c in tags]

    @router.post("/api/v1/tags/rename")
    async def api_tags_rename(body: dict):
        old_tag, new_tag = body.get("old"), body.get("new")
        if not old_tag or not new_tag:
            return {"error": "Both 'old' and 'new' tag names are required"}
        return {"status": "ok", "renamed": memos.rename_tag(old_tag, new_tag), "old_tag": old_tag, "new_tag": new_tag}

    @router.post("/api/v1/tags/delete")
    async def api_tags_delete(body: dict):
        tag = body.get("tag")
        if not tag:
            return {"error": "Tag name is required"}
        return {"status": "ok", "deleted": memos.delete_tag(tag), "tag": tag}

    # ── Consolidation ─────────────────────────────────────────

    @router.post("/api/v1/consolidate")
    async def api_consolidate(body: dict):
        threshold = body.get("similarity_threshold", 0.75)
        merge = body.get("merge_content", False)
        dry = body.get("dry_run", False)
        if body.get("async", False):
            handle = await memos.consolidate_async(similarity_threshold=threshold, merge_content=merge, dry_run=dry)
            return {"status": "started", "task_id": handle.task_id}
        result = memos.consolidate(similarity_threshold=threshold, merge_content=merge, dry_run=dry)
        return {"status": "completed", "groups_found": result.groups_found, "memories_merged": result.memories_merged, "space_freed": result.space_freed}

    @router.get("/api/v1/consolidate/{task_id}")
    async def api_consolidate_status(task_id: str):
        status = memos.consolidation_status(task_id)
        return status if status else {"status": "not_found", "task_id": task_id}

    @router.get("/api/v1/consolidate")
    async def api_consolidate_list():
        return {"tasks": memos.consolidation_tasks()}

    # ── Versioning ────────────────────────────────────────────

    @router.get("/api/v1/memory/{item_id}/history")
    async def api_version_history(item_id: str):
        versions = memos.history(item_id)
        return {"item_id": item_id, "versions": [v.to_dict() for v in versions], "total": len(versions)}

    @router.get("/api/v1/memory/{item_id}/version/{version_number}")
    async def api_version_get(item_id: str, version_number: int):
        v = memos.get_version(item_id, version_number)
        if v is None:
            return {"status": "not_found", "item_id": item_id, "version": version_number}
        return {"status": "ok", "version": v.to_dict()}

    @router.get("/api/v1/memory/{item_id}/diff")
    async def api_version_diff(item_id: str, v1: int, v2: int | None = None, latest: bool = False):
        if latest:
            result = memos.diff_latest(item_id)
        else:
            if v2 is None:
                return {"status": "error", "message": "Provide v2 or use ?latest=true"}
            result = memos.diff(item_id, v1, v2)
        if result is None:
            return {"status": "not_found", "item_id": item_id}
        return {"status": "ok", "diff": result.to_dict()}

    @router.post("/api/v1/memory/{item_id}/rollback")
    async def api_version_rollback(item_id: str, body: dict):
        version = body.get("version")
        if version is None:
            return {"status": "error", "message": "version is required"}
        result = memos.rollback(item_id, version)
        if result is None:
            return {"status": "not_found", "item_id": item_id, "version": version}
        return {"status": "ok", "item_id": result.id, "content": result.content[:200], "tags": result.tags, "rolled_back_to": version}

    @router.get("/api/v1/snapshot")
    async def api_snapshot(at: float):
        versions = memos.snapshot_at(at)
        return {"timestamp": at, "total": len(versions), "memories": [v.to_dict() for v in versions[:200]]}

    @router.get("/api/v1/recall/at")
    async def api_recall_at(q: str, at: float, top: int = 5, min_score: float = 0.0):
        results = memos.recall_at(q, at, top=top, min_score=min_score)
        return {
            "query": q, "timestamp": at, "total": len(results),
            "results": [{"id": r.item.id, "content": r.item.content, "score": round(r.score, 4), "tags": r.item.tags, "match_reason": r.match_reason} for r in results],
        }

    @router.get("/api/v1/versioning/stats")
    async def api_versioning_stats():
        return memos.versioning_stats()

    @router.post("/api/v1/versioning/gc")
    async def api_versioning_gc(body: dict = None):
        body = body or {}
        removed = memos.versioning_gc(max_age_days=body.get("max_age_days", 90.0), keep_latest=body.get("keep_latest", 3))
        return {"status": "ok", "removed": removed}

    @router.get("/api/v1/recall/at/stream")
    async def api_recall_at_stream(q: str, at: float, top: int = 5, min_score: float = 0.0):
        """Stream time-travel recall results as SSE events."""
        from ..sse import sse_stream
        import asyncio as _asyncio
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

    @router.post("/api/v1/feedback")
    async def api_record_feedback(body: dict):
        item_id, feedback = body.get("item_id"), body.get("feedback")
        if not item_id or not feedback:
            return {"status": "error", "message": "item_id and feedback are required"}
        try:
            entry = memos.record_feedback(
                item_id=item_id, feedback=feedback,
                query=body.get("query", ""), score_at_recall=body.get("score_at_recall", 0.0),
                agent_id=body.get("agent_id", ""),
            )
            return {"status": "ok", "feedback": entry.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.get("/api/v1/feedback")
    async def api_list_feedback(item_id: str | None = None, limit: int = 100):
        entries = memos.get_feedback(item_id=item_id, limit=limit)
        return {"feedback": [e.to_dict() for e in entries], "total": len(entries)}

    @router.get("/api/v1/feedback/stats")
    async def api_feedback_stats():
        return memos.feedback_stats().to_dict()

    # ── Decay & Reinforce ─────────────────────────────────────

    @router.post("/api/v1/decay/run")
    async def api_decay_run(body: dict = None):
        body = body or {}
        items = memos._store.list_all(namespace=memos._namespace)
        report = memos._decay.run_decay(items, min_age_days=body.get("min_age_days"), floor=body.get("floor"), dry_run=body.get("dry_run", True))
        if not body.get("dry_run", True):
            for item in items:
                memos._store.upsert(item, namespace=memos._namespace)
        return {
            "status": "ok", "total": report.total, "decayed": report.decayed,
            "avg_importance_before": round(report.avg_importance_before, 4),
            "avg_importance_after": round(report.avg_importance_after, 4),
            "details": report.details[:50],
        }

    @router.post("/api/v1/memories/{memory_id}/reinforce")
    async def api_reinforce(memory_id: str, body: dict = None):
        body = body or {}
        item = memos._store.get(memory_id, namespace=memos._namespace)
        if item is None:
            return {"status": "error", "message": f"Memory not found: {memory_id}"}
        old_imp = item.importance
        new_imp = memos._decay.reinforce(item, strength=body.get("strength"))
        memos._store.upsert(item, namespace=memos._namespace)
        return {"status": "ok", "id": item.id, "importance_before": round(old_imp, 4), "importance_after": round(new_imp, 4)}

    # ── Compress ──────────────────────────────────────────────

    @router.post("/api/v1/compress")
    async def api_compress(body: dict = None):
        body = body or {}
        result = memos.compress(threshold=float(body.get("threshold", 0.1)), dry_run=bool(body.get("dry_run", True)))
        return {
            "status": "ok", "compressed_count": result.compressed_count, "summary_count": result.summary_count,
            "freed_bytes": result.freed_bytes, "groups_considered": result.groups_considered, "details": result.details,
        }

    # ── Dedup ─────────────────────────────────────────────────

    @router.post("/api/v1/dedup/check")
    async def api_dedup_check(body: dict):
        content_text = body.get("content", "")
        if not content_text:
            return {"status": "error", "message": "content is required"}
        result = memos.dedup_check(content_text, threshold=body.get("threshold"))
        resp = {"is_duplicate": result.is_duplicate, "reason": result.reason, "similarity": result.similarity}
        if result.match:
            resp["match"] = {"id": result.match.id, "content": result.match.content[:500], "tags": result.match.tags, "importance": result.match.importance}
        return resp

    @router.post("/api/v1/dedup/scan")
    async def api_dedup_scan(body: dict):
        result = memos.dedup_scan(fix=body.get("fix", False), threshold=body.get("threshold"))
        return {
            "total_scanned": result.total_scanned, "exact_duplicates": result.exact_duplicates,
            "near_duplicates": result.near_duplicates, "total_duplicates": result.total_duplicates,
            "fixed": result.fixed, "groups": result.groups[:50],
        }

    # ── Sync & Conflict ───────────────────────────────────────

    @router.post("/api/v1/sync/check")
    async def api_sync_check(body: dict):
        from ...conflict import ConflictDetector
        from ...sharing.models import MemoryEnvelope
        try:
            envelope = MemoryEnvelope.from_dict(body["envelope"])
        except (KeyError, ValueError) as exc:
            return {"status": "error", "message": f"Invalid envelope: {exc}"}
        if not envelope.validate():
            return {"status": "error", "message": "Envelope checksum validation failed"}
        detector = ConflictDetector()
        return {"status": "ok", **detector.detect(memos, envelope).to_dict()}

    @router.post("/api/v1/sync/apply")
    async def api_sync_apply(body: dict):
        from ...conflict import ConflictDetector, ResolutionStrategy
        from ...sharing.models import MemoryEnvelope
        try:
            envelope = MemoryEnvelope.from_dict(body["envelope"])
        except (KeyError, ValueError) as exc:
            return {"status": "error", "message": f"Invalid envelope: {exc}"}
        if not envelope.validate():
            return {"status": "error", "message": "Envelope checksum validation failed"}
        try:
            strategy = ResolutionStrategy(body.get("strategy", "merge"))
        except ValueError:
            return {"status": "error", "message": f"Invalid strategy. Use: local_wins, remote_wins, merge, manual"}
        detector = ConflictDetector()
        report = detector.detect(memos, envelope)
        if body.get("dry_run", False):
            detector.resolve(report.conflicts, strategy)
            return {"status": "ok", "dry_run": True, **report.to_dict()}
        return {"status": "ok", **detector.apply(memos, report, strategy).to_dict()}

    # ── Export ────────────────────────────────────────────────

    @router.get("/api/v1/export/markdown")
    async def api_export_markdown(output_dir: str | None = None, update: bool = False, wiki_dir: str | None = None):
        """Export MemOS knowledge as a downloadable markdown ZIP."""
        import tempfile
        import zipfile
        from pathlib import Path
        from fastapi.responses import FileResponse
        from ...export_markdown import MarkdownExporter

        export_root = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="memos-markdown-export-"))
        MarkdownExporter(memos, kg=_kg_bridge._kg if hasattr(_kg_bridge, "_kg") else None, wiki_dir=wiki_dir).export(str(export_root), update=update)
        zip_path = export_root.parent / f"{export_root.name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for file_path in sorted(export_root.rglob("*")):
                if file_path.is_file():
                    bundle.write(file_path, arcname=str(file_path.relative_to(export_root)))
        return FileResponse(str(zip_path), media_type="application/zip", filename=f"memos-markdown-export-{int(time.time())}.zip")

    @router.get("/api/v1/export/parquet")
    async def api_export_parquet(include_metadata: bool = True, compression: str = "zstd"):
        """Export all memories as a downloadable Parquet file."""
        import tempfile
        from fastapi.responses import FileResponse
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            result = memos.export_parquet(tmp.name, include_metadata=include_metadata, compression=compression)
            return FileResponse(
                tmp.name, media_type="application/octet-stream",
                filename=f"memos-export-{int(time.time())}.parquet",
                headers={"X-Memos-Total": str(result["total"]), "X-Memos-Size": str(result["size_bytes"])},
            )

    return router
