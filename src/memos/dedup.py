"""Memory deduplication helpers for MemOS."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .models import MemoryItem


@dataclass
class DedupCheckResult:
    """A duplicate match for an incoming memory."""

    item: MemoryItem
    similarity: float
    reason: str  # "exact" | "near"


@dataclass
class DedupGroup:
    """A group of duplicate memories found in the store."""

    keep: MemoryItem
    duplicates: list[MemoryItem]
    similarity: float
    reason: str  # "exact" | "near"


@dataclass
class DedupScanResult:
    """Result of a dedup scan over the memory store."""

    groups_found: int = 0
    duplicates_found: int = 0
    duplicates_removed: int = 0
    details: list[DedupGroup] = field(default_factory=list)


class DedupEngine:
    """Detect exact and near-duplicate memories.

    Exact matching uses SHA-256 over normalized text (trim + lowercase).
    Near-duplicate matching uses Jaccard similarity over character trigrams.
    """

    def normalize(self, text: str) -> str:
        """Normalize text for stable duplicate checks."""
        return text.strip().lower()

    def normalized_hash(self, text: str) -> str:
        """Return the SHA-256 hash of normalized text."""
        return hashlib.sha256(self.normalize(text).encode("utf-8")).hexdigest()

    def check(
        self,
        content: str,
        existing: list[MemoryItem],
        *,
        threshold: float = 0.95,
    ) -> DedupCheckResult | None:
        """Check whether content is an exact or near duplicate."""
        normalized = self.normalize(content)
        if not normalized:
            return None

        target_hash = self.normalized_hash(content)
        for item in existing:
            if self.normalized_hash(item.content) == target_hash:
                return DedupCheckResult(item=item, similarity=1.0, reason="exact")

        target_trigrams = self._trigrams(normalized)
        best_match: DedupCheckResult | None = None
        for item in existing:
            similarity = self._jaccard(target_trigrams, self._trigrams(item.content))
            if similarity < threshold:
                continue
            if best_match is None or similarity > best_match.similarity:
                best_match = DedupCheckResult(item=item, similarity=similarity, reason="near")
        return best_match

    def is_duplicate(
        self,
        content: str,
        existing: list[MemoryItem],
        *,
        threshold: float = 0.95,
    ) -> MemoryItem | None:
        """Return the matched item if content is a duplicate."""
        match = self.check(content, existing, threshold=threshold)
        return match.item if match else None

    def scan(
        self,
        items: list[MemoryItem],
        *,
        threshold: float = 0.95,
    ) -> DedupScanResult:
        """Find exact and near-duplicate groups in a memory list."""
        if len(items) < 2:
            return DedupScanResult()

        exact_groups = self._find_exact_groups(items)
        remaining = self._items_not_in_groups(items, exact_groups)
        near_groups = self._find_near_groups(remaining, threshold=threshold)
        groups = exact_groups + near_groups
        groups.sort(key=lambda g: g.similarity, reverse=True)

        return DedupScanResult(
            groups_found=len(groups),
            duplicates_found=sum(len(group.duplicates) for group in groups),
            details=groups,
        )

    def merge_group(self, group: DedupGroup) -> MemoryItem:
        """Merge duplicate metadata into the kept item before deleting others."""
        keep = group.keep
        all_items = [keep] + group.duplicates

        keep.tags = sorted({tag for item in all_items for tag in item.tags})
        keep.importance = max(item.importance for item in all_items)
        keep.access_count = sum(item.access_count for item in all_items)
        keep.created_at = min(item.created_at for item in all_items)
        keep.accessed_at = max(item.accessed_at for item in all_items)

        merged_meta = dict(keep.metadata)
        for item in group.duplicates:
            for key, value in item.metadata.items():
                merged_meta.setdefault(key, value)
        keep.metadata = merged_meta
        return keep

    def _find_exact_groups(self, items: list[MemoryItem]) -> list[DedupGroup]:
        by_hash: dict[str, list[MemoryItem]] = {}
        for item in items:
            by_hash.setdefault(self.normalized_hash(item.content), []).append(item)

        groups: list[DedupGroup] = []
        for group_items in by_hash.values():
            if len(group_items) < 2:
                continue
            keep = self._pick_keep(group_items)
            groups.append(
                DedupGroup(
                    keep=keep,
                    duplicates=[item for item in group_items if item.id != keep.id],
                    similarity=1.0,
                    reason="exact",
                )
            )
        return groups

    def _find_near_groups(self, items: list[MemoryItem], *, threshold: float) -> list[DedupGroup]:
        groups: list[DedupGroup] = []
        used_ids: set[str] = set()
        tokenized = [(item, self._trigrams(item.content)) for item in items]

        for index, (item_a, grams_a) in enumerate(tokenized):
            if item_a.id in used_ids or not grams_a:
                continue

            similar: list[tuple[MemoryItem, float]] = []
            for other_index, (item_b, grams_b) in enumerate(tokenized):
                if other_index <= index or item_b.id in used_ids or not grams_b:
                    continue
                similarity = self._jaccard(grams_a, grams_b)
                if similarity >= threshold:
                    similar.append((item_b, similarity))

            if not similar:
                continue

            group_items = [item_a] + [item for item, _ in similar]
            keep = self._pick_keep(group_items)
            groups.append(
                DedupGroup(
                    keep=keep,
                    duplicates=[item for item in group_items if item.id != keep.id],
                    similarity=round(sum(score for _, score in similar) / len(similar), 3),
                    reason="near",
                )
            )
            for item in group_items:
                used_ids.add(item.id)

        return groups

    def _pick_keep(self, items: list[MemoryItem]) -> MemoryItem:
        return max(
            items,
            key=lambda item: (
                item.importance,
                item.access_count,
                -item.created_at,
            ),
        )

    def _trigrams(self, text: str) -> set[str]:
        normalized = re.sub(r"\s+", " ", self.normalize(text))
        if not normalized:
            return set()
        if len(normalized) < 3:
            return {normalized}
        return {normalized[index:index + 3] for index in range(len(normalized) - 2)}

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    @staticmethod
    def _items_not_in_groups(items: list[MemoryItem], groups: list[DedupGroup]) -> list[MemoryItem]:
        grouped_ids: set[str] = set()
        for group in groups:
            grouped_ids.add(group.keep.id)
            grouped_ids.update(item.id for item in group.duplicates)
        return [item for item in items if item.id not in grouped_ids]
