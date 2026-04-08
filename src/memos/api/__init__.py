"""REST API for MemOS."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from .. import __version__ as MEMOS_VERSION
from ..core import MemOS, MemoryStats

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import StreamingResponse, HTMLResponse
except ImportError:  # pragma: no cover - optional server dependency
    FastAPI = None  # type: ignore[assignment]
    WebSocket = None  # type: ignore[assignment]
    WebSocketDisconnect = None  # type: ignore[assignment]
    StreamingResponse = None  # type: ignore[assignment]
    HTMLResponse = None  # type: ignore[assignment]


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
        # Parse date filters
        _after = body.get("filter_after")
        _before = body.get("filter_before")
        from datetime import datetime as _dt
        filter_after = _dt.fromisoformat(_after).timestamp() if _after else None
        filter_before = _dt.fromisoformat(_before).timestamp() if _before else None
        results = memos.recall(
            query=body["query"],
            top=body.get("top", 5),
            filter_tags=body.get("filter_tags"),
            min_score=body.get("min_score", 0.0),
            filter_after=filter_after,
            filter_before=filter_before,
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

    async def get_memory(item_id: str) -> dict:
        item = memos.get(item_id)
        if item is None:
            return {"status": "not_found", "message": f"Memory {item_id} not found"}
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
            result["ttl"] = item.ttl
            result["expires_at"] = item.expires_at
            result["is_expired"] = item.is_expired
        if item.metadata:
            # Exclude internal metadata keys
            public_meta = {k: v for k, v in item.metadata.items() if not k.startswith("_")}
            if public_meta:
                result["metadata"] = public_meta
        return {"status": "ok", "item": result}

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
        "get_memory": get_memory,
    }


def create_fastapi_app(memos: Optional[MemOS] = None, api_keys: Optional[list[str]] = None, rate_limit: int = 100, **kwargs) -> Any:
    """Create a FastAPI application for MemOS.
    
    Args:
        api_keys: List of valid API keys. If None/empty, auth is disabled.
        rate_limit: Max requests per minute per key (default 100).
    """
    if FastAPI is None:
        raise ImportError(
            "FastAPI is required for the server. "
            "Install with: pip install memos[server]"
        )

    if memos is None:
        memos = MemOS(**kwargs)

    app = FastAPI(
        title="MemOS",
        description="Memory Operating System for LLM Agents",
        version=MEMOS_VERSION,
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

    @app.get("/api/v1/memory/{item_id}")
    async def api_get_memory(item_id: str):
        return await routes["get_memory"](item_id)

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


    @app.get("/api/v1/tags")
    async def api_tags(sort: str = "count", limit: int = 0):
        """List all tags with memory counts."""
        tags = memos.list_tags(sort=sort, limit=limit)
        return [{"tag": t, "count": c} for t, c in tags]

    @app.post("/api/v1/tags/rename")
    async def api_tags_rename(body: dict):
        """Rename a tag across all memories."""
        old_tag = body.get("old")
        new_tag = body.get("new")
        if not old_tag or not new_tag:
            return {"error": "Both 'old' and 'new' tag names are required"}
        count = memos.rename_tag(old_tag, new_tag)
        return {"status": "ok", "renamed": count, "old_tag": old_tag, "new_tag": new_tag}

    @app.post("/api/v1/tags/delete")
    async def api_tags_delete(body: dict):
        """Delete a tag from all memories."""
        tag = body.get("tag")
        if not tag:
            return {"error": "Tag name is required"}
        count = memos.delete_tag(tag)
        return {"status": "ok", "deleted": count, "tag": tag}

    @app.get("/api/v1/graph")
    async def api_graph(min_shared_tags: int = 1, limit: int = 500):
        """Return memory graph: nodes + edges based on shared tags."""
        import time as _time
        items = memos._store.list_all(namespace=memos._namespace)
        now = _time.time()

        # Build nodes
        nodes = []
        for item in items[:limit]:
            if item.is_expired:
                continue
            age_days = (now - item.created_at) / 86400
            nodes.append({
                "id": item.id,
                "label": item.content[:60] + ("…" if len(item.content) > 60 else ""),
                "content": item.content,
                "tags": item.tags,
                "importance": item.importance,
                "relevance": item.relevance_score,
                "age_days": round(age_days, 1),
                "access_count": item.access_count,
                "primary_tag": item.tags[0] if item.tags else "__untagged__",
            })

        # Build edges based on shared tags
        edges = []
        tag_to_ids: dict[str, list[str]] = {}
        for n in nodes:
            for tag in n["tags"]:
                tag_to_ids.setdefault(tag, []).append(n["id"])

        seen = set()
        for tag, ids in tag_to_ids.items():
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    key = tuple(sorted([ids[i], ids[j]]))
                    if key not in seen:
                        seen.add(key)
                        edges.append({
                            "source": ids[i],
                            "target": ids[j],
                            "shared_tags": [tag],
                            "weight": 1,
                        })
                    else:
                        # Increment weight for multiple shared tags
                        for e in edges:
                            if e["source"] == key[0] and e["target"] == key[1]:
                                e["weight"] += 1
                                e["shared_tags"].append(tag)
                                break

        if min_shared_tags > 1:
            edges = [e for e in edges if e["weight"] >= min_shared_tags]

        stats = memos.stats()
        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_memories": stats.total_memories,
                "total_tags": stats.total_tags,
            },
        }

    @app.get("/", response_class=HTMLResponse)
    @app.get("/dashboard", response_class=HTMLResponse)
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
                    continue

                try:
                    payload = json.loads(data)
                except Exception:
                    await websocket.send_json({"type": "error", "message": "send JSON subscribe/unsubscribe commands or ping"})
                    continue

                action = payload.get("action")
                event_types = payload.get("event_types")
                tags = payload.get("tags")
                namespace = payload.get("namespace")

                if action in {"subscribe", "update"}:
                    memos.events.update_ws_client(
                        queue,
                        event_types=event_types,
                        namespaces=[namespace] if namespace else None,
                        tags=tags,
                        active=True,
                        label=payload.get("label", ""),
                    )
                    await websocket.send_json({"type": "subscribed", "subscription": memos.events.get_ws_client_subscription(queue)})
                elif action == "unsubscribe":
                    memos.events.update_ws_client(queue, active=False)
                    await websocket.send_json({"type": "unsubscribed", "subscription": memos.events.get_ws_client_subscription(queue)})
                elif action == "list":
                    await websocket.send_json({"type": "subscriptions", "current": memos.events.get_ws_client_subscription(queue), "all": memos.events.list_subscriptions()})
                else:
                    await websocket.send_json({"type": "error", "message": f"unknown action: {action}"})
        except WebSocketDisconnect:
            pass
        finally:
            sender_task.cancel()
            memos.events.remove_ws_client(queue)

    @app.get("/api/v1/events/stream")
    async def event_stream(
        event_types: str | None = None,
        tags: str | None = None,
        namespace: str | None = None,
    ):
        """Stream memory events as SSE with optional filters."""
        from .sse import SSEEvent
        from fastapi.responses import StreamingResponse
        import asyncio as _asyncio

        event_type_list = [t.strip() for t in event_types.split(",") if t.strip()] if event_types else None
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        ns_list = [namespace] if namespace else None
        queue = memos.events.add_ws_client(event_types=event_type_list, namespaces=ns_list, tags=tag_list)

        async def _gen():
            try:
                while True:
                    event = await queue.get()
                    payload = event.to_dict()
                    yield SSEEvent(event=event.type, data=json.dumps(payload), id=str(int(event.timestamp * 1000))).encode()
                    await _asyncio.sleep(0)
            finally:
                memos.events.remove_ws_client(queue)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/v1/events")
    async def event_history(
        event_type: str | None = None,
        limit: int = 50,
        namespace: str | None = None,
        tags: str | None = None,
    ):
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        events = memos.events.get_history(event_type=event_type, limit=limit, namespace=namespace, tags=tag_list)
        return {"events": [e.to_dict() for e in events]}

    @app.get("/api/v1/subscriptions")
    async def list_subscriptions():
        subscriptions = memos.events.list_subscriptions()
        return {"subscriptions": subscriptions, "total": len(subscriptions)}

    @app.delete("/api/v1/subscriptions/{subscription_id}")
    async def delete_subscription(subscription_id: str):
        ok = memos.events.unsubscribe_subscription(subscription_id)
        return {"status": "deleted" if ok else "not_found", "subscription_id": subscription_id}

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
            "version": MEMOS_VERSION,
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


    # ── Relevance Feedback API ──────────────────────────────

    @app.post("/api/v1/feedback")
    async def api_record_feedback(body: dict):
        """Record relevance feedback for a recalled memory.

        Body: {"item_id": "...", "feedback": "relevant|not-relevant",
               "query": "", "score_at_recall": 0.0, "agent_id": ""}
        """
        item_id = body.get("item_id")
        feedback = body.get("feedback")
        if not item_id or not feedback:
            return {"status": "error", "message": "item_id and feedback are required"}
        try:
            entry = memos.record_feedback(
                item_id=item_id,
                feedback=feedback,
                query=body.get("query", ""),
                score_at_recall=body.get("score_at_recall", 0.0),
                agent_id=body.get("agent_id", ""),
            )
            return {"status": "ok", "feedback": entry.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.get("/api/v1/feedback")
    async def api_list_feedback(item_id: str | None = None, limit: int = 100):
        """List feedback entries, optionally filtered by item_id."""
        entries = memos.get_feedback(item_id=item_id, limit=limit)
        return {
            "feedback": [e.to_dict() for e in entries],
            "total": len(entries),
        }

    @app.get("/api/v1/feedback/stats")
    async def api_feedback_stats():
        """Get aggregate feedback statistics."""
        stats = memos.feedback_stats()
        return stats.to_dict()

    return app
