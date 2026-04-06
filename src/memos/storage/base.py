"""Base storage backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import MemoryItem


class StorageBackend(ABC):
    """Interface for memory storage backends.

    All methods accept an optional ``namespace`` parameter.
    When a namespace is provided, operations are scoped to that namespace only.
    """

    @abstractmethod
    def upsert(self, item: MemoryItem, *, namespace: str = "") -> None:
        """Insert or update a memory item."""

    @abstractmethod
    def get(self, item_id: str, *, namespace: str = "") -> Optional[MemoryItem]:
        """Retrieve a memory item by ID."""

    @abstractmethod
    def delete(self, item_id: str, *, namespace: str = "") -> bool:
        """Delete a memory item. Returns True if deleted."""

    @abstractmethod
    def list_all(self, *, namespace: str = "") -> list[MemoryItem]:
        """List all memory items."""

    @abstractmethod
    def search(self, query: str, limit: int = 20, *, namespace: str = "") -> list[MemoryItem]:
        """Simple keyword search."""

    @abstractmethod
    def list_namespaces(self) -> list[str]:
        """List all known namespaces."""
