"""Stats, analytics, ingest, mine, events, sharing, namespaces, health routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse


def create_admin_router(memos, _kg, key_manager, rate_limiter, MEMOS_VERSION: str, DASHBOARD_HTML: str) -> APIRouter:
    """Create the admin/ops API router."""
    router = APIRouter()

    # ── Stats & Analytics ────────────────────────────────────

    @router.get("/api/v1/stats")
    async def api_stats():
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

    @router.get("/api/v1/analytics/summary")
    async def api_analytics_summary(days: int = 7):
        return {"status": "ok", **memos.analytics.summary(days=days)}

    @router.get("/api/v1/analytics/top")
    async def api_analytics_top(n: int = 20):
        return {"status": "ok", "results": memos.analytics.top_recalled(n=n)}

    @router.get("/api/v1/analytics/patterns")
    async def api_analytics_patterns(n: int = 20):
        return {"status": "ok", "results": memos.analytics.query_patterns(n=n)}

    @router.get("/api/v1/analytics/latency")
    async def api_analytics_latency():
        return {"status": "ok", "results": memos.analytics.latency_stats()}

    @router.get("/api/v1/analytics/success-rate")
    async def api_analytics_success_rate(days: int = 7):
        return {"status": "ok", **memos.analytics.recall_success_rate_stats(days=days)}

    @router.get("/api/v1/analytics/daily")
    async def api_analytics_daily(days: int = 30):
        return {"status": "ok", "results": memos.analytics.daily_activity(days=days)}

    @router.get("/api/v1/analytics/zero-result")
    async def api_analytics_zero_result(n: int = 20):
        return {"status": "ok", "results": memos.analytics.zero_result_queries(n=n)}

    # ── Ingest & Mine ─────────────────────────────────────────

    @router.post("/api/v1/ingest/url")
    async def api_ingest_url(body: dict):
        """Fetch a URL and ingest it into memory."""
        url = body.get("url", "").strip()
        if not url:
            return {"status": "error", "message": "url is required"}
        result = memos.ingest_url(
            url,
            tags=body.get("tags"),
            importance=float(body.get("importance", 0.5)),
            max_chunk=int(body.get("max_chunk", 2000)),
            dry_run=bool(body.get("dry_run", False)),
        )
        head_meta = result.chunks[0].get("metadata", {}) if result.chunks else {}
        payload = {
            "status": "ok" if not result.errors else "partial",
            "url": url,
            "total_chunks": result.total_chunks,
            "skipped": result.skipped,
            "errors": result.errors,
            "source_type": head_meta.get("source_type"),
            "title": head_meta.get("title"),
        }
        if body.get("dry_run"):
            payload["chunks"] = result.chunks
        return payload

    @router.post("/api/v1/mine/conversation")
    async def api_mine_conversation(body: dict):
        """Mine a conversation transcript. Accepts text or server-side path."""
        import os
        import tempfile

        from ...ingest.conversation import ConversationMiner

        text_body = body.get("text", "") or body.get("content", "")
        path_body = body.get("path", "")
        if not text_body and not path_body:
            return {"status": "error", "message": "Either 'text'/'content' or 'path' is required"}

        per_speaker = bool(body.get("per_speaker", True))
        namespace_prefix = str(body.get("namespace_prefix", "conv"))
        extra_tags = body.get("tags") or []
        importance = float(body.get("importance", 0.6))
        dry_run = bool(body.get("dry_run", False))
        miner = ConversationMiner(memos, dry_run=dry_run)

        if text_body:
            try:
                fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="memos_conv_")
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(text_body)
                result = miner.mine_conversation(
                    tmp_path,
                    namespace_prefix=namespace_prefix,
                    per_speaker=per_speaker,
                    tags=extra_tags or None,
                    importance=importance,
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        else:
            result = miner.mine_conversation(
                path_body,
                namespace_prefix=namespace_prefix,
                per_speaker=per_speaker,
                tags=extra_tags or None,
                importance=importance,
            )

        return {
            "status": "ok" if not result.errors else "partial",
            "imported": result.imported,
            "skipped_duplicates": result.skipped_duplicates,
            "skipped_empty": result.skipped_empty,
            "speakers": result.speakers,
            "errors": result.errors,
        }

    # ── Dashboard ─────────────────────────────────────────────

    @router.get("/", response_class=HTMLResponse)
    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    # ── WebSocket ─────────────────────────────────────────────

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        import asyncio

        await websocket.accept()
        queue = memos.events.add_ws_client()

        async def sender():
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
                    await websocket.send_json(
                        {"type": "error", "message": "send JSON subscribe/unsubscribe commands or ping"}
                    )
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
                    await websocket.send_json(
                        {"type": "subscribed", "subscription": memos.events.get_ws_client_subscription(queue)}
                    )
                elif action == "unsubscribe":
                    memos.events.update_ws_client(queue, active=False)
                    await websocket.send_json(
                        {"type": "unsubscribed", "subscription": memos.events.get_ws_client_subscription(queue)}
                    )
                elif action == "list":
                    await websocket.send_json(
                        {
                            "type": "subscriptions",
                            "current": memos.events.get_ws_client_subscription(queue),
                            "all": memos.events.list_subscriptions(),
                        }
                    )
                else:
                    await websocket.send_json({"type": "error", "message": f"unknown action: {action}"})
        except WebSocketDisconnect:
            pass
        finally:
            sender_task.cancel()
            memos.events.remove_ws_client(queue)

    # ── Events ────────────────────────────────────────────────

    @router.get("/api/v1/events/stream")
    async def event_stream(event_types: str | None = None, tags: str | None = None, namespace: str | None = None):
        """Stream memory events as SSE with optional filters."""
        import asyncio as _asyncio

        from ..sse import SSEEvent

        event_type_list = [t.strip() for t in event_types.split(",") if t.strip()] if event_types else None
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        ns_list = [namespace] if namespace else None
        queue = memos.events.add_ws_client(event_types=event_type_list, namespaces=ns_list, tags=tag_list)

        async def _gen():
            try:
                while True:
                    event = await queue.get()
                    payload = event.to_dict()
                    yield SSEEvent(
                        event=event.type, data=json.dumps(payload), id=str(int(event.timestamp * 1000))
                    ).encode()
                    await _asyncio.sleep(0)
            finally:
                memos.events.remove_ws_client(queue)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/v1/events")
    async def event_history(
        event_type: str | None = None, limit: int = 50, namespace: str | None = None, tags: str | None = None
    ):
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        events = memos.events.get_history(event_type=event_type, limit=limit, namespace=namespace, tags=tag_list)
        return {"events": [e.to_dict() for e in events]}

    @router.get("/api/v1/subscriptions")
    async def list_subscriptions():
        subscriptions = memos.events.list_subscriptions()
        return {"subscriptions": subscriptions, "total": len(subscriptions)}

    @router.delete("/api/v1/subscriptions/{subscription_id}")
    async def delete_subscription(subscription_id: str):
        ok = memos.events.unsubscribe_subscription(subscription_id)
        return {"status": "deleted" if ok else "not_found", "subscription_id": subscription_id}

    @router.get("/api/v1/events/stats")
    async def event_stats():
        return {"total_events": memos.events.total_events_emitted, "ws_clients": memos.events.client_count}

    # ── Health & Rate Limit ───────────────────────────────────

    @router.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": MEMOS_VERSION,
            "auth_enabled": key_manager.auth_enabled,
            "active_keys": key_manager.key_count,
            "rate_limiting": True,
        }

    @router.get("/api/v1/rate-limit/status")
    async def api_rate_limit_status(request):
        return rate_limiter.get_status(request)

    # ── Namespace ACL ─────────────────────────────────────────

    @router.post("/api/v1/namespaces/{namespace}/grant")
    async def api_acl_grant(namespace: str, body: dict):
        agent_id, role = body.get("agent_id"), body.get("role")
        if not agent_id or not role:
            return {"status": "error", "message": "agent_id and role are required"}
        try:
            policy = memos.grant_namespace_access(
                agent_id, namespace, role, granted_by=body.get("granted_by", ""), expires_at=body.get("expires_at")
            )
            return {"status": "ok", "policy": policy}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/v1/namespaces/{namespace}/revoke")
    async def api_acl_revoke(namespace: str, body: dict):
        agent_id = body.get("agent_id")
        if not agent_id:
            return {"status": "error", "message": "agent_id is required"}
        return {"status": "revoked" if memos.revoke_namespace_access(agent_id, namespace) else "not_found"}

    @router.get("/api/v1/namespaces/{namespace}/policies")
    async def api_acl_list(namespace: str):
        policies = memos.list_namespace_policies(namespace=namespace)
        return {"namespace": namespace, "policies": policies, "total": len(policies)}

    @router.get("/api/v1/namespaces")
    async def api_acl_all_policies():
        policies = memos.list_namespace_policies()
        return {"policies": policies, "total": len(policies)}

    @router.get("/api/v1/namespaces/acl/stats")
    async def api_acl_stats():
        return memos.namespace_acl_stats()

    # ── Multi-Agent Sharing ───────────────────────────────────

    @router.post("/api/v1/share/offer")
    async def api_share_offer(body: dict):
        from ...sharing.models import SharePermission, ShareScope

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

    @router.post("/api/v1/share/{share_id}/accept")
    async def api_share_accept(share_id: str):
        try:
            return {"status": "ok", "share": memos.accept_share(share_id).to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/v1/share/{share_id}/reject")
    async def api_share_reject(share_id: str):
        try:
            return {"status": "ok", "share": memos.reject_share(share_id).to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/v1/share/{share_id}/revoke")
    async def api_share_revoke(share_id: str):
        try:
            return {"status": "ok", "share": memos.revoke_share(share_id).to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.get("/api/v1/share/{share_id}/export")
    async def api_share_export(share_id: str):
        try:
            return {"status": "ok", "envelope": memos.export_shared(share_id).to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/v1/share/import")
    async def api_share_import(body: dict):
        from ...sharing.models import MemoryEnvelope

        try:
            envelope = MemoryEnvelope.from_dict(body["envelope"])
            learned = memos.import_shared(envelope)
            return {"status": "ok", "imported": len(learned), "ids": [i.id for i in learned]}
        except (ValueError, KeyError) as e:
            return {"status": "error", "message": str(e)}

    @router.get("/api/v1/shares")
    async def api_shares_list(agent: str | None = None, status: str | None = None):
        from ...sharing.models import ShareStatus as SS

        st = SS(status) if status else None
        shares = memos.list_shares(agent=agent, status=st)
        return {"shares": [s.to_dict() for s in shares], "total": len(shares)}

    @router.get("/api/v1/sharing/stats")
    async def api_sharing_stats():
        return memos.sharing_stats()

    return router
