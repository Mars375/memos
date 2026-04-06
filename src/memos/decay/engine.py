"""Decay engine — smart forgetting for memory management."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..models import MemoryItem


@dataclass
class DecayConfig:
    """Configuration for memory decay behavior."""
    rate: float = 0.01          # Relevance loss per day (exponential decay)
    access_boost: float = 0.05  # Relevance gain per access
    importance_floor: float = 0.1  # Memories above this importance never fully decay
    max_age_days: float = 365.0    # Hard age limit regardless of score
    max_memories: int = 10_000     # Evict oldest if over this


class DecayEngine:
    """Manages memory decay and pruning.
    
    Decay formula:
        adjusted_score = base_score * (1 - rate)^age_days + importance * access_boost * log(access_count + 1)
    
    A memory with importance=1.0 (permanent) decays very slowly.
    A memory with importance=0.0 (ephemeral) decays fast.
    Frequently accessed memories are reinforced.
    """

    def __init__(self, rate: float = 0.01, max_memories: int = 10_000) -> None:
        self.rate = rate
        self.max_memories = max_memories

    def adjusted_score(self, base_score: float, item: MemoryItem) -> float:
        """Calculate decay-adjusted relevance score."""
        age_days = (time.time() - item.created_at) / 86400

        # Exponential decay
        decay_factor = (1 - self.rate) ** age_days

        # Access reinforcement
        import math
        access_bonus = item.importance * 0.05 * math.log(item.access_count + 1)

        # Importance floor — important memories resist decay
        importance_floor = item.importance * 0.1

        adjusted = base_score * decay_factor + access_bonus + importance_floor
        return max(0.0, min(1.0, adjusted))

    def find_prune_candidates(
        self,
        items: list[MemoryItem],
        threshold: float = 0.1,
        max_age_days: float = 90.0,
    ) -> list[MemoryItem]:
        """Find memories that should be pruned.
        
        A memory is a prune candidate if:
        1. Its adjusted score is below threshold, AND
        2. It's older than some minimum age (1 day), AND
        3. It's either below max_age_days or has low importance
        """
        now = time.time()
        candidates = []

        for item in items:
            age_days = (now - item.created_at) / 86400

            # Never prune very recent memories (under 1 day)
            if age_days < 1.0:
                continue

            # Never prune high-importance memories unless very old
            if item.importance >= 0.9 and age_days < max_age_days:
                continue

            # Prune if decayed (never prune by age alone if high importance)
            adjusted = self.adjusted_score(0.5, item)  # Use median base score
            if adjusted < threshold or (age_days > max_age_days and item.importance < 0.9):
                candidates.append(item)

        # Sort: lowest score first (prune worst first)
        candidates.sort(key=lambda x: self.adjusted_score(0.5, x))

        # If over max_memories, also evict oldest low-importance
        if len(items) > self.max_memories:
            excess = len(items) - self.max_memories
            old_low = sorted(
                [i for i in items if i.importance < 0.5],
                key=lambda x: x.created_at,
            )
            for item in old_low[:excess]:
                if item not in candidates:
                    candidates.append(item)

        return candidates
