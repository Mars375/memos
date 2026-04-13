"""Subscription registry for event delivery targets."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from .models import SubscriptionFilter, SubscriptionRecord


class SubscriptionRegistry:
    """In-memory registry for queue and callback subscriptions."""

    def __init__(self) -> None:
        self._records: dict[str, SubscriptionRecord] = {}
        self._queue_index: dict[int, str] = {}

    def register_queue(
        self,
        queue: asyncio.Queue,
        *,
        filters: Optional[SubscriptionFilter] = None,
        label: str = "",
    ) -> SubscriptionRecord:
        record = SubscriptionRecord(
            kind="queue",
            filters=filters or SubscriptionFilter(),
            label=label,
            queue=queue,
        )
        self._records[record.id] = record
        self._queue_index[id(queue)] = record.id
        return record

    def register_callback(
        self,
        handler,
        *,
        filters: Optional[SubscriptionFilter] = None,
        label: str = "",
    ) -> SubscriptionRecord:
        record = SubscriptionRecord(
            kind="callback",
            filters=filters or SubscriptionFilter(),
            label=label,
            handler=handler,
        )
        self._records[record.id] = record
        return record

    def remove(self, subscription_id: str) -> bool:
        record = self._records.pop(subscription_id, None)
        if record is None:
            return False
        if record.kind == "queue" and record.queue is not None:
            self._queue_index.pop(id(record.queue), None)
        return True

    def remove_queue(self, queue: asyncio.Queue) -> bool:
        subscription_id = self._queue_index.pop(id(queue), None)
        if not subscription_id:
            return False
        self._records.pop(subscription_id, None)
        return True

    def get_queue_record(self, queue: asyncio.Queue) -> SubscriptionRecord | None:
        subscription_id = self._queue_index.get(id(queue))
        if not subscription_id:
            return None
        return self._records.get(subscription_id)

    def update_queue(
        self,
        queue: asyncio.Queue,
        *,
        filters: Optional[SubscriptionFilter] = None,
        active: Optional[bool] = None,
        label: Optional[str] = None,
    ) -> SubscriptionRecord | None:
        record = self.get_queue_record(queue)
        if record is None:
            return None
        if filters is not None:
            record.filters = filters
        if active is not None:
            record.active = active
        if label is not None:
            record.label = label
        return record

    def set_active(self, subscription_id: str, active: bool) -> bool:
        record = self._records.get(subscription_id)
        if record is None:
            return False
        record.active = active
        return True

    def list(self) -> list[SubscriptionRecord]:
        return sorted(self._records.values(), key=lambda r: r.created_at)

    def matching(self, event: Any) -> list[SubscriptionRecord]:
        return [record for record in self._records.values() if record.active and record.filters.matches(event)]

    def queue_count(self) -> int:
        return sum(1 for record in self._records.values() if record.kind == "queue")

    def clear(self) -> None:
        self._records.clear()
        self._queue_index.clear()
