"""In-memory storage backend — zero dependencies, namespace-aware."""

from __future__ import annotations

from typing import Optional

from ..models import MemoryItem
from .base import StorageBackend

_DEFAULT = ""  # default (global) namespace key


class InMemoryBackend(StorageBackend):
    """Simple dict-based storage. Good for testing and single-session use.

    Namespaces are isolated buckets.  ``namespace=""`` (default) is the global
    namespace that existed before multi-agent support.
    """

    def __init__(self) -> None:
        self._namespaces: dict[str, dict[str, MemoryItem]] = {_DEFAULT: {}}

    def _bucket(self, namespace: str) -> dict[str, MemoryItem]:
        if namespace not in self._namespaces:
            self._namespaces[namespace] = {}
        return self._namespaces[namespace]

    # --- StorageBackend interface ---

    def upsert(self, item: MemoryItem, *, namespace: str = _DEFAULT) -> None:
        self._bucket(namespace)[item.id] = item

    def get(self, item_id: str, *, namespace: str = _DEFAULT) -> Optional[MemoryItem]:
        return self._bucket(namespace).get(item_id)

    def delete(self, item_id: str, *, namespace: str = _DEFAULT) -> bool:
        return self._bucket(namespace).pop(item_id, None) is not None

    def list_all(self, *, namespace: str = _DEFAULT) -> list[MemoryItem]:
        return list(self._bucket(namespace).values())

    def search(self, query: str, limit: int = 20, *, namespace: str = _DEFAULT) -> list[MemoryItem]:
        q = query.lower()
        results = []
        for item in self._bucket(namespace).values():
            if q in item.content.lower():
                results.append(item)
            elif any(q in tag.lower() for tag in item.tags):
                results.append(item)
            if len(results) >= limit:
                break
        return results

    def list_namespaces(self) -> list[str]:
        return sorted(n for n in self._namespaces if n != _DEFAULT)
