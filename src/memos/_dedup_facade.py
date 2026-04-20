"""Dedup facade — near-duplicate detection and scanning."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from ._constants import DEFAULT_DEDUP_THRESHOLD
from .dedup import DedupCheckResult, DedupEngine, DedupScanResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DedupFacade:
    """Mixin providing dedup operations for the MemOS nucleus."""

    # ── Dedup ──────────────────────────────────────────

    @property
    def dedup_enabled(self) -> bool:
        """Whether dedup checking is enabled."""
        return self._dedup_enabled

    def dedup_set_enabled(self, enabled: bool = True, threshold: float = DEFAULT_DEDUP_THRESHOLD) -> None:
        """Enable or disable dedup checking at write time.

        Args:
            enabled: Enable dedup on learn().
            threshold: Similarity threshold (0.0-1.0) for near-duplicate detection.
        """
        self._dedup_enabled = enabled
        self._dedup_threshold = threshold
        if enabled:
            self._dedup_engine = DedupEngine(
                self._store,
                threshold=threshold,
                namespace=self._namespace or None,
            )
        else:
            self._dedup_engine = None

    def dedup_check(self, content: str, *, threshold: Optional[float] = None) -> DedupCheckResult:
        """Check if content would be a duplicate.

        Args:
            content: Content to check.
            threshold: Override threshold for this check.

        Returns:
            DedupCheckResult with is_duplicate, match, reason, similarity.
        """
        if self._dedup_engine is None:
            self._dedup_engine = DedupEngine(
                self._store,
                threshold=threshold or self._dedup_threshold,
                namespace=self._namespace or None,
            )
        return self._dedup_engine.check(content, threshold=threshold)

    def dedup_scan(self, *, fix: bool = False, threshold: Optional[float] = None) -> DedupScanResult:
        """Scan all memories for duplicates.

        Args:
            fix: If True, remove found duplicates.
            threshold: Override threshold for this scan.

        Returns:
            DedupScanResult with counts and details.
        """
        if self._dedup_engine is None:
            self._dedup_engine = DedupEngine(
                self._store,
                threshold=threshold or self._dedup_threshold,
                namespace=self._namespace or None,
            )
        result = self._dedup_engine.scan(fix=fix, threshold=threshold)
        if fix:
            self._dedup_engine.invalidate_cache()
        return result
