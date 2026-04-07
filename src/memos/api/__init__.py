"""REST API for MemOS."""

from __future__ import annotations

import time
from typing import Any, Optional

from ..core import MemOS, MemoryStats


def create_api(memos: MemOS) -> dict[str, Any]:
    """Create API route handlers. Can be used with any ASGI framework.
    
    For FastAPI, wrap these in router. For raw ASGI, use the asgi_app below.
    """
    async def learn(body: dict) -> dict:
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

    async def recall(body: dict) -> dict:
        results = memos.recall(
            query=body["query"],
            top=body.get("top", 5),
            filter_tags=body.get("filter_tags"),
            min_score=body.get("min_score", 0.0),
        )
        return {
            "status": "ok",
            "results": [
                {
                    "id": r.item.id,
                    "content": r.item.content,
                    "score": round(r.score, 4),
                    "tags": r.item.tags,
                    "match_reason": r.match_reason,
                    "age_days": round(
                        (__import__("time").time() - r.item.created_at) / 86400, 1
                    ),
                }
                for r in results
            ],
        }

    async def prune(body: dict) -> dict:
        pruned = memos.prune(
            threshold=body.get("threshold", 0.1),
            max_age_days=body.get("max_age_days", 90.0),
            dry_run=body.get("dry_run", False),
        )
        return {
            "status": "ok",
            "pruned_count": len(pruned),
            "pruned_ids": [item.id for item in pruned],
        }

    async def stats(_body: dict = None) -> dict:
        s = memos.stats()
        return {
            "total_memories": s.total_memories,
            "total_tags": s.total_tags,
            "avg_relevance": round(s.avg_relevance, 3),
            "avg_importance": round(s.avg_importance, 3),
            "oldest_memory_days": round(s.oldest_memory_days, 1),
            "newest_memory_days": round(s.newest_memory_days, 1),
            "decay_candidates": s.decay_candidates,
            "top_tags": s.top_tags,
        }

    async def search(body: dict) -> dict:
        items = memos.search(q=body["q"], limit=body.get("limit", 20))
        return {
            "status": "ok",
            "results": [
                {
                    "id": item.id,
                    "content": item.content[:200],
                    "tags": item.tags,
                    "importance": item.importance,
                }
                for item in items
            ],
        }

    async def delete_memory(item_id: str) -> dict:
        success = memos.forget(item_id)
        return {"status": "deleted" if success else "not_found"}

    async def batch_learn(body: dict) -> dict:
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

    return {
        "learn": learn,
        "batch_learn": batch_learn,
        "recall": recall,
        "prune": prune,
        "stats": stats,
        "search": search,
        "delete_memory": delete_memory,
    }


