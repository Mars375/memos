"""Data classes for living wiki."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _safe_slug(name: str) -> str:
    """Convert entity name to filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unnamed"


@dataclass
class LivingPage:
    """A single living wiki page."""

    entity: str
    entity_type: str
    path: Path
    memory_ids: List[str] = field(default_factory=list)
    backlinks: List[str] = field(default_factory=list)  # entity names
    created_at: float = 0.0
    updated_at: float = 0.0
    size_bytes: int = 0
    is_orphan: bool = False
    has_contradictions: bool = False
    _slug_cache: Optional[str] = field(default=None, repr=False)

    @property
    def slug(self) -> str:
        """Filesystem-safe slug for this page (derived from entity name)."""
        if self._slug_cache is not None:
            return self._slug_cache
        self._slug_cache = _safe_slug(self.entity)
        return self._slug_cache

    @property
    def memory_count(self) -> int:
        """Number of memories linked to this page."""
        return len(self.memory_ids)


@dataclass
class LintReport:
    """Result of linting the living wiki."""

    orphan_pages: List[str] = field(default_factory=list)
    empty_pages: List[str] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    stale_pages: List[str] = field(default_factory=list)  # no update in >30 days
    missing_backlinks: List[Tuple[str, str]] = field(default_factory=list)  # (from, to)


@dataclass
class UpdateResult:
    """Result of a living wiki update."""

    pages_created: int = 0
    pages_updated: int = 0
    entities_found: int = 0
    memories_indexed: int = 0
    backlinks_added: int = 0
