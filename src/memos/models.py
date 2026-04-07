"""Data models for MemOS."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional


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
    ttl: Optional[float] = None  # Time-to-live in seconds; None = no expiry

    def touch(self) -> None:
        """Update access metadata."""
        self.accessed_at = time.time()
        self.access_count += 1

    @property
    def expires_at(self) -> Optional[float]:
        """Unix timestamp when this memory expires, or None."""
        if self.ttl is None or self.ttl <= 0:
            return None
        return self.created_at + self.ttl

    @property
    def is_expired(self) -> bool:
        """Check if this memory has expired based on TTL."""
        if self.ttl is None or self.ttl <= 0:
            return False
        return time.time() > self.created_at + self.ttl


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
    expired_memories: int = 0
    top_tags: list[str] = field(default_factory=list)


def generate_id(content: str) -> str:
    """Generate a deterministic ID from content."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def parse_ttl(value: str) -> float:
    """Parse a human-readable TTL string into seconds.

    Supported formats:
        - "30s" → 30 seconds
        - "5m"  → 5 minutes
        - "2h"  → 2 hours
        - "7d"  → 7 days
        - "1w"  → 1 week
        - plain number → seconds

    Args:
        value: TTL string to parse.

    Returns:
        TTL in seconds.

    Raises:
        ValueError: If the format is invalid.
    """
    value = value.strip()
    if not value:
        raise ValueError("TTL cannot be empty")

    # Plain number → seconds
    try:
        return float(value)
    except ValueError:
        pass

    units = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }

    suffix = value[-1].lower()
    if suffix not in units:
        raise ValueError(
            f"Invalid TTL format: '{value}'. "
            f"Use a number or Ns/Nm/Nh/Nd/Nw (e.g., '30m', '2h', '7d')"
        )

    try:
        amount = float(value[:-1])
    except ValueError:
        raise ValueError(f"Invalid TTL amount in '{value}'")

    if amount <= 0:
        raise ValueError(f"TTL must be positive, got {amount}")

    return amount * units[suffix]
