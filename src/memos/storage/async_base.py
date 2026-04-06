"""Async storage backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import MemoryItem


class AsyncStorageBackend(ABC):
    """Async interface for memory storage backends.

    Mirrors StorageBackend but all methods are coroutines.
    Accepts an optional ``namespace`` parameter for scoped operations.
    """

    @abstractmethod
    async def upsert(self, item: MemoryItem, *, namespace: str = "") -> None:
        """Insert or update a memory item."""

    @abstractmethod
    async def get(self, item_id: str, *, namespace: str = "") -> Optional[MemoryItem]:
        """Retrieve a memory item by ID."""

    @abstractmethod
    async def delete(self, item_id: str, *, namespace: str = "") -> bool:
        """Delete a memory item. Returns True if deleted."""

    @abstractmethod
    async def list_all(self, *, namespace: str = "") -> list[MemoryItem]:
        """List all memory items."""

    @abstractmethod
    async def search(self, query: str, limit: int = 20, *, namespace: str = "") -> list[MemoryItem]:
        """Simple keyword search."""

    @abstractmethod
    async def list_namespaces(self) -> list[str]:
        """List all known namespaces."""
