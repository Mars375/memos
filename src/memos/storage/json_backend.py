"""JSON file storage backend — zero dependencies, persistent across CLI calls.

Stores all memories in a single JSON file (default: ``.memos/store.json``).
Each CLI invocation reads the file on startup and writes after every mutation.
This is the recommended default backend for single-user CLI usage.

For high-throughput or multi-process scenarios, use SQLite, Chroma, or Qdrant.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Optional

from ..models import MemoryItem
from .base import StorageBackend

_DEFAULT = ""  # global namespace key


class JsonFileBackend(StorageBackend):
    """File-backed storage that persists across process restarts.

    Layout::

        .memos/
        ├── memos.json       # config (created by ``memos init``)
        └── store.json       # memory data (managed by this backend)

    Thread-safe via a process-local lock (safe for asyncio, not for
    multi-process concurrency — use a server backend for that).
    """

    def __init__(self, path: str | Path = ".memos/store.json") -> None:
        self._path = Path(path).expanduser()
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, dict]] = {_DEFAULT: {}}
        self._load()

    # ---- persistence ----

    def _load(self) -> None:
        """Load store from disk (no-op if file missing)."""
        if self._path.is_file():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                # Expect {namespace: {id: item_dict, ...}, ...}
                if isinstance(raw, dict):
                    self._data = {_DEFAULT: {}}
                    for ns, items in raw.items():
                        if isinstance(items, dict):
                            self._data[ns] = {k: v for k, v in items.items() if isinstance(v, dict) and "content" in v}
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._quarantine_corrupt_store()
                self._data = {_DEFAULT: {}}
            except OSError:
                self._data = {_DEFAULT: {}}
        else:
            self._data = {_DEFAULT: {}}

    def _quarantine_corrupt_store(self) -> None:
        """Move an unreadable JSON store aside before future writes replace it."""
        corrupt_path = self._path.with_suffix(f"{self._path.suffix}.corrupt")
        counter = 1
        while corrupt_path.exists():
            corrupt_path = self._path.with_suffix(f"{self._path.suffix}.corrupt.{counter}")
            counter += 1
        try:
            self._path.replace(corrupt_path)
        except OSError:
            pass

    def _fsync_parent_dir(self) -> None:
        """Best-effort fsync for the directory entry created by atomic replace."""
        if not hasattr(os, "O_DIRECTORY"):
            return
        try:
            fd = os.open(self._path.parent, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _save(self) -> None:
        """Atomically write store to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f".{self._path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                os.chmod(tmp, 0o600)
                json.dump(self._data, f, ensure_ascii=False, indent=None)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self._path)
            os.chmod(self._path, 0o600)
            self._fsync_parent_dir()
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    # ---- helpers ----

    @staticmethod
    def _item_to_dict(item: MemoryItem) -> dict:
        d = {
            "id": item.id,
            "content": item.content,
            "tags": item.tags,
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
            "relevance_score": item.relevance_score,
            "metadata": item.metadata,
        }
        if item.ttl is not None:
            d["ttl"] = item.ttl
        return d

    @staticmethod
    def _dict_to_item(d: dict) -> MemoryItem:
        return MemoryItem(
            id=d["id"],
            content=d["content"],
            tags=d.get("tags", []),
            importance=d.get("importance", 0.5),
            created_at=d.get("created_at", 0.0),
            accessed_at=d.get("accessed_at", 0.0),
            access_count=d.get("access_count", 0),
            relevance_score=d.get("relevance_score", 0.0),
            metadata=d.get("metadata", {}),
            ttl=d.get("ttl"),
        )

    def _bucket(self, namespace: str) -> dict[str, dict]:
        if namespace not in self._data:
            self._data[namespace] = {}
        return self._data[namespace]

    # ---- StorageBackend interface ----

    def upsert(self, item: MemoryItem, *, namespace: str = _DEFAULT) -> None:
        with self._lock:
            self._bucket(namespace)[item.id] = self._item_to_dict(item)
            self._save()

    def get(self, item_id: str, *, namespace: str = _DEFAULT) -> Optional[MemoryItem]:
        with self._lock:
            d = self._bucket(namespace).get(item_id)
            return self._dict_to_item(d) if d else None

    def delete(self, item_id: str, *, namespace: str = _DEFAULT) -> bool:
        with self._lock:
            bucket = self._bucket(namespace)
            if item_id in bucket:
                del bucket[item_id]
                self._save()
                return True
            return False

    def list_all(self, *, namespace: str = _DEFAULT) -> list[MemoryItem]:
        with self._lock:
            return [self._dict_to_item(d) for d in self._bucket(namespace).values()]

    def search(self, query: str, limit: int = 20, *, namespace: str = _DEFAULT) -> list[MemoryItem]:
        q = query.lower()
        results: list[MemoryItem] = []
        with self._lock:
            for d in self._bucket(namespace).values():
                item = self._dict_to_item(d)
                if q in item.content.lower():
                    results.append(item)
                elif any(q in tag.lower() for tag in item.tags):
                    results.append(item)
                if len(results) >= limit:
                    break
        return results

    def list_namespaces(self) -> list[str]:
        with self._lock:
            return sorted(n for n in self._data if n != _DEFAULT)
