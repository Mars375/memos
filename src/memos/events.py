"""WebSocket event bus for real-time memory change notifications.

Provides an in-process pub/sub layer that emits events when memories are
created, updated, deleted, or pruned. Any number of WebSocket clients can
subscribe and receive a live stream of changes.

Event types:
  - learned      : a new memory was stored
  - recalled     : a memory was accessed via recall
  - forgotten    : a memory was deleted by ID/content
  - pruned       : one or more memories were removed by decay
  - consolidated : memories were merged by the consolidation engine
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine
import logging

logger = logging.getLogger(__name__)


@dataclass
class MemoryEvent:
    """A single memory change event."""

    type: str                           # learned | recalled | forgotten | pruned | consolidated
    data: dict[str, Any] = field(default_factory=dict)
    namespace: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(
            {"type": self.type, "data": self.data, "namespace": self.namespace, "timestamp": self.timestamp},
            default=str,
        )

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data, "namespace": self.namespace, "timestamp": self.timestamp}


# Type alias for async event handlers
EventHandler = Callable[["MemoryEvent"], Coroutine[Any, Any, None]]


class EventBus:
    """In-process async event bus for memory change notifications.

    Thread-safe for single-event-loop usage (which is the FastAPI default).
    Supports both programmatic subscribers and WebSocket client queues.
    """

    def __init__(self, max_history: int = 200) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._ws_clients: list[asyncio.Queue[MemoryEvent]] = []
        self._history: list[MemoryEvent] = []
        self._max_history = max_history

    # ── Subscribe / unsubscribe ──────────────────────────────

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register an async handler for a specific event type (or '*' for all)."""
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a previously registered handler."""
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    # ── WebSocket client management ──────────────────────────

    def add_ws_client(self) -> asyncio.Queue[MemoryEvent]:
        """Create a queue for a new WebSocket client. Returns the queue."""
        q: asyncio.Queue[MemoryEvent] = asyncio.Queue(maxsize=500)
        self._ws_clients.append(q)
        return q

    def remove_ws_client(self, q: asyncio.Queue[MemoryEvent]) -> None:
        """Remove a client queue when it disconnects."""
        if q in self._ws_clients:
            self._ws_clients.remove(q)

    # ── Emit ─────────────────────────────────────────────────

    def emit_sync(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        namespace: str = "",
    ) -> None:
        """Synchronous emit — safe to call from sync MemOS methods.

        Pushes events to WebSocket queues immediately (they're asyncio thread-safe).
        Schedules async handlers on the running event loop if one exists.
        """
        event = MemoryEvent(
            type=event_type,
            data=data or {},
            namespace=namespace,
        )

        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Push to all WebSocket queues
        dead_queues: list[asyncio.Queue[MemoryEvent]] = []
        for q in self._ws_clients:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(q)
        for q in dead_queues:
            self.remove_ws_client(q)
            logger.warning("Dropped slow WebSocket client (queue full)")

        # Schedule async handlers if there's a running loop
        try:
            loop = asyncio.get_running_loop()
            for handler in self._subscribers.get(event_type, []):
                loop.create_task(handler(event))
            for handler in self._subscribers.get("*", []):
                loop.create_task(handler(event))
        except RuntimeError:
            pass  # No running loop — WS clients still got the event

    async def emit(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        namespace: str = "",
    ) -> None:
        """Async emit — await all typed + wildcard handlers."""
        event = MemoryEvent(
            type=event_type,
            data=data or {},
            namespace=namespace,
        )

        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Push to WebSocket queues
        dead_queues: list[asyncio.Queue[MemoryEvent]] = []
        for q in self._ws_clients:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(q)
        for q in dead_queues:
            self.remove_ws_client(q)

        # Await all matching handlers
        for handler in self._subscribers.get(event_type, []):
            try:
                await handler(event)
            except Exception:
                logger.exception("Event handler error for %s", event_type)
        for handler in self._subscribers.get("*", []):
            try:
                await handler(event)
            except Exception:
                logger.exception("Event handler error for wildcard")

    # ── History ──────────────────────────────────────────────

    def get_history(
        self,
        event_type: str | None = None,
        limit: int = 50,
        namespace: str | None = None,
    ) -> list[MemoryEvent]:
        """Return recent events, optionally filtered by type and namespace."""
        events = list(self._history)
        if event_type:
            events = [e for e in events if e.type == event_type]
        if namespace is not None:
            events = [e for e in events if e.namespace == namespace]
        return events[-limit:]

    @property
    def client_count(self) -> int:
        """Number of connected WebSocket clients."""
        return len(self._ws_clients)

    @property
    def total_events_emitted(self) -> int:
        """Approximate total events (based on history size)."""
        return len(self._history)

    def clear(self) -> None:
        """Reset the bus (useful for testing)."""
        self._history.clear()
        self._subscribers.clear()
        self._ws_clients.clear()
