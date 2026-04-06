"""REST API for MemOS."""

from __future__ import annotations

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
    key_manager = APIKeyManager(keys=api_keys)
    key_manager.rate_limiter.max_requests = rate_limit
    if key_manager.auth_enabled:
        app.middleware("http")(create_auth_middleware(key_manager))

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
            "version": "0.10.0",
            "auth_enabled": key_manager.auth_enabled,
            "active_keys": key_manager.key_count,
        }

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

    return app
