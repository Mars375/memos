"""Tests for filtered event subscriptions and live streams."""

from __future__ import annotations

import asyncio
import json

import pytest
from starlette.testclient import TestClient

from memos import MemOS
from memos.api import create_fastapi_app
from memos.events import EventBus, MemoryEvent
from memos.subscriptions import SubscriptionFilter


class TestSubscriptionFilter:
    def test_matches_event_type_namespace_and_tags(self):
        event = MemoryEvent(
            type="learned",
            data={"id": "abc", "tags": ["infra", "pi"]},
            namespace="agent-a",
        )

        assert SubscriptionFilter.from_options(event_types=["learned"]).matches(event)
        assert SubscriptionFilter.from_options(namespaces=["agent-a"]).matches(event)
        assert SubscriptionFilter.from_options(tags=["infra"]).matches(event)
        assert not SubscriptionFilter.from_options(event_types=["forgotten"]).matches(event)
        assert not SubscriptionFilter.from_options(namespaces=["agent-b"]).matches(event)
        assert not SubscriptionFilter.from_options(tags=["other"]).matches(event)


class TestEventBusFilteredDelivery:
    def test_queue_subscription_filters_by_tag(self):
        bus = EventBus()
        q = bus.add_ws_client(tags=["infra"], namespaces=["agent-a"])

        bus.emit_sync("learned", {"id": "1", "tags": ["food"]}, namespace="agent-a")
        assert q.empty()

        bus.emit_sync("learned", {"id": "2", "tags": ["infra"]}, namespace="agent-a")
        assert not q.empty()
        event = q.get_nowait()
        assert event.data["id"] == "2"

    @pytest.mark.asyncio
    async def test_callback_subscription_filters_and_unsubscribes(self):
        bus = EventBus()
        received: list[MemoryEvent] = []

        async def handler(event: MemoryEvent):
            received.append(event)

        sub_id = bus.subscribe_filtered(
            handler,
            event_types=["learned"],
            namespaces=["agent-a"],
            tags=["infra"],
        )

        await bus.emit("learned", {"id": "1", "tags": ["infra"]}, namespace="agent-a")
        await bus.emit("learned", {"id": "2", "tags": ["other"]}, namespace="agent-a")

        assert len(received) == 1
        assert received[0].data["id"] == "1"
        assert bus.unsubscribe_subscription(sub_id)


class TestMemOSSubscriptions:
    @pytest.mark.asyncio
    async def test_programmatic_subscribe_receives_filtered_events(self):
        mem = MemOS(sanitize=False)
        received: list[MemoryEvent] = []

        async def handler(event: MemoryEvent):
            received.append(event)

        sub_id = mem.subscribe(handler, tags=["infra"])
        await mem.events.emit("learned", {"id": "1", "tags": ["infra"]}, namespace="agent-a")
        await mem.events.emit("learned", {"id": "2", "tags": ["food"]}, namespace="agent-a")

        assert len(received) == 1
        assert received[0].data["id"] == "1"
        assert mem.unsubscribe(sub_id)


class TestLiveStreams:
    def test_websocket_subscribe_filters_by_namespace_and_tag(self):
        mem = MemOS(sanitize=False)
        app = create_fastapi_app(memos=mem)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"action": "subscribe", "event_types": ["learned"], "tags": ["infra"], "namespace": "agent-a"})
            ack = ws.receive_json()
            assert ack["type"] == "subscribed"

            mem.namespace = "agent-a"
            mem.learn("Docker on Pi", tags=["infra"])

            event = json.loads(ws.receive_text())
            assert event["type"] == "learned"
            assert event["namespace"] == "agent-a"
            assert event["data"]["tags"] == ["infra"]

    def test_event_history_filters_by_tag(self):
        mem = MemOS(sanitize=False)
        app = create_fastapi_app(memos=mem)
        client = TestClient(app)

        mem.learn("Infra note", tags=["infra"])
        mem.learn("Food note", tags=["food"])

        resp = client.get("/api/v1/events?tags=infra")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) >= 1
        assert any(event["data"].get("tags") == ["infra"] for event in data["events"])
