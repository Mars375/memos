"""Decay engine — smart forgetting for memory management.

Provides:
- Ebbinghaus-inspired exponential decay on relevance scores
- Access-based reinforcement (logarithmic bonus)
- Explicit reinforce() to boost importance
- run_decay() to batch-apply importance decay across all memories
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..models import MemoryItem


@dataclass
class DecayConfig:
    """Configuration for memory decay behavior."""
    rate: float = 0.01              # Relevance loss per day (exponential decay)
    access_boost: float = 0.05      # Relevance gain per access
    importance_floor: float = 0.1   # Minimum importance (memories don't decay below this)
    max_age_days: float = 365.0     # Hard age limit regardless of score
    max_memories: int = 10_000      # Evict oldest if over this
    reinforce_strength: float = 0.05  # Importance boost per reinforce call
    auto_reinforce: bool = True     # Auto-reinforce recalled memories
    decay_min_age_days: float = 7.0  # Don't decay memories younger than this


@dataclass
class DecayReport:
    """Report from a decay run."""
    total: int = 0
    decayed: int = 0
    pruned: int = 0
    reinforced: int = 0
    avg_importance_before: float = 0.0
    avg_importance_after: float = 0.0
    details: List[dict] = field(default_factory=list)


class DecayEngine:
    """Manages memory decay and pruning.

    Decay formula:
        adjusted_score = base_score * (1 - rate)^age_days
                       + importance * access_boost * log(access_count + 1)

    A memory with importance=1.0 (permanent) decays very slowly.
    A memory with importance=0.0 (ephemeral) decays fast.
    Frequently accessed memories are reinforced.
    """

    def __init__(
        self,
        rate: float = 0.01,
        max_memories: int = 10_000,
        reinforce_strength: float = 0.05,
        auto_reinforce: bool = True,
        importance_floor: float = 0.1,
        decay_min_age_days: float = 7.0,
    ) -> None:
        self.rate = rate
        self.max_memories = max_memories
        self.reinforce_strength = reinforce_strength
        self.auto_reinforce = auto_reinforce
        self.importance_floor = importance_floor
        self.decay_min_age_days = decay_min_age_days

    def adjusted_score(self, base_score: float, item: MemoryItem) -> float:
        """Calculate decay-adjusted relevance score."""
        age_days = (time.time() - item.created_at) / 86400

        # Exponential decay
        decay_factor = (1 - self.rate) ** age_days

        # Access reinforcement
        access_bonus = item.importance * self.reinforce_strength * math.log(item.access_count + 1)

        # Importance floor — important memories resist decay
        importance_floor = item.importance * 0.1

        adjusted = base_score * decay_factor + access_bonus + importance_floor
        return max(0.0, min(1.0, adjusted))

    def reinforce(self, item: MemoryItem, strength: Optional[float] = None) -> float:
        """Boost a memory's importance.

        Args:
            item: The memory to reinforce.
            strength: Override boost amount. Uses self.reinforce_strength if None.

        Returns:
            New importance value (clamped to [0, 1]).
        """
        boost = strength if strength is not None else self.reinforce_strength
        item.importance = min(1.0, item.importance + boost)
        item.touch()
        return item.importance

    def run_decay(
        self,
        items: List[MemoryItem],
        min_age_days: Optional[float] = None,
        floor: Optional[float] = None,
        dry_run: bool = False,
    ) -> DecayReport:
        """Apply importance decay to all eligible memories.

        For each memory older than min_age_days, reduce importance by the
        Ebbinghaus decay factor. Importance never goes below floor.

        Args:
            items: All memories to evaluate.
            min_age_days: Minimum age in days to be eligible. Uses config default if None.
            floor: Minimum importance after decay. Uses config default if None.
            dry_run: If True, don't modify items — just report.

        Returns:
            DecayReport with statistics and details.
        """
        min_age = min_age_days if min_age_days is not None else self.decay_min_age_days
        imp_floor = floor if floor is not None else self.importance_floor
        now = time.time()

        report = DecayReport(total=len(items))
        importance_before = []

        for item in items:
            age_days = (now - item.created_at) / 86400
            importance_before.append(item.importance)

            # Skip young memories
            if age_days < min_age:
                continue

            # Skip permanent memories (importance >= 0.9)
            if item.importance >= 0.9:
                continue

            # Calculate decay factor
            decay_factor = (1 - self.rate) ** age_days

            # New importance = max(floor, original * decay_factor)
            new_importance = max(imp_floor, item.importance * decay_factor)

            if new_importance < item.importance:
                report.decayed += 1
                report.details.append({
                    "id": item.id,
                    "importance_before": round(item.importance, 4),
                    "importance_after": round(new_importance, 4),
                    "age_days": round(age_days, 1),
                })
                if not dry_run:
                    item.importance = new_importance

        report.avg_importance_before = (
            sum(importance_before) / len(importance_before) if importance_before else 0.0
        )
        report.avg_importance_after = (
            sum(item.importance for item in items) / len(items) if items else 0.0
        )

        return report

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
