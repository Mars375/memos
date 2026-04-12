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
class ScoreBreakdown:
    """Detailed score breakdown for a recall result."""
    semantic: float = 0.0
    keyword: float = 0.0
    importance: float = 0.0
    recency: float = 0.0
    tag_bonus: float = 0.0
    total: float = 0.0
    backend: str = ""  # "hybrid" | "qdrant" | "keyword-only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic": round(self.semantic, 4),
            "keyword": round(self.keyword, 4),
            "importance": round(self.importance, 4),
            "recency": round(self.recency, 4),
            "tag_bonus": round(self.tag_bonus, 4),
            "total": round(self.total, 4),
            "backend": self.backend,
        }


@dataclass
class RecallResult:
    """Result from a recall query."""
    item: MemoryItem
    score: float  # 0.0 to 1.0
    match_reason: str = ""  # "semantic" | "keyword" | "recent" | "tag"
    score_breakdown: Optional[ScoreBreakdown] = None


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
    # Token compression reporting (P9)
    total_chars: int = 0        # sum of len(content) across all memories
    total_tokens: int = 0       # estimated tokens (chars // 4)
    prunable_tokens: int = 0    # tokens in decay-candidate memories
    expired_tokens: int = 0     # tokens in expired (TTL) memories


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


@dataclass
class FeedbackEntry:
    """A single relevance feedback entry for a memory item."""
    item_id: str
    feedback: str  # "relevant" or "not-relevant"
    query: str = ""  # the query that triggered the recall
    score_at_recall: float = 0.0  # score when the item was recalled
    agent_id: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "feedback": self.feedback,
            "query": self.query,
            "score_at_recall": self.score_at_recall,
            "agent_id": self.agent_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeedbackEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class FeedbackStats:
    """Statistics about feedback collected."""
    total_feedback: int = 0
    relevant_count: int = 0
    not_relevant_count: int = 0
    items_with_feedback: int = 0
    avg_feedback_score: float = 0.0  # +1 for relevant, -1 for not-relevant

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_feedback": self.total_feedback,
            "relevant_count": self.relevant_count,
            "not_relevant_count": self.not_relevant_count,
            "items_with_feedback": self.items_with_feedback,
            "avg_feedback_score": round(self.avg_feedback_score, 3),
        }
