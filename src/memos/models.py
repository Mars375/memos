"""Data models for MemOS."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryItem:
    """A single memory entry."""
    id: str
    content: str
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5  # 0.0 = ephemeral, 1.0 = permanent
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    relevance_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update access metadata."""
        self.accessed_at = time.time()
        self.access_count += 1


@dataclass
class RecallResult:
    """Result from a recall query."""
    item: MemoryItem
    score: float  # 0.0 to 1.0
    match_reason: str = ""  # "semantic" | "keyword" | "recent" | "tag"


@dataclass
class MemoryStats:
    """Statistics about the memory store."""
    total_memories: int = 0
    total_tags: int = 0
    avg_relevance: float = 0.0
    avg_importance: float = 0.0
    oldest_memory_days: float = 0.0
    newest_memory_days: float = 0.0
    decay_candidates: int = 0
    top_tags: list[str] = field(default_factory=list)


def generate_id(content: str) -> str:
    """Generate a deterministic ID from content."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]
