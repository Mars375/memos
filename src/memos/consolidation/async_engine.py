"""Async consolidation engine — run memory dedup in the background.

Provides non-blocking consolidation that runs in an asyncio task,
reporting progress via the event bus.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..storage.base import StorageBackend
from .engine import ConsolidationEngine, ConsolidationResult


@dataclass
class AsyncConsolidationHandle:
    """Handle for tracking an async consolidation run."""

    task_id: str
    status: str = "pending"  # pending | running | completed | failed
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    result: ConsolidationResult | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": round(self.finished_at - self.started_at, 2) if self.finished_at else None,
            "result": {
                "groups_found": self.result.groups_found,
                "memories_merged": self.result.memories_merged,
                "space_freed": self.result.space_freed,
            }
            if self.result
            else None,
            "error": self.error,
        }


class AsyncConsolidationEngine:
    """Run consolidation as a background asyncio task.

    Usage:
        engine = AsyncConsolidationEngine()
        handle = await engine.start(store, similarity_threshold=0.7)
        # ... do other work ...
        status = engine.get_status(handle.task_id)
    """

    def __init__(
        self,
        *,
        similarity_threshold: float = 0.75,
        merge_content: bool = False,
        dry_run: bool = False,
    ) -> None:
        self._threshold = similarity_threshold
        self._merge_content = merge_content
        self._dry_run = dry_run
        self._tasks: dict[str, AsyncConsolidationHandle] = {}
        self._event_callback: Any = None  # Optional callback(event_type, data)

    def on_event(self, callback: Any) -> None:
        """Register a callback for consolidation events."""
        self._event_callback = callback

    def _emit(self, event_type: str, data: dict) -> None:
        if self._event_callback:
            self._event_callback(event_type, data)

    async def start(
        self,
        store: StorageBackend,
        *,
        similarity_threshold: float | None = None,
        merge_content: bool | None = None,
        dry_run: bool | None = None,
        namespace: str = "",
    ) -> AsyncConsolidationHandle:
        """Start an async consolidation run.

        Returns a handle that can be polled for status.
        """
        task_id = uuid.uuid4().hex[:12]
        handle = AsyncConsolidationHandle(task_id=task_id)
        self._tasks[task_id] = handle

        threshold = similarity_threshold if similarity_threshold is not None else self._threshold
        merge = merge_content if merge_content is not None else self._merge_content
        dry = dry_run if dry_run is not None else self._dry_run

        self._emit(
            "consolidation_started",
            {
                "task_id": task_id,
                "threshold": threshold,
                "merge_content": merge,
                "dry_run": dry,
            },
        )

        asyncio.create_task(self._run(handle, store, threshold, merge, dry, namespace))

        return handle

    async def _run(
        self,
        handle: AsyncConsolidationHandle,
        store: StorageBackend,
        threshold: float,
        merge_content: bool,
        dry_run: bool,
        namespace: str,
    ) -> None:
        """Execute consolidation in a thread pool to avoid blocking the event loop."""
        handle.status = "running"

        try:
            engine = ConsolidationEngine(similarity_threshold=threshold)
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: engine.consolidate(store, merge_content=merge_content, dry_run=dry_run, namespace=namespace),
            )
            handle.result = result
            handle.status = "completed"
            handle.finished_at = time.time()

            self._emit(
                "consolidation_completed",
                {
                    "task_id": handle.task_id,
                    "groups_found": result.groups_found,
                    "memories_merged": result.memories_merged,
                    "space_freed": result.space_freed,
                    "duration_s": round(handle.finished_at - handle.started_at, 2),
                },
            )

        except Exception as e:
            handle.status = "failed"
            handle.error = str(e)
            handle.finished_at = time.time()

            self._emit(
                "consolidation_failed",
                {
                    "task_id": handle.task_id,
                    "error": str(e),
                },
            )

    def get_status(self, task_id: str) -> AsyncConsolidationHandle | None:
        """Get the status of a consolidation task."""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[AsyncConsolidationHandle]:
        """List all consolidation tasks."""
        return list(self._tasks.values())

    def clear_completed(self, max_age_seconds: float = 3600) -> int:
        """Remove completed/failed tasks older than max_age_seconds."""
        now = time.time()
        to_remove = []
        for tid, handle in self._tasks.items():
            if handle.status in ("completed", "failed") and handle.finished_at:
                if now - handle.finished_at > max_age_seconds:
                    to_remove.append(tid)
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)
