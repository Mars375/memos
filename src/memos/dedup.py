"""Memory Deduplication Engine — prevent duplicate memories at write time.

Two-phase check:
1. Exact match — SHA-256 on normalized content → O(1) via hash lookup
2. Near-duplicate — Jaccard similarity on trigrams → catches paraphrases

Integrates into MemOS.learn() to skip duplicates before insertion.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .models import MemoryItem
from .storage.base import StorageBackend

logger = logging.getLogger(__name__)


@dataclass
class DedupCheckResult:
    """Result of a duplicate check."""

    is_duplicate: bool = False
    match: Optional[MemoryItem] = None
    reason: str = ""  # "exact" | "near" | ""
    similarity: float = 0.0


@dataclass
class DedupScanResult:
    """Result of a batch dedup scan."""

    total_scanned: int = 0
    exact_duplicates: int = 0
    near_duplicates: int = 0
    total_duplicates: int = 0
    groups: list[dict] = field(default_factory=list)
    fixed: int = 0  # Number of duplicates actually removed


class DedupEngine:
    """Prevent duplicate memories with exact hash + near-duplicate trigram matching.

    Usage:
        engine = DedupEngine(store)
        result = engine.check("some content")
        if result.is_duplicate:
            print(f"Duplicate of {result.match.id} ({result.reason})")
    """

    def __init__(
        self,
        store: StorageBackend,
        *,
        threshold: float = 0.95,
        namespace: Optional[str] = None,
    ) -> None:
        self._store = store
        self._threshold = threshold
        self._namespace = namespace or ""
        self._hash_index: dict[str, MemoryItem] = {}
        self._built = False

    def _build_hash_index(self) -> None:
        """Build SHA-256 hash index from current store contents."""
        self._hash_index.clear()
        for item in self._store.list_all(namespace=self._namespace):
            h = self._content_hash(item.content)
            if h not in self._hash_index:
                self._hash_index[h] = item
        self._built = True

    def _ensure_index(self) -> None:
        """Lazily build the hash index if needed."""
        if not self._built:
            self._build_hash_index()

    def invalidate_cache(self) -> None:
        """Force rebuild of hash index on next check."""
        self._built = False

    def register(self, item: MemoryItem) -> None:
        """Register a newly inserted item in the hash index."""
        if not self._built:
            self._build_hash_index()
        h = self._content_hash(item.content)
        if h not in self._hash_index:
            self._hash_index[h] = item

    # --- Core check ---

    def check(self, content: str, *, threshold: Optional[float] = None) -> DedupCheckResult:
        """Check if content is a duplicate of existing memories.

        Args:
            content: The content to check.
            threshold: Override similarity threshold for this check.

        Returns:
            DedupCheckResult with is_duplicate, match, reason, similarity.
        """
        self._ensure_index()
        thresh = threshold if threshold is not None else self._threshold

        # Phase 1: Exact match via SHA-256
        h = self._content_hash(content)
        if h in self._hash_index:
            return DedupCheckResult(
                is_duplicate=True,
                match=self._hash_index[h],
                reason="exact",
                similarity=1.0,
            )

        # Phase 2: Near-duplicate via trigram Jaccard
        if thresh < 1.0:
            trigrams_new = self._trigrams(content)
            if not trigrams_new:
                return DedupCheckResult(is_duplicate=False)

            best_item = None
            best_sim = 0.0

            for item in self._store.list_all(namespace=self._namespace):
                trigrams_existing = self._trigrams(item.content)
                if not trigrams_existing:
                    continue
                sim = self._jaccard(trigrams_new, trigrams_existing)
                if sim > best_sim:
                    best_sim = sim
                    best_item = item

            if best_sim >= thresh and best_item is not None:
                return DedupCheckResult(
                    is_duplicate=True,
                    match=best_item,
                    reason="near",
                    similarity=round(best_sim, 4),
                )

        return DedupCheckResult(is_duplicate=False)

    def scan(
        self,
        *,
        fix: bool = False,
        threshold: Optional[float] = None,
    ) -> DedupScanResult:
        """Scan all memories for duplicates.

        Args:
            fix: If True, remove duplicates (keep oldest/highest importance).
            threshold: Override similarity threshold.

        Returns:
            DedupScanResult with counts and optional group details.
        """
        items = self._store.list_all(namespace=self._namespace)
        if len(items) < 2:
            return DedupScanResult(total_scanned=len(items))

        thresh = threshold if threshold is not None else self._threshold
        result = DedupScanResult(total_scanned=len(items))
        seen_hashes: dict[str, MemoryItem] = {}
        seen_trigrams: list[tuple[set[str], MemoryItem]] = []
        used: set[str] = set()

        for item in items:
            if item.id in used:
                continue

            h = self._content_hash(item.content)

            # Exact check
            if h in seen_hashes:
                original = seen_hashes[h]
                result.exact_duplicates += 1
                result.total_duplicates += 1
                result.groups.append(
                    {
                        "duplicate_id": item.id,
                        "original_id": original.id,
                        "reason": "exact",
                        "similarity": 1.0,
                        "content_preview": item.content[:100],
                    }
                )
                used.add(item.id)
                if fix:
                    self._store.delete(item.id, namespace=self._namespace)
                    result.fixed += 1
                continue

            seen_hashes[h] = item

            # Near-dup check
            if thresh < 1.0:
                tri = self._trigrams(item.content)
                if len(tri) < 2:
                    seen_trigrams.append((tri, item))
                    continue

                for existing_tri, existing_item in seen_trigrams:
                    if existing_item.id in used:
                        continue
                    sim = self._jaccard(tri, existing_tri)
                    if sim >= thresh:
                        result.near_duplicates += 1
                        result.total_duplicates += 1
                        result.groups.append(
                            {
                                "duplicate_id": item.id,
                                "original_id": existing_item.id,
                                "reason": "near",
                                "similarity": round(sim, 4),
                                "content_preview": item.content[:100],
                            }
                        )
                        used.add(item.id)
                        if fix:
                            self._store.delete(item.id, namespace=self._namespace)
                            result.fixed += 1
                        break
                else:
                    seen_trigrams.append((tri, item))

        return result

    # --- Helpers ---

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for hashing: lowercase, collapse whitespace, strip punctuation."""
        text = text.lower().strip()
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^\w\s]", "", text)
        return text

    @staticmethod
    def _content_hash(content: str) -> str:
        """SHA-256 hash of normalized content."""
        norm = DedupEngine._normalize(content)
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    @staticmethod
    def _trigrams(text: str) -> set[str]:
        """Extract character trigrams from normalized text."""
        norm = DedupEngine._normalize(text)
        if len(norm) < 3:
            return set()
        return {norm[i : i + 3] for i in range(len(norm) - 2)}

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        """Jaccard similarity between two sets."""
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)
