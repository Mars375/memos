"""Candidate discovery for compaction phases."""

from __future__ import annotations

import time

from .._constants import SECONDS_PER_DAY
from ..models import MemoryItem
from ._models import ClusterInfo


class CompactionDiscoveryMixin:
    """Find memories eligible for archive, merge, and cluster compaction."""

    def find_archive_candidates(self, items: list[MemoryItem]) -> list[MemoryItem]:
        """Find memories eligible for archival."""
        now = time.time()
        candidates = []

        for item in items:
            age_days = (now - item.created_at) / SECONDS_PER_DAY
            if age_days < self._config.archive_age_days:
                continue
            if item.importance >= self._config.archive_importance_floor:
                continue

            score = self._decay.adjusted_score(0.5, item)
            if score < self._config.stale_score_threshold:
                candidates.append(item)

        return candidates

    def find_stale_groups(self, items: list[MemoryItem]) -> list[ClusterInfo]:
        """Group stale memories by semantic similarity."""
        now = time.time()
        stale = []
        for item in items:
            if "archived" in item.tags:
                continue
            score = self._decay.adjusted_score(0.5, item)
            if score < self._config.stale_score_threshold:
                age_days = (now - item.created_at) / SECONDS_PER_DAY
                if age_days > 1.0:
                    stale.append(item)

        if len(stale) < self._config.cluster_min_size:
            return []

        tokenized = [(item, self._tokenize(item.content)) for item in stale]

        inv_index: dict[str, list[int]] = {}
        for index, (_, tokens) in enumerate(tokenized):
            for token in tokens:
                inv_index.setdefault(token, []).append(index)

        used: set[str] = set()
        groups: list[ClusterInfo] = []

        for index, (item_a, tokens_a) in enumerate(tokenized):
            if item_a.id in used or len(tokens_a) < 2:
                continue

            candidate_indices: set[int] = set()
            for token in tokens_a:
                for candidate_index in inv_index.get(token, []):
                    if candidate_index != index:
                        candidate_indices.add(candidate_index)

            similar = [(item_a, tokens_a)]
            for candidate_index in candidate_indices:
                item_b, tokens_b = tokenized[candidate_index]
                if item_b.id in used or len(tokens_b) < 2:
                    continue
                similarity = self._jaccard(tokens_a, tokens_b)
                if similarity >= self._config.merge_similarity_threshold:
                    similar.append((item_b, tokens_b))

            if len(similar) >= self._config.cluster_min_size:
                group_items = [similar_item[0] for similar_item in similar[: self._config.cluster_max_size]]
                ages = [(now - memory.created_at) / SECONDS_PER_DAY for memory in group_items]
                scores = [self._decay.adjusted_score(0.5, memory) for memory in group_items]
                dominant_tag = self._dominant_tag(group_items)

                groups.append(
                    ClusterInfo(
                        memories=group_items,
                        avg_importance=sum(memory.importance for memory in group_items) / len(group_items),
                        avg_age_days=sum(ages) / len(ages),
                        avg_score=sum(scores) / len(scores),
                        tag=dominant_tag,
                    )
                )

                for memory in group_items:
                    used.add(memory.id)

        return groups


__all__ = ["CompactionDiscoveryMixin"]
