"""Tests for async storage backends."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from memos.models import MemoryItem
from memos.storage.async_wrapper import AsyncWrapper
from memos.storage.memory_backend import InMemoryBackend


def _item(content: str, **kw) -> MemoryItem:
    kw.setdefault("id", uuid.uuid4().hex[:12])
    return MemoryItem(content=content, **kw)


# ── AsyncWrapper over InMemoryBackend ────────────────────────────────────────


@pytest.fixture
def async_backend():
    return AsyncWrapper(InMemoryBackend())


@pytest.mark.asyncio
async def test_upsert_and_get(async_backend):
    item = _item("hello async")
    await async_backend.upsert(item)
    got = await async_backend.get(item.id)
    assert got is not None
    assert got.content == "hello async"


@pytest.mark.asyncio
async def test_get_missing(async_backend):
    assert await async_backend.get("nope") is None


@pytest.mark.asyncio
async def test_delete(async_backend):
    item = _item("bye")
    await async_backend.upsert(item)
    assert await async_backend.delete(item.id) is True
    assert await async_backend.get(item.id) is None


@pytest.mark.asyncio
async def test_delete_missing(async_backend):
    assert await async_backend.delete("ghost") is False


@pytest.mark.asyncio
async def test_list_all(async_backend):
    items = [_item("a"), _item("b"), _item("c")]
    for i in items:
        await async_backend.upsert(i)
    all_items = await async_backend.list_all()
    assert len(all_items) == 3


@pytest.mark.asyncio
async def test_search(async_backend):
    await async_backend.upsert(_item("python async"))
    await async_backend.upsert(_item("rust futures"))
    results = await async_backend.search("python")
    assert len(results) == 1
    assert "python" in results[0].content


@pytest.mark.asyncio
async def test_search_limit(async_backend):
    for i in range(10):
        await async_backend.upsert(_item(f"item number {i}"))
    results = await async_backend.search("item", limit=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_list_namespaces(async_backend):
    item = _item("ns item")
    await async_backend.upsert(item, namespace="agent-1")
    ns = await async_backend.list_namespaces()
    assert "agent-1" in ns


@pytest.mark.asyncio
async def test_namespaces_isolated(async_backend):
    a = _item("in a")
    b = _item("in b")
    await async_backend.upsert(a, namespace="a")
    await async_backend.upsert(b, namespace="b")
    items_a = await async_backend.list_all(namespace="a")
    items_b = await async_backend.list_all(namespace="b")
    assert len(items_a) == 1
    assert len(items_b) == 1
    assert items_a[0].content == "in a"


@pytest.mark.asyncio
async def test_concurrent_writes(async_backend):
    """Multiple concurrent upserts should all succeed."""
    items = [_item(f"concurrent-{i}") for i in range(20)]
    await asyncio.gather(*(async_backend.upsert(i) for i in items))
    all_items = await async_backend.list_all()
    assert len(all_items) == 20


@pytest.mark.asyncio
async def test_concurrent_read_write(async_backend):
    """Concurrent reads and writes should not crash."""
    item = _item("rw-test")
    await async_backend.upsert(item)

    async def reader():
        for _ in range(10):
            await async_backend.get(item.id)
            await async_backend.search("rw")

    async def writer():
        for i in range(10):
            await async_backend.upsert(_item(f"extra-{i}"))

    await asyncio.gather(reader(), writer())
    all_items = await async_backend.list_all()
    assert len(all_items) == 11


@pytest.mark.asyncio
async def test_upsert_overwrites(async_backend):
    item = _item("original")
    await async_backend.upsert(item)
    item.content = "updated"
    await async_backend.upsert(item)
    got = await async_backend.get(item.id)
    assert got.content == "updated"


@pytest.mark.asyncio
async def test_empty_list_all(async_backend):
    assert await async_backend.list_all() == []


@pytest.mark.asyncio
async def test_empty_search(async_backend):
    assert await async_backend.search("nothing") == []


@pytest.mark.asyncio
async def test_search_by_tag(async_backend):
    item = _item("some content", tags=["kubernetes"])
    await async_backend.upsert(item)
    results = await async_backend.search("kubernetes")
    assert len(results) == 1