def create_fastapi_app(memos: Optional[MemOS] = None, api_keys: Optional[list[str]] = None, rate_limit: int = 100, **kwargs) -> Any:
    """Create a FastAPI application for MemOS.
    
    Args:
        api_keys: List of valid API keys. If None/empty, auth is disabled.
        rate_limit: Max requests per minute per key (default 100).
    """
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import StreamingResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for the server. "
            "Install with: pip install memos[server]"
        )

    if memos is None:
        memos = MemOS(**kwargs)

    app = FastAPI(
        title="MemOS",
        description="Memory Operating System for LLM Agents",
        version="0.1.0",
    )

    routes = create_api(memos)

    @app.post("/api/v1/learn")
    async def api_learn(body: dict):
        return await routes["learn"](body)

    @app.post("/api/v1/learn/batch")
    async def api_batch_learn(body: dict):
        """Batch learn — store multiple memories in one call.

        Body:
            items: list of dicts, each with content (required), tags, importance, metadata.
            continue_on_error: bool (default True) — skip invalid items vs raise.

        Returns:
            status, learned count, skipped count, errors, item details.
        """
        return await routes["batch_learn"](body)

    @app.post("/api/v1/recall")
    async def api_recall(body: dict):
        return await routes["recall"](body)

    # SSE Streaming Recall endpoint
    @app.get("/api/v1/recall/stream")
    async def api_recall_stream(
        q: str,
        top: int = 5,
        filter_tags: str | None = None,
        min_score: float = 0.0,
    ):
        """Stream recall results as Server-Sent Events (SSE).

        Each matching memory is sent as a separate SSE event, allowing
        clients to start processing results before the full search completes.

        Query params:
            q: The search query
            top: Maximum results to return (default 5)
            filter_tags: Comma-separated tag filter
            min_score: Minimum relevance score (default 0.0)
        """
        from .sse import sse_stream

        tags = [t.strip() for t in filter_tags.split(",") if t.strip()] if filter_tags else None
        recall_gen = memos.recall_stream(
            query=q, top=top, filter_tags=tags, min_score=min_score,
        )
        return StreamingResponse(
            sse_stream(recall_gen, q),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/v1/prune")
    async def api_prune(body: dict):
        return await routes["prune"](body)

    @app.get("/api/v1/stats")
    async def api_stats():
        return await routes["stats"]()

    @app.get("/api/v1/search")
    async def api_search(q: str, limit: int = 20):
        return await routes["search"]({"q": q, "limit": limit})

    @app.delete("/api/v1/memory/{item_id}")
    async def api_delete(item_id: str):
        return await routes["delete_memory"](item_id)

    # Auth & rate limiting
    from .auth import APIKeyManager, create_auth_middleware
    from .ratelimit import RateLimiter, create_rate_limit_middleware, DEFAULT_RULES
    key_manager = APIKeyManager(keys=api_keys)
    key_manager.rate_limiter.max_requests = rate_limit
    if key_manager.auth_enabled:
        app.middleware("http")(create_auth_middleware(key_manager))

    # Standalone per-endpoint rate limiter (works with or without auth)
    rate_limiter = RateLimiter(default_max=rate_limit, rules=DEFAULT_RULES)
    app.middleware("http")(create_rate_limit_middleware(rate_limiter))

    # Dashboard
    from ..web import DASHBOARD_HTML
    from fastapi.responses import HTMLResponse

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    # WebSocket endpoint for real-time events
    import asyncio

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        queue = memos.events.add_ws_client()

        async def sender():
            """Background task: send events from queue to WebSocket."""
            try:
                while True:
                    event = await queue.get()
                    await websocket.send_text(event.to_json())
            except Exception:
                pass

        sender_task = asyncio.create_task(sender())
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data.startswith("filter:"):
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            sender_task.cancel()
            memos.events.remove_ws_client(queue)

    @app.get("/api/v1/events")
    async def event_history(event_type: str | None = None, limit: int = 50, namespace: str | None = None):
        events = memos.events.get_history(event_type=event_type, limit=limit, namespace=namespace)
        return {"events": [e.to_dict() for e in events]}

    @app.get("/api/v1/events/stats")
    async def event_stats():
        return {
            "total_events": memos.events.total_events_emitted,
            "ws_clients": memos.events.client_count,
        }

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.16.0",
            "auth_enabled": key_manager.auth_enabled,
            "active_keys": key_manager.key_count,
            "rate_limiting": True,
        }

    @app.get("/api/v1/rate-limit/status")
    async def api_rate_limit_status(request):
        """Get current rate limit status for the requesting client."""
        return rate_limiter.get_status(request)

    # Parquet export
    @app.get("/api/v1/export/parquet")
    async def api_export_parquet(include_metadata: bool = True, compression: str = "zstd"):
        """Export all memories as a downloadable Parquet file."""
        import tempfile
        from fastapi.responses import FileResponse

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            result = memos.export_parquet(
                tmp.name,
                include_metadata=include_metadata,
                compression=compression,
            )
            return FileResponse(
                tmp.name,
                media_type="application/octet-stream",
                filename=f"memos-export-{int(time.time())}.parquet",
                headers={"X-Memos-Total": str(result["total"]), "X-Memos-Size": str(result["size_bytes"])},
            )

    # Async consolidation
    @app.post("/api/v1/consolidate")
    async def api_consolidate(body: dict):
        """Run consolidation (sync or async).

        Body:
            async: bool (default False) — run in background.
            similarity_threshold: float (default 0.75).
            merge_content: bool (default False).
            dry_run: bool (default False).
        """
        threshold = body.get("similarity_threshold", 0.75)
        merge = body.get("merge_content", False)
        dry = body.get("dry_run", False)
        is_async = body.get("async", False)

        if is_async:
            handle = await memos.consolidate_async(
                similarity_threshold=threshold,
                merge_content=merge,
                dry_run=dry,
            )
            return {"status": "started", "task_id": handle.task_id}
        else:
            result = memos.consolidate(
                similarity_threshold=threshold,
                merge_content=merge,
                dry_run=dry,
            )
            return {
                "status": "completed",
                "groups_found": result.groups_found,
                "memories_merged": result.memories_merged,
                "space_freed": result.space_freed,
            }

    @app.get("/api/v1/consolidate/{task_id}")
    async def api_consolidate_status(task_id: str):
        """Get status of an async consolidation task."""
        status = memos.consolidation_status(task_id)
        if not status:
            return {"status": "not_found", "task_id": task_id}
        return status

    @app.get("/api/v1/consolidate")
    async def api_consolidate_list():
        """List all async consolidation tasks."""
        return {"tasks": memos.consolidation_tasks()}


    # ── Versioning API ───────────────────────────────────────

    @app.get("/api/v1/memory/{item_id}/history")
    async def api_version_history(item_id: str):
        """Get version history for a memory item."""
        versions = memos.history(item_id)
        return {
            "item_id": item_id,
            "versions": [v.to_dict() for v in versions],
            "total": len(versions),
        }

    @app.get("/api/v1/memory/{item_id}/version/{version_number}")
    async def api_version_get(item_id: str, version_number: int):
        """Get a specific version of a memory item."""
        v = memos.get_version(item_id, version_number)
        if v is None:
            return {"status": "not_found", "item_id": item_id, "version": version_number}
        return {"status": "ok", "version": v.to_dict()}

    @app.get("/api/v1/memory/{item_id}/diff")
    async def api_version_diff(item_id: str, v1: int, v2: int | None = None, latest: bool = False):
        """Diff between two versions. Use ?latest=true for last two versions."""
        if latest:
            result = memos.diff_latest(item_id)
        else:
            if v2 is None:
                return {"status": "error", "message": "Provide v2 or use ?latest=true"}
            result = memos.diff(item_id, v1, v2)
        if result is None:
            return {"status": "not_found", "item_id": item_id}
        return {"status": "ok", "diff": result.to_dict()}

    @app.post("/api/v1/memory/{item_id}/rollback")
    async def api_version_rollback(item_id: str, body: dict):
        """Roll back a memory to a specific version.

        Body: {"version": <int>}
        """
        version = body.get("version")
        if version is None:
            return {"status": "error", "message": "version is required"}
        result = memos.rollback(item_id, version)
        if result is None:
            return {"status": "not_found", "item_id": item_id, "version": version}
        return {
            "status": "ok",
            "item_id": result.id,
            "content": result.content[:200],
            "tags": result.tags,
            "rolled_back_to": version,
        }

    @app.get("/api/v1/snapshot")
    async def api_snapshot(at: float):
        """Get a snapshot of all memories at a given timestamp (epoch)."""
        versions = memos.snapshot_at(at)
        return {
            "timestamp": at,
            "total": len(versions),
            "memories": [v.to_dict() for v in versions[:200]],
        }

    @app.get("/api/v1/recall/at")
    async def api_recall_at(q: str, at: float, top: int = 5, min_score: float = 0.0):
        """Time-travel recall: query memories as they were at a given timestamp."""
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

    @app.get("/api/v1/versioning/stats")
    async def api_versioning_stats():
        """Get versioning statistics."""
        return memos.versioning_stats()

    @app.post("/api/v1/versioning/gc")
    async def api_versioning_gc(body: dict = None):
        """Garbage collect old versions.

        Body: {"max_age_days": 90, "keep_latest": 3}
        """
        body = body or {}
        removed = memos.versioning_gc(
            max_age_days=body.get("max_age_days", 90.0),
            keep_latest=body.get("keep_latest", 3),
        )
        return {"status": "ok", "removed": removed}

    # ── Streaming time-travel recall ──────────────────────────

    @app.get("/api/v1/recall/at/stream")
    async def api_recall_at_stream(q: str, at: float, top: int = 5, min_score: float = 0.0):
        """Stream time-travel recall results as SSE events."""
        from .sse import sse_stream, SSEEvent, format_recall_event, format_done_event
        import asyncio as _asyncio

        results = memos.recall_at(q, at, top=top, min_score=min_score)

        async def _gen():
            for r in results:
                yield r
                await _asyncio.sleep(0)

        return StreamingResponse(
            sse_stream(_gen(), q),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Namespace ACL API ───────────────────────────────────

    @app.post("/api/v1/namespaces/{namespace}/grant")
    async def api_acl_grant(namespace: str, body: dict):
        """Grant an agent access to a namespace.

        Body: {"agent_id": "...", "role": "owner|writer|reader|denied",
               "expires_at": null}
        """
        agent_id = body.get("agent_id")
        role = body.get("role")
        if not agent_id or not role:
            return {"status": "error", "message": "agent_id and role are required"}
        try:
            policy = memos.grant_namespace_access(
                agent_id, namespace, role,
                granted_by=body.get("granted_by", ""),
                expires_at=body.get("expires_at"),
            )
            return {"status": "ok", "policy": policy}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/namespaces/{namespace}/revoke")
    async def api_acl_revoke(namespace: str, body: dict):
        """Revoke an agent's access to a namespace.

        Body: {"agent_id": "..."}
        """
        agent_id = body.get("agent_id")
        if not agent_id:
            return {"status": "error", "message": "agent_id is required"}
        success = memos.revoke_namespace_access(agent_id, namespace)
        return {"status": "revoked" if success else "not_found"}

    @app.get("/api/v1/namespaces/{namespace}/policies")
    async def api_acl_list(namespace: str):
        """List all ACL policies for a namespace."""
        policies = memos.list_namespace_policies(namespace=namespace)
        return {"namespace": namespace, "policies": policies, "total": len(policies)}

    @app.get("/api/v1/namespaces")
    async def api_acl_all_policies():
        """List all ACL policies across all namespaces."""
        policies = memos.list_namespace_policies()
        return {"policies": policies, "total": len(policies)}

    @app.get("/api/v1/namespaces/acl/stats")
    async def api_acl_stats():
        """Get namespace ACL statistics."""
        return memos.namespace_acl_stats()


    # ── Multi-Agent Sharing API ─────────────────────────────

    @app.post("/api/v1/share/offer")
    async def api_share_offer(body: dict):
        """Offer to share memories with another agent.

        Body: {"target_agent": "...", "scope": "items|tag|namespace",
               "scope_key": "", "permission": "read|read_write|admin",
               "expires_at": null}
        """
        from ..sharing.models import ShareScope, SharePermission
        try:
            scope = ShareScope(body.get("scope", "items"))
            permission = SharePermission(body.get("permission", "read"))
        except ValueError as e:
            return {"status": "error", "message": str(e)}
        try:
            req = memos.share_with(
                body["target_agent"],
                scope=scope,
                scope_key=body.get("scope_key", ""),
                permission=permission,
                expires_at=body.get("expires_at"),
            )
            return {"status": "ok", "share": req.to_dict()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/share/{share_id}/accept")
    async def api_share_accept(share_id: str):
        """Accept a pending share."""
        try:
            req = memos.accept_share(share_id)
            return {"status": "ok", "share": req.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/share/{share_id}/reject")
    async def api_share_reject(share_id: str):
        """Reject a pending share."""
        try:
            req = memos.reject_share(share_id)
            return {"status": "ok", "share": req.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/share/{share_id}/revoke")
    async def api_share_revoke(share_id: str):
        """Revoke a share."""
        try:
            req = memos.revoke_share(share_id)
            return {"status": "ok", "share": req.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.get("/api/v1/share/{share_id}/export")
    async def api_share_export(share_id: str):
        """Export memories for an accepted share as a JSON envelope."""
        try:
            envelope = memos.export_shared(share_id)
            return {"status": "ok", "envelope": envelope.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/share/import")
    async def api_share_import(body: dict):
        """Import memories from a received envelope.

        Body: {"envelope": {"source_agent": "...", "target_agent": "...", "memories": [...]}}
        """
        from ..sharing.models import MemoryEnvelope
        try:
            envelope = MemoryEnvelope.from_dict(body["envelope"])
            learned = memos.import_shared(envelope)
            return {
                "status": "ok",
                "imported": len(learned),
                "ids": [i.id for i in learned],
            }
        except (ValueError, KeyError) as e:
            return {"status": "error", "message": str(e)}

    @app.get("/api/v1/shares")
    async def api_shares_list(agent: str | None = None, status: str | None = None):
        """List shares, optionally filtered."""
        from ..sharing.models import ShareStatus as SS
        st = SS(status) if status else None
        shares = memos.list_shares(agent=agent, status=st)
        return {
            "shares": [s.to_dict() for s in shares],
            "total": len(shares),
        }

    @app.get("/api/v1/sharing/stats")
    async def api_sharing_stats():
        """Get sharing statistics."""
        return memos.sharing_stats()

    return app
