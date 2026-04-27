"""Shared helper methods for compaction."""

from __future__ import annotations

import re
import time

from .._constants import (
    CLUSTER_SUMMARY_IMPORTANCE_FACTOR,
    CLUSTER_SUMMARY_MIN_IMPORTANCE,
    COMPACTION_MERGE_IMPORTANCE_BOOST,
    STALE_MERGE_NOVELTY_RATIO,
)
from ..consolidation.engine import ConsolidationEngine
from ..models import MemoryItem, generate_id


class CompactionHelperMixin:
    """Pure helper methods used by compaction phases and discovery."""

    _STOPWORDS = ConsolidationEngine._STOPWORDS

    def _merge_stale_group(self, memories: list[MemoryItem]) -> MemoryItem:
        """Merge a group of stale memories into one summary memory."""
        memories.sort(key=lambda memory: memory.importance, reverse=True)
        base = memories[0]

        all_content = [base.content]
        base_tokens = self._tokenize(base.content)
        for memory in memories[1:]:
            memory_tokens = self._tokenize(memory.content)
            new_ratio = len(memory_tokens - base_tokens) / max(len(memory_tokens), 1)
            if new_ratio > STALE_MERGE_NOVELTY_RATIO:
                all_content.append(memory.content)

        all_tags = set()
        for memory in memories:
            all_tags.update(memory.tags)
        all_tags.discard("archived")

        merged_meta: dict = {
            "compacted": True,
            "compacted_from": len(memories),
            "compacted_at": time.time(),
        }
        for memory in memories:
            if memory.metadata:
                for key, value in memory.metadata.items():
                    if key not in merged_meta:
                        merged_meta[key] = value

        if len(all_content) == 1:
            content = all_content[0]
        else:
            content = "\n".join(f"• {part}" for part in all_content)

        new_id = generate_id(content)
        max_importance = max(memory.importance for memory in memories)

        return MemoryItem(
            id=new_id,
            content=content,
            tags=sorted(all_tags),
            importance=min(max_importance + COMPACTION_MERGE_IMPORTANCE_BOOST, 1.0),
            created_at=min(memory.created_at for memory in memories),
            accessed_at=max(memory.accessed_at for memory in memories),
            access_count=sum(memory.access_count for memory in memories),
            metadata=merged_meta,
        )

    def _create_cluster_summary(self, tag: str, items: list[MemoryItem]) -> MemoryItem:
        """Create a summary memory for a cluster of related items."""
        key_points = []
        for item in items:
            content = item.content.strip()
            if len(content) > 200:
                first_sentence = re.split(r"[.!?]", content)[0]
                key_points.append(first_sentence.strip()[:200])
            else:
                key_points.append(content)

        summary_lines = [f"[{tag}] Summary ({len(items)} memories):"]
        for index, point in enumerate(key_points[:20], 1):
            summary_lines.append(f"{index}. {point}")
        if len(key_points) > 20:
            summary_lines.append(f"... and {len(key_points) - 20} more")

        content = "\n".join(summary_lines)

        return MemoryItem(
            id=generate_id(content),
            content=content,
            tags=[tag, "compacted"],
            importance=max(
                CLUSTER_SUMMARY_MIN_IMPORTANCE,
                max(item.importance for item in items) * CLUSTER_SUMMARY_IMPORTANCE_FACTOR,
            ),
            created_at=min(item.created_at for item in items),
            accessed_at=time.time(),
            access_count=sum(item.access_count for item in items),
            metadata={
                "compacted": True,
                "compacted_from": len(items),
                "compacted_at": time.time(),
                "compaction_type": "cluster_summary",
            },
        )

    @classmethod
    def _tokenize(cls, text: str) -> set[str]:
        words = re.findall(r"\w+", text.lower())
        return {word for word in words if len(word) > 2 and word not in cls._STOPWORDS}

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    @staticmethod
    def _dominant_tag(items: list[MemoryItem]) -> str:
        """Find the most common tag among items."""
        counts: dict[str, int] = {}
        for item in items:
            for tag in item.tags:
                if tag != "archived":
                    counts[tag] = counts.get(tag, 0) + 1
        if not counts:
            return ""
        return max(counts, key=counts.get)


__all__ = ["CompactionHelperMixin"]
