"""Stats, analytics, ingest, mine, events, sharing, namespaces, health routes."""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse

from ..errors import error_response, not_found
from ..schemas import (
    ACLGrantRequest,
    ACLRevokeRequest,
    IngestURLRequest,
    MineConversationRequest,
    ShareImportRequest,
    ShareOfferRequest,
)

logger = logging.getLogger(__name__)

# Module-level start time for uptime calculation
_start_time: float = time.time()


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
    async def api_ingest_url(body: IngestURLRequest):
        """Fetch a URL and ingest it into memory."""
        result = memos.ingest_url(
            body.url,
            tags=body.tags,
            importance=body.importance,
            max_chunk=body.max_chunk,
            dry_run=body.dry_run,
        )
        head_meta = result.chunks[0].get("metadata", {}) if result.chunks else {}
        payload = {
            "status": "ok" if not result.errors else "partial",
            "url": body.url,
            "total_chunks": result.total_chunks,
            "skipped": result.skipped,
            "errors": result.errors,
            "source_type": head_meta.get("source_type"),
            "title": head_meta.get("title"),
        }
        if body.dry_run:
            payload["chunks"] = result.chunks
        return payload

    @router.post("/api/v1/mine/conversation")
    async def api_mine_conversation(body: MineConversationRequest):
        """Mine a conversation transcript. Accepts text or server-side path."""
        import asyncio
        import os
        import tempfile

        from ...ingest.conversation import ConversationMiner

        text_body = body.text or body.content or ""
        path_body = body.path or ""

        per_speaker = body.per_speaker
        namespace_prefix = body.namespace_prefix
        extra_tags = body.tags or []
        importance = body.importance
        dry_run = body.dry_run

        def _blocking_mine():
            miner = ConversationMiner(memos, dry_run=dry_run)
            if text_body:
                try:
                    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="memos_conv_")
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        fh.write(text_body)
                    return miner.mine_conversation(
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
                        logger.debug("Temp file cleanup failed for %s", tmp_path, exc_info=True)
            return miner.mine_conversation(
                path_body,
                namespace_prefix=namespace_prefix,
                per_speaker=per_speaker,
                tags=extra_tags or None,
                importance=importance,
            )

        result = await asyncio.to_thread(_blocking_mine)
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
        """WebSocket endpoint for live event subscriptions.

        When authentication is enabled (one or more API keys configured),
        callers must supply a valid ``api_key`` query parameter, e.g.
        ``ws://host/ws?api_key=sk-...``.  Connections without a valid key
        are rejected with code 4001.
        """
        import asyncio

        # ── WebSocket authentication ──────────────────────────
        if key_manager.auth_enabled:
            ws_key = websocket.query_params.get("api_key", "")
            if not ws_key or not key_manager.validate(ws_key):
                await websocket.close(code=4001, reason="Unauthorized: invalid or missing api_key")
                return

        await websocket.accept()
        queue = memos.events.add_ws_client()

        async def sender():
            try:
                while True:
                    event = await queue.get()
                    await websocket.send_text(event.to_json())
            except Exception:
                logger.debug("WebSocket sender loop ended", exc_info=True)
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
        if not ok:
            return not_found(f"Subscription {subscription_id} not found")
        return {"status": "ok", "deleted": subscription_id}

    @router.get("/api/v1/events/stats")
    async def event_stats():
        return {"total_events": memos.events.total_events_emitted, "ws_clients": memos.events.client_count}

    # ── Health & Rate Limit ───────────────────────────────────

    @router.get("/health")
    async def health():
        """Public liveness probe — intentionally minimal.

        Auth state (whether keys are configured, how many) is NOT exposed
        here because this endpoint is unauthenticated.  See
        ``/api/v1/health`` for the authenticated variant.
        """
        return {
            "status": "ok",
            "version": MEMOS_VERSION,
        }

    @router.get("/api/v1/health")
    async def api_v1_health():
        """Authenticated health check with version, uptime, and auth state."""
        uptime = time.time() - _start_time
        try:
            import importlib.metadata

            version = importlib.metadata.version("memos")
        except Exception:
            version = MEMOS_VERSION
        return {
            "status": "ok",
            "version": version,
            "uptime": round(uptime, 2),
            "auth_enabled": key_manager.auth_enabled,
            "active_keys": key_manager.key_count,
        }

    @router.get("/api/v1/rate-limit/status")
    async def api_rate_limit_status(request):
        return rate_limiter.get_status(request)

    # ── Namespace ACL ─────────────────────────────────────────

    @router.post("/api/v1/namespaces/{namespace}/grant")
    async def api_acl_grant(namespace: str, body: ACLGrantRequest):
        try:
            policy = memos.grant_namespace_access(
                body.agent_id,
                namespace,
                body.role,
                granted_by=body.granted_by,
                expires_at=body.expires_at,
            )
            return {"status": "ok", "policy": policy}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)

    @router.post("/api/v1/namespaces/{namespace}/revoke")
    async def api_acl_revoke(namespace: str, body: ACLRevokeRequest):
        revoked = memos.revoke_namespace_access(body.agent_id, namespace)
        if not revoked:
            return not_found(f"No access found for {body.agent_id}")
        return {"status": "ok", "revoked": body.agent_id}

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
    async def api_share_offer(body: ShareOfferRequest):
        from ...sharing.models import SharePermission, ShareScope

        scope = ShareScope(body.scope)
        permission = SharePermission(body.permission)
        try:
            req = memos.share_with(
                body.target_agent,
                scope=scope,
                scope_key=body.scope_key,
                permission=permission,
                expires_at=body.expires_at,
            )
            return {"status": "ok", "share": req.to_dict()}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)

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
    async def api_share_import(body: ShareImportRequest):
        from ...sharing.models import MemoryEnvelope

        try:
            envelope = MemoryEnvelope.from_dict(body.envelope)
            learned = memos.import_shared(envelope)
            return {"status": "ok", "imported": len(learned), "ids": [i.id for i in learned]}
        except (ValueError, KeyError) as exc:
            return error_response(str(exc), status_code=400)

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
