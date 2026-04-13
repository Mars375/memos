"""Async wrapper that delegates to any sync StorageBackend via thread pool."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Optional

from ..models import MemoryItem
from .async_base import AsyncStorageBackend
from .base import StorageBackend

_default_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="memos-async")


class AsyncWrapper(AsyncStorageBackend):
    """Wraps any sync StorageBackend and runs calls in a thread pool.

    This provides non-blocking I/O for FastAPI/ASGI without requiring
    the underlying backend to be natively async.
    """

    def __init__(self, backend: StorageBackend, executor: ThreadPoolExecutor | None = None) -> None:
        self._backend = backend
        self._executor = executor or _default_executor

    async def upsert(self, item: MemoryItem, *, namespace: str = "") -> None:
        await asyncio.get_running_loop().run_in_executor(
            self._executor, partial(self._backend.upsert, item, namespace=namespace)
        )

    async def get(self, item_id: str, *, namespace: str = "") -> Optional[MemoryItem]:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, partial(self._backend.get, item_id, namespace=namespace)
        )

    async def delete(self, item_id: str, *, namespace: str = "") -> bool:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, partial(self._backend.delete, item_id, namespace=namespace)
        )

    async def list_all(self, *, namespace: str = "") -> list[MemoryItem]:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, partial(self._backend.list_all, namespace=namespace)
        )

    async def search(self, query: str, limit: int = 20, *, namespace: str = "") -> list[MemoryItem]:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, partial(self._backend.search, query, limit, namespace=namespace)
        )

    async def list_namespaces(self) -> list[str]:
        return await asyncio.get_running_loop().run_in_executor(self._executor, self._backend.list_namespaces)
