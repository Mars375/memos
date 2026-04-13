"""Memory compression for very low-importance memories."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .models import MemoryItem, generate_id


@dataclass
class CompressionResult:
    """Summary of a compression run."""

    compressed_count: int = 0
    summary_count: int = 0
    freed_bytes: int = 0
    groups_considered: int = 0
    summaries: list[MemoryItem] = field(default_factory=list)
    deleted_ids: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)


class MemoryCompressor:
    """Compress very low-importance memories into aggregate summaries."""

    def compress(
        self,
        items: list[MemoryItem],
        threshold: float = 0.1,
    ) -> CompressionResult:
        eligible = [
            item
            for item in items
            if item.importance < threshold
            and not item.is_expired
            and not item.metadata.get("compressed")
            and "compressed" not in item.tags
        ]

        grouped: dict[tuple[str, ...], list[MemoryItem]] = {}
        for item in eligible:
            key = tuple(sorted(t for t in item.tags if t and t != "compressed"))
            if not key:
                key = ("untagged",)
            grouped.setdefault(key, []).append(item)

        result = CompressionResult(groups_considered=len(grouped))
        now = time.time()

        for key, group in grouped.items():
            if len(group) < 2:
                continue

            group = sorted(group, key=lambda item: (item.importance, item.created_at))
            summary = self._build_summary(group, key, now)
            freed_bytes = sum(len(item.content.encode("utf-8")) for item in group) - len(
                summary.content.encode("utf-8")
            )

            result.compressed_count += len(group)
            result.summary_count += 1
            result.freed_bytes += max(0, freed_bytes)
            result.summaries.append(summary)
            result.deleted_ids.extend(item.id for item in group)
            result.details.append(
                {
                    "tags": list(key),
                    "source_count": len(group),
                    "summary_id": summary.id,
                    "freed_bytes": max(0, freed_bytes),
                }
            )

        return result

    def _build_summary(
        self,
        items: list[MemoryItem],
        tags: tuple[str, ...],
        now: float,
    ) -> MemoryItem:
        pieces = [item.content.strip().replace("\n", " ") for item in items if item.content.strip()]
        content = " | ".join(pieces)
        summary_content = f"[compressed:{'/'.join(tags)}] {content}"
        return MemoryItem(
            id=generate_id(summary_content),
            content=summary_content,
            tags=sorted(set(tags) | {"compressed"}),
            importance=0.15,
            created_at=min(item.created_at for item in items),
            accessed_at=now,
            access_count=sum(item.access_count for item in items),
            metadata={
                "compressed": True,
                "compressed_from": len(items),
                "compressed_at": now,
                "source_ids": [item.id for item in items],
            },
        )
