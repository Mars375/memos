"""Backend migration engine — move memories between storage backends.

Usage (programmatic):
    from memos import MemOS
    source = MemOS(backend="memory", persist_path=".memos/store.json")
    report = source.migrate_to(
        dest_backend="chroma",
        embed_host="http://localhost:11434",
    )


Usage (CLI):
    memos migrate --dest chroma --dest-embed-host http://localhost:11434
    memos migrate --dest qdrant --dest-qdrant-path ./qdrant-data --dest-embed-host http://localhost:11434
    memos migrate --dest json --dest-path ./backup.json
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .storage.base import StorageBackend
from .storage.chroma_backend import ChromaBackend
from .storage.json_backend import JsonFileBackend
from .storage.memory_backend import InMemoryBackend
from .storage.pinecone_backend import PineconeBackend
from .storage.qdrant_backend import QdrantBackend

logger = logging.getLogger(__name__)


@dataclass
class MigrationReport:
    """Result of a backend migration."""

    source_backend: str
    dest_backend: str
    total_items: int = 0
    migrated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    namespaces_migrated: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0
    dry_run: bool = False

    @property
    def duration_seconds(self) -> float:
        if self.finished_at and self.started_at:
            return round(self.finished_at - self.started_at, 2)
        return 0.0

    def summary(self) -> str:
        mode = " (dry-run)" if self.dry_run else ""
        lines = [
            f"Migration{mode}: {self.source_backend} → {self.dest_backend}",
            f"  Items: {self.migrated}/{self.total_items} migrated, {self.skipped} skipped",
            f"  Namespaces: {self.namespaces_migrated}",
            f"  Errors: {len(self.errors)}",
            f"  Duration: {self.duration_seconds}s",
        ]
        return "\n".join(lines)


def _create_backend(
    backend: str,
    **kwargs: Any,
) -> StorageBackend:
    """Instantiate a storage backend from a name + kwargs."""
    if backend in ("memory", "inmemory"):
        path = kwargs.get("persist_path")
        if path:
            return JsonFileBackend(path=path)
        return InMemoryBackend()
    if backend == "json":
        return JsonFileBackend(path=kwargs.get("path", ".memos/store.json"))
    if backend == "chroma":
        return ChromaBackend(
            host=kwargs.get("host", "localhost"),
            port=kwargs.get("port", 8000),
        )
    if backend == "qdrant":
        return QdrantBackend(
            host=kwargs.get("host", "localhost"),
            port=kwargs.get("port", 6333),
            api_key=kwargs.get("api_key"),
            path=kwargs.get("qdrant_path"),
            embed_host=kwargs.get("embed_host", "http://localhost:11434"),
            embed_model=kwargs.get("embed_model", "nomic-embed-text"),
            vector_size=kwargs.get("vector_size", 768),
        )
    if backend == "pinecone":
        return PineconeBackend(
            api_key=kwargs.get("api_key", ""),
            environment=kwargs.get("environment"),
            index_name=kwargs.get("index_name", "memos"),
            embed_host=kwargs.get("embed_host", "http://localhost:11434"),
            embed_model=kwargs.get("embed_model", "nomic-embed-text"),
            vector_size=kwargs.get("vector_size", 768),
            cloud=kwargs.get("cloud", "aws"),
            region=kwargs.get("region", "us-east-1"),
            serverless=kwargs.get("serverless", True),
        )
    raise ValueError(f"Unknown backend: {backend!r}")


class MigrationEngine:
    """Migrate all data from one backend to another."""

    def migrate(
        self,
        source: StorageBackend,
        source_name: str,
        dest: StorageBackend,
        dest_name: str,
        *,
        namespaces: Optional[list[str]] = None,
        tags_filter: Optional[list[str]] = None,
        merge: str = "skip",
        dry_run: bool = False,
        batch_size: int = 100,
        on_progress: Any = None,
    ) -> MigrationReport:
        """Run migration from source to destination backend.

        Args:
            source: Source storage backend.
            source_name: Human-readable name for the source.
            dest: Destination storage backend.
            dest_name: Human-readable name for the destination.
            namespaces: Only migrate these namespaces (None = all).
            tags_filter: Only migrate items that have at least one of these tags.
            merge: How to handle existing items: "skip", "overwrite", "error".
            dry_run: If True, report what would happen without writing.
            batch_size: Number of items to process before calling on_progress.
            on_progress: Optional callback(report, items_done) for progress.

        Returns:
            MigrationReport with full statistics.
        """
        report = MigrationReport(
            source_backend=source_name,
            dest_backend=dest_name,
            started_at=time.time(),
            dry_run=dry_run,
        )

        # Determine namespaces to migrate
        all_ns = source.list_namespaces()
        # Always include the default namespace "" and dedupe while preserving order.
        if namespaces is not None:
            target_ns = list(dict.fromkeys(namespaces))
        else:
            target_ns = list(dict.fromkeys([""] + all_ns))
        report.namespaces_migrated = len(target_ns)

        items_done = 0
        for ns in target_ns:
            items = source.list_all(namespace=ns)
            for item in items:
                report.total_items += 1

                # Apply tag filter if specified
                if tags_filter and not any(t in item.tags for t in tags_filter):
                    report.skipped += 1
                    items_done += 1
                    continue

                # Check existing in destination
                existing = dest.get(item.id, namespace=ns)
                if existing and merge == "skip":
                    report.skipped += 1
                    items_done += 1
                    continue
                if existing and merge == "error":
                    report.errors.append(f"Item {item.id} already exists in dest (namespace={ns!r})")
                    report.skipped += 1
                    items_done += 1
                    continue

                # Migrate
                if not dry_run:
                    try:
                        if existing and merge == "overwrite":
                            dest.delete(item.id, namespace=ns)
                        dest.upsert(item, namespace=ns)
                    except Exception as e:
                        report.errors.append(f"Failed to migrate {item.id} (ns={ns!r}): {e}")
                        report.skipped += 1
                        items_done += 1
                        continue

                report.migrated += 1
                items_done += 1

                if on_progress and items_done % batch_size == 0:
                    try:
                        on_progress(report, items_done)
                    except Exception:
                        logger.debug("on_progress callback failed", exc_info=True)
                        pass

        report.finished_at = time.time()
        return report
