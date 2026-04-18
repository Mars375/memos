"""I/O facade for MemOS — export, import, parquet, and migration."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ._constants import DEFAULT_IMPORTANCE
from .models import MemoryItem, generate_id

if TYPE_CHECKING:
    from .migration import MigrationReport


class IOFacade:
    """Mixin exposing export/import/parquet/migration APIs on MemOS."""

    _store: Any
    _namespace: str
    _retrieval: Any
    _events: Any
    _backend_name: str

    # ── JSON export/import ────────────────────────────────────

    def export_json(self, *, include_metadata: bool = True) -> dict:
        """Export all memories as a JSON-serializable dict."""
        items = self._store.list_all(namespace=self._namespace)
        return {
            "version": "0.2.0",
            "exported_at": time.time(),
            "total": len(items),
            "memories": [
                {
                    "id": item.id,
                    "content": item.content,
                    "tags": item.tags,
                    "importance": item.importance,
                    "created_at": item.created_at,
                    "accessed_at": item.accessed_at,
                    "access_count": item.access_count,
                    **({"metadata": item.metadata} if include_metadata else {}),
                }
                for item in items
            ],
        }

    def import_json(
        self,
        data: dict,
        *,
        merge: str = "skip",
        tags_prefix: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Import memories from a JSON dict (as produced by export_json)."""
        result = {"imported": 0, "skipped": 0, "overwritten": 0, "errors": []}
        memories = data.get("memories", [])

        for entry in memories:
            try:
                mem_id = entry.get("id", generate_id(entry["content"]))
                existing = self._store.get(mem_id, namespace=self._namespace)

                if existing and merge == "skip":
                    result["skipped"] += 1
                    continue

                if existing and merge == "overwrite":
                    self._store.delete(mem_id, namespace=self._namespace)
                    result["overwritten"] += 1

                tags = list(entry.get("tags", []))
                if tags_prefix:
                    tags.extend(tags_prefix)

                if not dry_run:
                    item = MemoryItem(
                        id=mem_id,
                        content=entry["content"].strip(),
                        tags=tags,
                        importance=max(0.0, min(1.0, entry.get("importance", DEFAULT_IMPORTANCE))),
                        created_at=entry.get("created_at", time.time()),
                        accessed_at=entry.get("accessed_at", time.time()),
                        access_count=entry.get("access_count", 0),
                        metadata=entry.get("metadata", {}),
                    )
                    self._store.upsert(item, namespace=self._namespace)
                    self._retrieval.index(item)
                result["imported"] += 1
            except Exception as e:
                result["errors"].append(str(e))

        return result

    # ── Parquet export/import ─────────────────────────────────

    def export_parquet(
        self,
        path: str,
        *,
        include_metadata: bool = True,
        compression: str = "zstd",
    ) -> dict:
        """Export all memories to a Parquet file.

        Requires pyarrow: ``pip install memos[parquet]``

        Args:
            path: Output file path.
            include_metadata: Include metadata as a JSON column.
            compression: Parquet codec (zstd, snappy, gzip, none).

        Returns:
            Summary dict with total, path, size_bytes, compression.
        """
        from .parquet_io import export_parquet as _export

        items = self._store.list_all(namespace=self._namespace)
        result = _export(items, path, include_metadata=include_metadata, compression=compression)

        self._events.emit_sync(
            "exported",
            {
                "format": "parquet",
                "total": result["total"],
                "path": result["path"],
                "size_bytes": result["size_bytes"],
            },
            namespace=self._namespace,
        )

        return result

    def import_parquet(
        self,
        path: str,
        *,
        merge: str = "skip",
        tags_prefix: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Import memories from a Parquet file.

        Requires pyarrow: ``pip install memos[parquet]``

        Args:
            path: Input Parquet file path.
            merge: "skip" (ignore existing), "overwrite" (replace), "duplicate" (always add).
            tags_prefix: Extra tags to add to all imported items.
            dry_run: If True, parse but don't store.

        Returns:
            dict with imported, skipped, overwritten, errors counts.
        """
        from .parquet_io import import_parquet as _import

        items = _import(path, tags_prefix=tags_prefix)
        result = {"imported": 0, "skipped": 0, "overwritten": 0, "errors": []}

        for item in items:
            try:
                existing = self._store.get(item.id, namespace=self._namespace)

                if existing and merge == "skip":
                    result["skipped"] += 1
                    continue

                if existing and merge == "overwrite":
                    self._store.delete(item.id, namespace=self._namespace)
                    result["overwritten"] += 1

                if not dry_run:
                    self._store.upsert(item, namespace=self._namespace)
                    self._retrieval.index(item)
                result["imported"] += 1
            except Exception as e:
                result["errors"].append(str(e))

        self._events.emit_sync(
            "imported",
            {
                "format": "parquet",
                "imported": result["imported"],
                "skipped": result["skipped"],
            },
            namespace=self._namespace,
        )

        return result

    # ── Migration ─────────────────────────────────────────────

    def migrate_to(
        self,
        dest_backend: str,
        *,
        namespaces: list[str] | None = None,
        tags_filter: list[str] | None = None,
        merge: str = "skip",
        dry_run: bool = False,
        batch_size: int = 100,
        **backend_kwargs,
    ) -> "MigrationReport":
        """Migrate memories from this backend to another backend.

        Args:
            dest_backend: Target backend name.
            namespaces: Optional namespace filter.
            tags_filter: Optional tag filter.
            merge: "skip", "overwrite", or "error" for existing items.
            dry_run: If True, report without writing.
            batch_size: Progress callback interval.
            backend_kwargs: Destination backend constructor args.
        """
        from .migration import MigrationEngine, _create_backend

        dest = _create_backend(dest_backend, **backend_kwargs)
        source_namespaces = namespaces
        if source_namespaces is None and self._namespace:
            source_namespaces = [self._namespace]
        engine = MigrationEngine()
        return engine.migrate(
            self._store,
            self._backend_name,
            dest,
            dest_backend,
            namespaces=source_namespaces,
            tags_filter=tags_filter,
            merge=merge,
            dry_run=dry_run,
            batch_size=batch_size,
        )
