"""WebSocket, SSE event stream, event history, and subscription admin routes."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


def register_admin_events_routes(router: APIRouter, memos, key_manager) -> None:
    """Register WebSocket endpoint, SSE stream, event history, and subscription routes."""

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
                except json.JSONDecodeError:
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
        from ..errors import not_found

        ok = memos.events.unsubscribe_subscription(subscription_id)
        if not ok:
            return not_found(f"Subscription {subscription_id} not found")
        return {"status": "ok", "deleted": subscription_id}

    @router.get("/api/v1/events/stats")
    async def event_stats():
        return {"total_events": memos.events.total_events_emitted, "ws_clients": memos.events.client_count}
