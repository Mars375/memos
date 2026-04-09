"""Memory compression for decayed memories."""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable

from .models import MemoryItem, generate_id


@dataclass
class CompressionGroup:
    """Details for a compressed group of memories."""

    group_key: str
    source_ids: list[str] = field(default_factory=list)
    source_count: int = 0
    source_bytes: int = 0
    summary_bytes: int = 0
    summary_preview: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "group_key": self.group_key,
            "source_ids": self.source_ids,
            "source_count": self.source_count,
            "source_bytes": self.source_bytes,
            "summary_bytes": self.summary_bytes,
            "summary_preview": self.summary_preview,
            "tags": self.tags,
        }


@dataclass
class CompressionResult:
    """Result of a compression pass."""

    compressed_count: int = 0
    summary_count: int = 0
    freed_bytes: int = 0
    skipped_count: int = 0
    deleted_ids: list[str] = field(default_factory=list)
    summaries: list[MemoryItem] = field(default_factory=list)
    groups: list[CompressionGroup] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "compressed_count": self.compressed_count,
            "summary_count": self.summary_count,
            "freed_bytes": self.freed_bytes,
            "skipped_count": self.skipped_count,
            "deleted_ids": self.deleted_ids,
            "summaries": [
                {
                    "id": item.id,
                    "content": item.content,
                    "tags": item.tags,
                    "importance": item.importance,
                    "created_at": item.created_at,
                    "metadata": item.metadata,
                }
                for item in self.summaries
            ],
            "groups": [group.to_dict() for group in self.groups],
        }


class MemoryCompressor:
    """Compress low-importance memories into grouped summaries."""

    def __init__(
        self,
        *,
        separator: str = " | ",
        summary_importance: float = 0.15,
        min_group_size: int = 2,
        summarizer: Callable[[list[MemoryItem]], str] | None = None,
    ) -> None:
        self.separator = separator
        self.summary_importance = summary_importance
        self.min_group_size = min_group_size
        self.summarizer = summarizer

    def compress(
        self,
        items: list[MemoryItem],
        threshold: float = 0.1,
    ) -> CompressionResult:
        """Plan compression for memories below the importance threshold."""
        eligible = [
            item
            for item in items
            if item.importance < threshold
            and "compressed" not in {tag.lower() for tag in item.tags}
            and not item.metadata.get("compression")
        ]
        if not eligible:
            return CompressionResult(skipped_count=len(items))

        buckets = self._group_items(eligible)
        result = CompressionResult()

        for group_key, bucket in sorted(buckets.items()):
            if len(bucket) < self.min_group_size:
                result.skipped_count += len(bucket)
                continue

            summary = self._build_summary(group_key, bucket, threshold=threshold)
            source_bytes = sum(len(item.content.encode("utf-8")) for item in bucket)
            summary_bytes = len(summary.content.encode("utf-8"))

            result.compressed_count += len(bucket)
            result.summary_count += 1
            result.freed_bytes += max(0, source_bytes - summary_bytes)
            result.deleted_ids.extend(item.id for item in bucket)
            result.summaries.append(summary)
            result.groups.append(
                CompressionGroup(
                    group_key=group_key,
                    source_ids=[item.id for item in bucket],
                    source_count=len(bucket),
                    source_bytes=source_bytes,
                    summary_bytes=summary_bytes,
                    summary_preview=summary.content[:200],
                    tags=summary.tags,
                )
            )

        return result

    def _group_items(self, items: list[MemoryItem]) -> dict[str, list[MemoryItem]]:
        tag_counts = Counter(
            tag.lower().strip()
            for item in items
            for tag in item.tags
            if tag and tag.strip()
        )
        buckets: dict[str, list[MemoryItem]] = defaultdict(list)

        for item in items:
            normalized_tags = sorted({tag.lower().strip() for tag in item.tags if tag and tag.strip()})
            if not normalized_tags:
                buckets["untagged"].append(item)
                continue

            best_tag = sorted(
                normalized_tags,
                key=lambda tag: (-tag_counts.get(tag, 0), tag),
            )[0]
            buckets[best_tag].append(item)

        return buckets

    def _build_summary(
        self,
        group_key: str,
        items: list[MemoryItem],
        *,
        threshold: float,
    ) -> MemoryItem:
        ordered = sorted(items, key=lambda item: (item.created_at, item.id))
        unique_contents: list[str] = []
        seen: set[str] = set()
        for item in ordered:
            content = item.content.strip()
            if not content or content in seen:
                continue
            seen.add(content)
            unique_contents.append(content)

        if self.summarizer is not None:
            try:
                summary_content = self.summarizer(ordered).strip()
            except Exception:
                summary_content = ""
        else:
            summary_content = ""

        if not summary_content:
            summary_content = self.separator.join(unique_contents)

        shared_tags = self._shared_tags(ordered)
        summary_tags = list(shared_tags)
        if group_key != "untagged" and group_key not in summary_tags:
            summary_tags.append(group_key)
        if "compressed" not in summary_tags:
            summary_tags.append("compressed")

        created_at = max(item.created_at for item in ordered)
        now = time.time()
        payload = f"compressed:{group_key}:{summary_content}"
        metadata = {
            "compression": {
                "group_key": group_key,
                "source_ids": [item.id for item in ordered],
                "source_count": len(ordered),
                "threshold": threshold,
                "mode": "llm" if self.summarizer is not None else "concat",
                "compressed_at": now,
            }
        }
        return MemoryItem(
            id=generate_id(payload),
            content=summary_content,
            tags=summary_tags,
            importance=self.summary_importance,
            created_at=created_at,
            accessed_at=created_at,
            metadata=metadata,
        )

    @staticmethod
    def _shared_tags(items: list[MemoryItem]) -> list[str]:
        if not items:
            return []
        shared = {
            tag.lower().strip()
            for tag in items[0].tags
            if tag and tag.strip()
        }
        for item in items[1:]:
            shared &= {
                tag.lower().strip()
                for tag in item.tags
                if tag and tag.strip()
            }
        return sorted(shared)
