"""Tests for async consolidation engine."""

import asyncio
import time

import pytest

from memos.consolidation.async_engine import AsyncConsolidationEngine, AsyncConsolidationHandle
from memos.storage.memory_backend import InMemoryBackend
from memos.models import MemoryItem


def _make_item(content: str, **kw) -> MemoryItem:
    return MemoryItem(id=f"test-{content[:8]}-{time.time_ns()}", content=content, **kw)


class TestAsyncConsolidationHandle:
    def test_initial_state(self):
        handle = AsyncConsolidationHandle(task_id="abc123")
        assert handle.status == "pending"
        assert handle.result is None
        assert handle.error is None
        assert handle.finished_at is None

    def test_to_dict_pending(self):
        handle = AsyncConsolidationHandle(task_id="abc123")
        d = handle.to_dict()
        assert d["status"] == "pending"
        assert d["result"] is None
        assert d["duration_s"] is None

    def test_to_dict_completed(self):
        from memos.consolidation.engine import ConsolidationResult
        handle = AsyncConsolidationHandle(task_id="abc123")
        handle.status = "completed"
        handle.finished_at = handle.started_at + 1.5
        handle.result = ConsolidationResult(groups_found=3, memories_merged=5, space_freed=5)
        d = handle.to_dict()
        assert d["status"] == "completed"
        assert d["result"]["groups_found"] == 3
        assert d["duration_s"] == 1.5


class TestAsyncConsolidationEngine:
    @pytest.mark.asyncio
    async def test_start_and_complete(self):
        store = InMemoryBackend()
        store.upsert(_make_item("Hello world"))
        store.upsert(_make_item("Hello world"))

        engine = AsyncConsolidationEngine()
        handle = await engine.start(store)
        assert handle.status in ("pending", "running")

        # Wait for completion
        for _ in range(50):
            await asyncio.sleep(0.05)
            if handle.status in ("completed", "failed"):
                break

        assert handle.status == "completed"
        assert handle.result is not None
        assert handle.result.groups_found >= 1

    @pytest.mark.asyncio
    async def test_dry_run(self):
        store = InMemoryBackend()
        store.upsert(_make_item("Duplicate content"))
        store.upsert(_make_item("Duplicate content"))

        engine = AsyncConsolidationEngine()
        handle = await engine.start(store, dry_run=True)

        for _ in range(50):
            await asyncio.sleep(0.05)
            if handle.status in ("completed", "failed"):
                break

        assert handle.status == "completed"
        # Dry run: space_freed should be 0 (nothing removed)
        assert handle.result.space_freed == 0
        # But duplicates should still be in the store
        assert len(store.list_all()) == 2

    @pytest.mark.asyncio
    async def test_get_status(self):
        store = InMemoryBackend()
        engine = AsyncConsolidationEngine()
        handle = await engine.start(store)

        status = engine.get_status(handle.task_id)
        assert status is not None
        assert status.task_id == handle.task_id

        # Nonexistent task
        assert engine.get_status("nope") is None

    @pytest.mark.asyncio
    async def test_list_tasks(self):
        store = InMemoryBackend()
        engine = AsyncConsolidationEngine()

        h1 = await engine.start(store)
        h2 = await engine.start(store)

        tasks = engine.list_tasks()
        assert len(tasks) == 2
        task_ids = {t.task_id for t in tasks}
        assert h1.task_id in task_ids
        assert h2.task_id in task_ids

    @pytest.mark.asyncio
    async def test_clear_completed(self):
        store = InMemoryBackend()
        store.upsert(_make_item("dup"))
        store.upsert(_make_item("dup"))

        engine = AsyncConsolidationEngine()
        handle = await engine.start(store)

        # Wait for completion
        for _ in range(100):
            await asyncio.sleep(0.05)
            if handle.status in ("completed", "failed"):
                break

        assert handle.status == "completed"
        assert len(engine.list_tasks()) == 1

        # Clear completed tasks with max_age=0 so it's always old enough
        cleared = engine.clear_completed(max_age_seconds=0)
        assert cleared == 1
        assert len(engine.list_tasks()) == 0

    @pytest.mark.asyncio
    async def test_event_callback(self):
        events = []
        store = InMemoryBackend()
        store.upsert(_make_item("Hello world"))
        store.upsert(_make_item("Hello world"))

        engine = AsyncConsolidationEngine()
        engine.on_event(lambda etype, data: events.append((etype, data)))

        handle = await engine.start(store)

        for _ in range(50):
            await asyncio.sleep(0.05)
            if handle.status in ("completed", "failed"):
                break

        event_types = [e[0] for e in events]
        assert "consolidation_started" in event_types
        assert "consolidation_completed" in event_types

    @pytest.mark.asyncio
    async def test_empty_store(self):
        store = InMemoryBackend()
        engine = AsyncConsolidationEngine()
        handle = await engine.start(store)

        for _ in range(50):
            await asyncio.sleep(0.05)
            if handle.status in ("completed", "failed"):
                break

        assert handle.status == "completed"
        assert handle.result.groups_found == 0


class TestMemOSAsyncConsolidation:
    @pytest.mark.asyncio
    async def test_consolidate_async(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("Duplicate content alpha")
        mem.learn("Duplicate content alpha")

        handle = await mem.consolidate_async()

        for _ in range(50):
            await asyncio.sleep(0.05)
            if handle.status in ("completed", "failed"):
                break

        assert handle.status == "completed"

    @pytest.mark.asyncio
    async def test_consolidation_status(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("Some content")

        handle = await mem.consolidate_async(dry_run=True)

        # Status should be queryable
        status = mem.consolidation_status(handle.task_id)
        assert status is not None
        assert "task_id" in status

    @pytest.mark.asyncio
    async def test_consolidation_tasks_list(self):
        mem = MemOS(backend="memory", sanitize=False)

        await mem.consolidate_async()
        await mem.consolidate_async()

        tasks = mem.consolidation_tasks()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_consolidation_status_not_found(self):
        mem = MemOS(backend="memory", sanitize=False)
        assert mem.consolidation_status("nonexistent") is None

    def test_consolidation_tasks_empty(self):
        mem = MemOS(backend="memory", sanitize=False)
        assert mem.consolidation_tasks() == []


# Import MemOS for the integration tests
from memos.core import MemOS
