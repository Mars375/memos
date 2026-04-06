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

    return {
        "learn": learn,
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

    @app.post("/api/v1/recall")
    async def api_recall(body: dict):
        return await routes["recall"](body)

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
            "version": "0.3.0",
            "auth_enabled": key_manager.auth_enabled,
            "active_keys": key_manager.key_count,
        }

    return app
