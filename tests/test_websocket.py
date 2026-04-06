"""Tests for WebSocket event subscriptions."""
import asyncio
import pytest
from memos import MemOS
from memos.events import EventBus, MemoryEvent


class TestEventBus:
    """Unit tests for EventBus."""

    def test_create_bus(self):
        bus = EventBus()
        assert bus.client_count == 0
        assert bus.total_events_emitted == 0

    def test_emit_sync_adds_to_history(self):
        bus = EventBus()
        bus.emit_sync("learned", {"id": "abc123"})
        assert len(bus.get_history()) == 1
        event = bus.get_history()[0]
        assert event.type == "learned"
        assert event.data == {"id": "abc123"}

    def test_history_limit(self):
        bus = EventBus(max_history=5)
        for i in range(10):
            bus.emit_sync("learned", {"id": str(i)})
        assert len(bus.get_history()) == 5
        assert bus.get_history()[0].data["id"] == "5"

    def test_history_filter_by_type(self):
        bus = EventBus()
        bus.emit_sync("learned", {"id": "1"})
        bus.emit_sync("forgotten", {"id": "2"})
        bus.emit_sync("learned", {"id": "3"})
        learned = bus.get_history(event_type="learned")
        assert len(learned) == 2

    def test_history_filter_by_namespace(self):
        bus = EventBus()
        bus.emit_sync("learned", {"id": "1"}, namespace="agent-a")
        bus.emit_sync("learned", {"id": "2"}, namespace="agent-b")
        result = bus.get_history(namespace="agent-a")
        assert len(result) == 1

    def test_add_remove_ws_client(self):
        bus = EventBus()
        q = bus.add_ws_client()
        assert bus.client_count == 1
        bus.remove_ws_client(q)
        assert bus.client_count == 0

    def test_emit_sync_pushes_to_ws_queues(self):
        bus = EventBus()
        q = bus.add_ws_client()
        bus.emit_sync("learned", {"id": "test"})
        assert not q.empty()
        event = q.get_nowait()
        assert event.type == "learned"

    def test_ws_queue_overflow_drops_client(self):
        bus = EventBus()
        q = bus.add_ws_client()  # maxsize=500
        for i in range(501):
            bus.emit_sync("learned", {"id": str(i)})
        assert bus.client_count == 0

    def test_clear(self):
        bus = EventBus()
        bus.emit_sync("learned", {"id": "1"})
        bus.add_ws_client()
        bus.clear()
        assert bus.total_events_emitted == 0
        assert bus.client_count == 0

    def test_memory_event_to_json(self):
        e = MemoryEvent(type="learned", data={"id": "abc"})
        j = e.to_json()
        assert '"learned"' in j
        assert '"abc"' in j

    def test_memory_event_to_dict(self):
        e = MemoryEvent(type="forgotten", data={"id": "xyz"}, namespace="test")
        d = e.to_dict()
        assert d["type"] == "forgotten"
        assert d["namespace"] == "test"

    @pytest.mark.asyncio
    async def test_async_emit(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("learned", handler)
        await bus.emit("learned", {"id": "abc"})
        assert len(received) == 1
        assert received[0].data["id"] == "abc"

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("*", handler)
        await bus.emit("learned", {"id": "1"})
        await bus.emit("forgotten", {"id": "2"})
        assert len(received) == 2

    def test_unsubscribe(self):
        bus = EventBus()

        async def handler(event):
            pass

        bus.subscribe("learned", handler)
        bus.unsubscribe("learned", handler)
        assert len(bus._subscribers.get("learned", [])) == 0


class TestMemOSEvents:
    """Integration tests for MemOS event emission."""

    def test_learn_emits_event(self):
        mem = MemOS(sanitize=False)
        mem.learn("test content", tags=["test"])
        history = mem.events.get_history()
        assert len(history) >= 1
        assert any(e.type == "learned" and "test content" in e.data.get("content", "") for e in history)

    def test_forget_emits_event(self):
        mem = MemOS(sanitize=False)
        item = mem.learn("to be forgotten")
        mem.forget(item.id)
        history = mem.events.get_history(event_type="forgotten")
        assert len(history) == 1

    def test_prune_emits_event(self):
        mem = MemOS(sanitize=False)
        import time
        from memos.models import MemoryItem
        old_time = time.time() - 100 * 86400
        item = MemoryItem(
            id="old-low", content="old low importance memory",
            importance=0.0, created_at=old_time,
        )
        mem._store.upsert(item)
        pruned = mem.prune(threshold=0.1, dry_run=False)
        if pruned:
            history = mem.events.get_history(event_type="pruned")
            assert len(history) == 1

    def test_recall_emits_event(self):
        mem = MemOS(sanitize=False)
        mem.learn("hello world")
        results = mem.recall("hello")
        if results:
            history = mem.events.get_history(event_type="recalled")
            assert len(history) >= 1

    def test_events_namespace_isolation(self):
        mem = MemOS(sanitize=False)
        mem.namespace = "agent-x"
        mem.learn("secret data")
        history = mem.events.get_history(namespace="agent-x")
        assert len(history) == 1
        history_other = mem.events.get_history(namespace="agent-y")
        assert len(history_other) == 0

    def test_ws_client_receives_events(self):
        mem = MemOS(sanitize=False)
        q = mem.events.add_ws_client()
        mem.learn("ws test")
        assert not q.empty()
        event = q.get_nowait()
        assert event.type == "learned"

    def test_multiple_ws_clients(self):
        mem = MemOS(sanitize=False)
        q1 = mem.events.add_ws_client()
        q2 = mem.events.add_ws_client()
        mem.learn("broadcast test")
        assert not q1.empty()
        assert not q2.empty()
