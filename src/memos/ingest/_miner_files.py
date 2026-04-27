"""File and directory mining mixin for :mod:`memos.ingest.miner`."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import List, Optional

from ._miner_common import MineResult, iter_files
from .chunker import chunk_text, content_hash, detect_room

logger = logging.getLogger(__name__)


class FileMiningMixin:
    """Mine plain text, markdown, and code files into memory chunks."""

    def _is_duplicate(self, text: str) -> bool:
        h = content_hash(text)
        if h in self._seen_hashes:
            return True
        self._seen_hashes.add(h)
        return False

    def _store_chunk(self, content: str, tags: List[str], importance: float = 0.5) -> bool:
        """Store one chunk. Returns True if stored, False if skipped."""
        content = content.strip()
        if len(content) < 20:
            return False
        if self._is_duplicate(content):
            return False
        if not self._dry_run:
            self._memos.learn(content, tags=tags, importance=importance)
        return True

    def _mine_chunks(
        self,
        text: str,
        base_tags: List[str],
        source_path: Optional[Path] = None,
        importance: float = 0.5,
        known_hashes: Optional[set] = None,
    ) -> MineResult:
        """Chunk text and store each chunk.

        Args:
            known_hashes: If provided (--diff mode), skip chunks whose content
                hash is already in this set.
        """
        result = MineResult()
        chunks = chunk_text(text, size=self._chunk_size, overlap=self._chunk_overlap)

        batch: List[tuple[str, List[str], float]] = []

        for chunk in chunks:
            if len(chunk.strip()) < 20:
                result.skipped_empty += 1
                continue

            ch = content_hash(chunk)

            if known_hashes is not None and ch in known_hashes:
                result.skipped_cached += 1
                continue

            if self._is_duplicate(chunk):
                result.skipped_duplicates += 1
                continue

            tags = list(base_tags)
            if source_path:
                room_tags = detect_room(source_path, chunk)
                for tag in room_tags:
                    if tag not in tags:
                        tags.append(tag)
            for tag in self._extra_tags:
                if tag not in tags:
                    tags.append(tag)

            if self._dry_run:
                result.chunks.append({"content": chunk[:80] + "...", "tags": tags})
                result.imported += 1
            else:
                batch.append((chunk, tags, importance))
                if len(batch) >= self._batch_size:
                    self._flush_batch(batch, result)
                    batch = []

        if batch:
            self._flush_batch(batch, result)

        return result

    def _flush_batch(self, batch: List[tuple], result: MineResult) -> None:
        for content, tags, importance in batch:
            try:
                item = self._memos.learn(content, tags=tags, importance=importance)
                result.imported += 1
                if item is not None:
                    result.memory_ids.append(item.id)
            except Exception as exc:
                result.errors.append(str(exc))

    def mine_file(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        diff: bool = False,
    ) -> MineResult:
        """Mine a single text/markdown/code file.

        Args:
            diff: If True, only mine chunks not previously seen for this file
                (requires cache to be set).
        """
        path = Path(path).expanduser().resolve()
        result = MineResult()

        if not path.exists():
            result.errors.append(f"Not found: {path}")
            return result

        try:
            raw_bytes = path.read_bytes()
            text = raw_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            result.errors.append(f"Read error {path}: {exc}")
            return result

        file_sha256 = hashlib.sha256(raw_bytes).hexdigest()

        if self._cache is not None and not self._update and not diff:
            if self._cache.is_fresh(str(path), file_sha256):
                result.skipped_cached += 1
                return result

        if self._cache is not None and self._update:
            entry = self._cache.get(str(path))
            if entry and entry["memory_ids"]:
                for memory_id in entry["memory_ids"]:
                    try:
                        self._memos.forget(memory_id)
                    except Exception:
                        logger.warning("Forget failed during undo for %s", memory_id, exc_info=True)

        known_hashes: Optional[set] = None
        if diff and self._cache is not None:
            known_hashes = self._cache.get_chunk_hashes(str(path))

        base_tags = list(tags or [])
        base_tags += detect_room(path, text)

        chunk_result = self._mine_chunks(
            text,
            base_tags,
            source_path=path,
            importance=importance,
            known_hashes=known_hashes,
        )
        result.merge(chunk_result)

        if self._cache is not None and not self._dry_run:
            all_chunk_hashes: List[str] = []
            for chunk in chunk_text(text, size=self._chunk_size, overlap=self._chunk_overlap):
                if len(chunk.strip()) >= 20:
                    all_chunk_hashes.append(content_hash(chunk))
            if diff and known_hashes:
                merged = set(known_hashes) | set(all_chunk_hashes)
                all_chunk_hashes = list(merged)

            existing = self._cache.get(str(path))
            existing_ids: List[str] = existing["memory_ids"] if existing else []
            if self._update:
                existing_ids = []
            all_ids = existing_ids + result.memory_ids
            self._cache.record(
                str(path),
                file_sha256,
                memory_ids=all_ids,
                chunk_hashes=all_chunk_hashes,
            )

        return result

    def mine_directory(
        self,
        directory: str | Path,
        tags: Optional[List[str]] = None,
        extensions: Optional[set] = None,
        importance: float = 0.5,
        max_files: int = 500,
        diff: bool = False,
    ) -> MineResult:
        """Mine all files in a directory recursively."""
        directory = Path(directory).expanduser()
        result = MineResult()

        if not directory.is_dir():
            result.errors.append(f"Not a directory: {directory}")
            return result

        files = list(iter_files(directory, extensions=extensions, max_files=max_files))
        for file_path in files:
            file_result = self.mine_file(file_path, tags=tags, importance=importance, diff=diff)
            result.merge(file_result)

        return result


__all__ = ["FileMiningMixin"]
