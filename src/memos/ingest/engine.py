"""File ingestion engine — parse markdown/JSON into memory items."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class IngestResult:
    """Result of a file ingestion."""

    total_chunks: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        return f"IngestResult({self.total_chunks} chunks, {self.skipped} skipped, {len(self.errors)} errors)"


def _chunk_markdown(
    text: str,
    source: str = "",
    max_chunk: int = 2000,
) -> list[dict[str, Any]]:
    """Split markdown into chunks by headers, with fallback by size."""
    chunks: list[dict[str, Any]] = []

    # Split by headers (## or ###)
    sections = re.split(r"\n(?=#{1,3}\s)", text)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract header as tag
        header_match = re.match(r"^#{1,3}\s+(.+)", section)
        tags: list[str] = []
        if header_match:
            tag = header_match.group(1).strip().lower()[:50]
            tags = [re.sub(r"[^\w\s-]", "", tag).replace(" ", "-")]

        # If section fits in one chunk
        if len(section) <= max_chunk:
            chunks.append(
                {
                    "content": section,
                    "tags": tags,
                    "metadata": {"source": source, "type": "markdown"},
                }
            )
        else:
            # Split by paragraphs
            paragraphs = re.split(r"\n{2,}", section)
            buf = ""
            for para in paragraphs:
                candidate = f"{buf}\n\n{para}".strip() if buf else para
                if len(candidate) > max_chunk and buf:
                    chunks.append(
                        {
                            "content": buf,
                            "tags": tags,
                            "metadata": {"source": source, "type": "markdown"},
                        }
                    )
                    buf = para
                else:
                    buf = candidate
            if buf:
                chunks.append(
                    {
                        "content": buf,
                        "tags": tags,
                        "metadata": {"source": source, "type": "markdown"},
                    }
                )

    # If no headers found, treat whole doc as one chunk
    if not chunks and text.strip():
        chunks.append(
            {
                "content": text.strip(),
                "tags": [],
                "metadata": {"source": source, "type": "markdown"},
            }
        )

    return chunks


def _chunk_json(
    data: Any,
    source: str = "",
    max_chunk: int = 2000,
) -> list[dict[str, Any]]:
    """Parse JSON into memory items. Supports:
    - Array of objects with "content" field
    - Array of strings
    - Single object with "content" field
    - Flat key-value mapping
    """
    chunks: list[dict[str, Any]] = []

    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict) and "content" in item:
                tags = item.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",")]
                chunks.append(
                    {
                        "content": str(item["content"]).strip(),
                        "tags": tags,
                        "importance": item.get("importance", 0.5),
                        "metadata": {
                            **{k: v for k, v in item.items() if k not in ("content", "tags", "importance")},
                            "source": source,
                            "type": "json",
                        },
                    }
                )
            elif isinstance(item, str) and item.strip():
                chunks.append(
                    {
                        "content": item.strip(),
                        "tags": [],
                        "metadata": {"source": source, "type": "json", "index": i},
                    }
                )
    elif isinstance(data, dict):
        if "content" in data:
            tags = data.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]
            chunks.append(
                {
                    "content": str(data["content"]).strip(),
                    "tags": tags,
                    "importance": data.get("importance", 0.5),
                    "metadata": {
                        **{k: v for k, v in data.items() if k not in ("content", "tags", "importance")},
                        "source": source,
                        "type": "json",
                    },
                }
            )
        else:
            # Key-value → one chunk per entry
            for key, value in data.items():
                content = f"{key}: {value}"
                if len(content) <= max_chunk:
                    chunks.append(
                        {
                            "content": content,
                            "tags": [key.lower()[:30]],
                            "metadata": {"source": source, "type": "json", "key": key},
                        }
                    )
    return chunks


def ingest_file(
    path: str | Path,
    *,
    tags: Optional[list[str]] = None,
    importance: float = 0.5,
    max_chunk: int = 2000,
    dry_run: bool = False,
) -> IngestResult:
    """Parse a file into memory-ready chunks. Does NOT store — returns chunks."""
    path = Path(path)
    result = IngestResult()

    if not path.exists():
        result.errors.append(f"File not found: {path}")
        return result

    if not path.is_file():
        result.errors.append(f"Not a file: {path}")
        return result

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        result.errors.append(f"Read error: {e}")
        return result

    if not text.strip():
        result.skipped = 1
        return result

    source = str(path)
    suffix = path.suffix.lower()

    if suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            result.errors.append(f"Invalid JSON: {e}")
            return result
        chunks = _chunk_json(data, source=source, max_chunk=max_chunk)
    elif suffix in (".md", ".markdown", ".txt"):
        chunks = _chunk_markdown(text, source=source, max_chunk=max_chunk)
    else:
        result.errors.append(f"Unsupported format: {suffix}")
        return result

    # Apply user tags and importance
    for chunk in chunks:
        if tags:
            chunk["tags"] = list(set(chunk.get("tags", []) + tags))
        chunk["importance"] = importance

    result.total_chunks = len(chunks)
    result.chunks = chunks
    return result


def ingest_files(
    paths: list[str | Path],
    *,
    tags: Optional[list[str]] = None,
    importance: float = 0.5,
    max_chunk: int = 2000,
) -> IngestResult:
    """Ingest multiple files, merging results."""
    merged = IngestResult()
    for p in paths:
        r = ingest_file(p, tags=tags, importance=importance, max_chunk=max_chunk)
        merged.total_chunks += r.total_chunks
        merged.skipped += r.skipped
        merged.errors.extend(r.errors)
        merged.chunks.extend(r.chunks)
    return merged
