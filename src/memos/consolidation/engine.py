"""Consolidation engine — find and merge semantically similar memories."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from ..models import MemoryItem, generate_id
from ..storage.base import StorageBackend


@dataclass
class DuplicateGroup:
    """A group of similar memories that can be merged."""
    keep: MemoryItem          # Best memory to keep (highest importance * recency)
    duplicates: list[MemoryItem]  # Memories to merge/remove
    similarity: float         # Average pairwise similarity (0-1)
    reason: str = ""          # "semantic" or "exact"


@dataclass
class ConsolidationResult:
    """Result of a consolidation run."""
    groups_found: int = 0
    memories_merged: int = 0
    space_freed: int = 0      # Number of memories removed
    details: list[DuplicateGroup] = field(default_factory=list)


class ConsolidationEngine:
    """Find and merge semantically similar memories.

    Two-phase approach:
    1. **Exact dedup** — normalize + compare (fast, no embeddings)
    2. **Semantic dedup** — token overlap / Jaccard similarity (no embeddings needed,
       works offline; can optionally use embeddings via the retrieval engine)

    Merge strategy:
    - Keep the item with highest (importance * recency_weight)
    - Merge tags from all duplicates
    - Optionally merge content (keep longest or concatenate unique parts)
    - Update access_count to sum of all merged items
    """

    def __init__(
        self,
        *,
        similarity_threshold: float = 0.75,
        use_embeddings: bool = False,
        embed_host: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
    ) -> None:
        self._threshold = similarity_threshold
        self._use_embeddings = use_embeddings
        self._embed_host = embed_host
        self._embed_model = embed_model

    def find_duplicates(
        self,
        items: list[MemoryItem],
        *,
        max_groups: int = 50,
    ) -> list[DuplicateGroup]:
        """Find groups of duplicate/near-duplicate memories.

        Returns groups sorted by similarity (most similar first).
        """
        if len(items) < 2:
            return []

        # Phase 1: exact dedup via normalized content
        exact_groups = self._find_exact_duplicates(items)

        # Phase 2: semantic dedup via token similarity
        remaining = self._items_not_in_groups(items, exact_groups)
        semantic_groups = self._find_semantic_duplicates(remaining)

        all_groups = exact_groups + semantic_groups
        all_groups.sort(key=lambda g: g.similarity, reverse=True)
        return all_groups[:max_groups]

    def consolidate(
        self,
        store: StorageBackend,
        *,
        merge_content: bool = False,
        dry_run: bool = False,
    ) -> ConsolidationResult:
        """Find and merge duplicate memories in the store.

        Args:
            store: The storage backend to operate on.
            merge_content: If True, concatenate unique content from duplicates.
            dry_run: If True, don't actually modify anything — just report.

        Returns:
            ConsolidationResult with counts and details.
        """
        items = store.list_all()
        groups = self.find_duplicates(items)

        if not groups:
            return ConsolidationResult(groups_found=0)

        result = ConsolidationResult(
            groups_found=len(groups),
            details=groups,
        )

        if dry_run:
            return result

        for group in groups:
            # Merge into the best item
            merged = self._merge(group.keep, group.duplicates, merge_content=merge_content)
            store.upsert(merged)

            # Remove duplicates
            for dup in group.duplicates:
                if dup.id != merged.id:
                    store.delete(dup.id)
                    result.space_freed += 1

            result.memories_merged += len(group.duplicates)

        return result

    # --- Phase 1: Exact dedup ---

    def _normalize(self, text: str) -> str:
        """Normalize text for exact comparison."""
        text = text.lower().strip()
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^\w\s]", "", text)
        return text

    def _find_exact_duplicates(self, items: list[MemoryItem]) -> list[DuplicateGroup]:
        """Find exact duplicates by normalized content."""
        by_norm: dict[str, list[MemoryItem]] = {}
        for item in items:
            norm = self._normalize(item.content)
            by_norm.setdefault(norm, []).append(item)

        groups = []
        for norm, group_items in by_norm.items():
            if len(group_items) < 2:
                continue
            keep = self._pick_best(group_items)
            dups = [i for i in group_items if i.id != keep.id]
            groups.append(DuplicateGroup(
                keep=keep,
                duplicates=dups,
                similarity=1.0,
                reason="exact",
            ))
        return groups

    # --- Phase 2: Semantic dedup ---

    def _tokenize(self, text: str) -> set[str]:
        """Tokenize text into a set of words."""
        words = re.findall(r"\w+", text.lower())
        # Remove very short tokens and common stopwords
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be",
                      "been", "being", "have", "has", "had", "do", "does",
                      "did", "will", "would", "could", "should", "may",
                      "might", "can", "shall", "to", "of", "in", "for",
                      "on", "with", "at", "by", "from", "as", "into",
                      "through", "during", "before", "after", "and", "but",
                      "or", "not", "no", "nor", "so", "yet", "both",
                      "either", "neither", "each", "every", "all", "any",
                      "few", "more", "most", "other", "some", "such",
                      "than", "too", "very", "just", "that", "this",
                      "these", "those", "it", "its", "i", "me", "my",
                      "we", "our", "you", "your", "he", "him", "his",
                      "she", "her", "they", "them", "their", "what",
                      "which", "who", "whom", "if", "then", "else",
                      "when", "where", "how", "about", "up", "out"}
        return {w for w in words if len(w) > 2 and w not in stopwords}

    def _jaccard(self, a: set[str], b: set[str]) -> float:
        """Jaccard similarity between two token sets."""
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _find_semantic_duplicates(self, items: list[MemoryItem]) -> list[DuplicateGroup]:
        """Find near-duplicates using token overlap (Jaccard similarity)."""
        # Pre-tokenize
        tokenized = [(item, self._tokenize(item.content)) for item in items]

        # Pairwise comparison with early termination
        groups = []
        used: set[str] = set()

        for i, (item_a, tokens_a) in enumerate(tokenized):
            if item_a.id in used or len(tokens_a) < 3:
                continue

            similar = []
            for j, (item_b, tokens_b) in enumerate(tokenized):
                if j <= i or item_b.id in used or len(tokens_b) < 3:
                    continue
                sim = self._jaccard(tokens_a, tokens_b)
                if sim >= self._threshold:
                    similar.append((item_b, sim))

            if similar:
                group_items = [item_a] + [s[0] for s in similar]
                keep = self._pick_best(group_items)
                dups = [i for i in group_items if i.id != keep.id]
                avg_sim = sum(s for _, s in similar) / len(similar)
                groups.append(DuplicateGroup(
                    keep=keep,
                    duplicates=dups,
                    similarity=round(avg_sim, 3),
                    reason="semantic",
                ))
                used.add(item_a.id)
                for s_item, _ in similar:
                    used.add(s_item.id)

        return groups

    # --- Merge ---

    def _pick_best(self, items: list[MemoryItem]) -> MemoryItem:
        """Pick the best item to keep: highest importance * recency."""
        def score(item: MemoryItem) -> float:
            age_days = (time.time() - item.created_at) / 86400
            recency = max(0.1, 1.0 - age_days / 90)  # Fade over 90 days
            return item.importance * 0.7 + recency * 0.3 + item.access_count * 0.01
        return max(items, key=score)

    def _merge(
        self,
        keep: MemoryItem,
        duplicates: list[MemoryItem],
        *,
        merge_content: bool = False,
    ) -> MemoryItem:
        """Merge duplicates into the kept item."""
        all_items = [keep] + duplicates

        # Merge tags (union)
        all_tags = set()
        for item in all_items:
            all_tags.update(item.tags)
        keep.tags = sorted(all_tags)

        # Sum access counts
        keep.access_count = sum(i.access_count for i in all_items)

        # Use most recent timestamp
        keep.created_at = min(i.created_at for i in all_items)
        keep.accessed_at = max(i.accessed_at for i in all_items)

        # Use highest importance
        keep.importance = max(i.importance for i in all_items)

        # Merge metadata
        for item in duplicates:
            if item.metadata:
                for k, v in item.metadata.items():
                    if k not in keep.metadata:
                        keep.metadata[k] = v

        # Optionally merge content
        if merge_content:
            unique_parts = self._extract_unique_parts(keep.content, [d.content for d in duplicates])
            if len(unique_parts) > 1:
                keep.content = "\n".join(unique_parts)
                keep.id = generate_id(keep.content)

        return keep

    def _extract_unique_parts(self, primary: str, others: list[str]) -> list[str]:
        """Extract unique content parts from duplicate contents."""
        parts = [primary]
        primary_tokens = self._tokenize(primary)

        for other in others:
            other_tokens = self._tokenize(other)
            # If >40% of tokens are new, include as additional content
            new_tokens = other_tokens - primary_tokens
            if new_tokens and len(new_tokens) / max(len(other_tokens), 1) > 0.4:
                parts.append(other)

        return parts

    @staticmethod
    def _items_not_in_groups(
        items: list[MemoryItem],
        groups: list[DuplicateGroup],
    ) -> list[MemoryItem]:
        """Return items not already in a duplicate group."""
        used_ids: set[str] = set()
        for g in groups:
            used_ids.add(g.keep.id)
            for d in g.duplicates:
                used_ids.add(d.id)
        return [i for i in items if i.id not in used_ids]
