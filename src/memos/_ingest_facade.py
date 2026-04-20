"""Ingest facade — file and URL ingestion."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ._constants import DEFAULT_IMPORTANCE, DEFAULT_MAX_CHUNK_SIZE
from .models import MemoryItem, generate_id

if TYPE_CHECKING:
    from .ingest.engine import IngestResult

logger = logging.getLogger(__name__)


class IngestFacade:
    """Mixin providing file/URL ingestion operations for the MemOS nucleus."""

    def ingest(
        self,
        path: str,
        *,
        tags: list[str] | None = None,
        importance: float = DEFAULT_IMPORTANCE,
        max_chunk: int = DEFAULT_MAX_CHUNK_SIZE,
        dry_run: bool = False,
    ) -> IngestResult:
        """Parse and store memories from a file (markdown, JSON, txt)."""
        from .ingest.engine import ingest_file

        result = ingest_file(path, tags=tags, importance=importance, max_chunk=max_chunk)

        if not dry_run:
            for chunk in result.chunks:
                try:
                    self.learn(
                        chunk["content"],
                        tags=chunk.get("tags", []),
                        importance=chunk.get("importance", importance),
                        metadata=chunk.get("metadata", {}),
                    )
                except Exception as e:
                    result.errors.append(f"Failed to store chunk: {e}")

        return result

    def ingest_url(
        self,
        url: str,
        *,
        tags: list[str] | None = None,
        importance: float = DEFAULT_IMPORTANCE,
        max_chunk: int = DEFAULT_MAX_CHUNK_SIZE,
        dry_run: bool = False,
        skip_sanitization: bool = False,
    ) -> IngestResult:
        """Fetch a URL, extract its contents, and store it as memories."""
        from .ingest.url import URLIngestor

        result = URLIngestor().ingest(
            url,
            tags=tags,
            importance=importance,
            max_chunk=max_chunk,
        )

        if not dry_run:
            for chunk in result.chunks:
                if skip_sanitization:
                    # Bypass sanitizer: store as a MemoryItem directly
                    try:
                        item = MemoryItem(
                            id=generate_id(chunk["content"]),
                            content=chunk["content"],
                            tags=chunk.get("tags", []),
                            importance=chunk.get("importance", importance),
                            metadata=chunk.get("metadata", {}),
                        )
                        self._store.upsert(item, namespace=self._namespace)
                        self._retrieval.index(item)
                        self._versioning.record_version(item, source="ingest_url")
                        continue
                    except Exception as e:
                        result.errors.append(f"Failed to store chunk (skip_sanitization): {e}")
                        continue
                try:
                    self.learn(
                        chunk["content"],
                        tags=chunk.get("tags", []),
                        importance=chunk.get("importance", importance),
                        metadata=chunk.get("metadata", {}),
                    )
                except Exception as e:
                    result.errors.append(f"Failed to store chunk: {e}")

        return result
