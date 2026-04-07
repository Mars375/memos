"""Compaction engine — merge stale memories, archive old ones, reclaim space."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from ..models import MemoryItem, generate_id
from ..storage.base import StorageBackend
from ..decay.engine import DecayEngine
from ..consolidation.engine import ConsolidationEngine, DuplicateGroup


@dataclass
class CompactionConfig:
    """Configuration for memory compaction."""
    # Age-based archiving
    archive_age_days: float = 90.0          # Age threshold for archiving
    archive_importance_floor: float = 0.3   # Never archive above this importance

    # Stale memory merging
    stale_score_threshold: float = 0.25     # Score below which a memory is "stale"
    merge_similarity_threshold: float = 0.6 # Jaccard threshold for grouping stales

    # Cluster compaction
    cluster_min_size: int = 3               # Min memories to form a cluster
    cluster_max_size: int = 20              # Max memories per cluster

    # Safety
    dry_run: bool = False                   # If True, don't modify anything
    max_compact_per_run: int = 200          # Cap on modifications per run


@dataclass
class ClusterInfo:
    """A group of related memories identified for compaction."""
    memories: list[MemoryItem]
    avg_importance: float
    avg_age_days: float
    avg_score: float
    tag: str = ""                           # Dominant tag


@dataclass
class CompactionReport:
    """Result of a compaction run."""
    # Archiving
    archived: int = 0
    archive_details: list[dict] = field(default_factory=list)

    # Stale merging
    stale_merged: int = 0
    stale_groups: int = 0

    # Cluster compaction
    clusters_compacted: int = 0
    cluster_details: list[dict] = field(default_factory=list)

    # Dedup (runs first)
    dedup_groups: int = 0
    dedup_merged: int = 0

    # Totals
    total_removed: int = 0
    total_added: int = 0
    net_delta: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "archived": self.archived,
            "stale_merged": self.stale_merged,
            "stale_groups": self.stale_groups,
            "clusters_compacted": self.clusters_compacted,
            "dedup_groups": self.dedup_groups,
            "dedup_merged": self.dedup_merged,
            "total_removed": self.total_removed,
            "total_added": self.total_added,
            "net_delta": self.net_delta,
            "duration_seconds": round(self.duration_seconds, 3),
            "archive_details": self.archive_details[:10],  # Cap for readability
            "cluster_details": self.cluster_details[:10],
        }


class CompactionEngine:
    """Full lifecycle compaction for memory stores.

    Pipeline:
    1. Dedup — find and merge exact/near-duplicates (via ConsolidationEngine)
    2. Archive — move very old, low-relevance memories to archive tag
    3. Stale merge — group and merge memories with low decay scores
    4. Cluster compact — compress large clusters of related memories

    Each phase produces a count and details. The full report is returned.
    """

    def __init__(
        self,
        config: Optional[CompactionConfig] = None,
        *,
        decay_rate: float = 0.01,
        max_memories: int = 10_000,
    ) -> None:
        self._config = config or CompactionConfig()
        self._decay = DecayEngine(rate=decay_rate, max_memories=max_memories)
        self._consolidation = ConsolidationEngine(
            similarity_threshold=self._config.merge_similarity_threshold,
        )

    def compact(self, store: StorageBackend) -> CompactionReport:
        """Run the full compaction pipeline.

        Args:
            store: Storage backend to compact.

        Returns:
            CompactionReport with detailed results.
        """
        start = time.time()
        report = CompactionReport()
        items = store.list_all()

        if len(items) < 2:
            report.duration_seconds = time.time() - start
            return report

        # Phase 1: Dedup
        self._phase_dedup(store, items, report)

        # Phase 2: Archive old low-relevance
        items = store.list_all()  # Refresh after dedup
        self._phase_archive(store, items, report)

        # Phase 3: Merge stale memories
        items = store.list_all()  # Refresh after archive
        self._phase_stale_merge(store, items, report)

        # Phase 4: Cluster compaction
        items = store.list_all()  # Refresh after stale merge
        self._phase_cluster_compact(store, items, report)

        # Compute totals
        report.total_removed = report.archived + report.dedup_merged + report.stale_merged
        report.net_delta = report.total_added - report.total_removed
        report.duration_seconds = time.time() - start

        return report

    def find_archive_candidates(
        self, items: list[MemoryItem]
    ) -> list[MemoryItem]:
        """Find memories eligible for archival."""
        now = time.time()
        candidates = []

        for item in items:
            age_days = (now - item.created_at) / 86400

            # Skip recent
            if age_days < self._config.archive_age_days:
                continue

            # Skip high-importance
            if item.importance >= self._config.archive_importance_floor:
                continue

            # Check decay score
            score = self._decay.adjusted_score(0.5, item)
            if score < self._config.stale_score_threshold:
                candidates.append(item)

        return candidates

    def find_stale_groups(
        self, items: list[MemoryItem]
    ) -> list[ClusterInfo]:
        """Group stale memories by semantic similarity."""
        now = time.time()
        stale = []
        for item in items:
            # Skip already-archived memories
            if "archived" in item.tags:
                continue
            score = self._decay.adjusted_score(0.5, item)
            if score < self._config.stale_score_threshold:
                age_days = (now - item.created_at) / 86400
                if age_days > 1.0:  # At least 1 day old
                    stale.append(item)

        if len(stale) < self._config.cluster_min_size:
            return []

        # Group by Jaccard similarity
        tokenized = [(item, self._tokenize(item.content)) for item in stale]
        used: set[str] = set()
        groups: list[ClusterInfo] = []

        for i, (item_a, tokens_a) in enumerate(tokenized):
            if item_a.id in used or len(tokens_a) < 2:
                continue

            similar = [(item_a, tokens_a)]
            for j, (item_b, tokens_b) in enumerate(tokenized):
                if j == i or item_b.id in used or len(tokens_b) < 2:
                    continue
                sim = self._jaccard(tokens_a, tokens_b)
                if sim >= self._config.merge_similarity_threshold:
                    similar.append((item_b, tokens_b))

            if len(similar) >= self._config.cluster_min_size:
                group_items = [s[0] for s in similar[:self._config.cluster_max_size]]
                ages = [(now - m.created_at) / 86400 for m in group_items]
                scores = [self._decay.adjusted_score(0.5, m) for m in group_items]
                dominant_tag = self._dominant_tag(group_items)

                groups.append(ClusterInfo(
                    memories=group_items,
                    avg_importance=sum(m.importance for m in group_items) / len(group_items),
                    avg_age_days=sum(ages) / len(ages),
                    avg_score=sum(scores) / len(scores),
                    tag=dominant_tag,
                ))

                for m in group_items:
                    used.add(m.id)

        return groups

    # ── Phase implementations ──────────────────────────────

    def _phase_dedup(
        self,
        store: StorageBackend,
        items: list[MemoryItem],
        report: CompactionReport,
    ) -> None:
        """Phase 1: Remove exact/near-duplicates."""
        if self._config.dry_run:
            groups = self._consolidation.find_duplicates(items)
            report.dedup_groups = len(groups)
            report.dedup_merged = sum(len(g.duplicates) for g in groups)
            return

        result = self._consolidation.consolidate(
            store, merge_content=False, dry_run=False,
        )
        report.dedup_groups = result.groups_found
        report.dedup_merged = result.space_freed

    def _phase_archive(
        self,
        store: StorageBackend,
        items: list[MemoryItem],
        report: CompactionReport,
    ) -> None:
        """Phase 2: Tag old low-relevance memories as archived."""
        candidates = self.find_archive_candidates(items)
        budget_used = report.archived + report.dedup_merged + report.stale_merged
        remaining_budget = self._config.max_compact_per_run - budget_used
        candidates = candidates[:max(0, remaining_budget)]

        if not candidates:
            return

        for item in candidates:
            # Skip already-archived
            if "archived" in item.tags:
                continue

            if self._config.dry_run:
                report.archived += 1
                report.archive_details.append({
                    "id": item.id,
                    "content": item.content[:100],
                    "age_days": round((time.time() - item.created_at) / 86400, 1),
                    "original_importance": item.importance,
                })
                continue

            # Create a modified copy to avoid in-place mutation issues
            archived_tags = list(item.tags) + ["archived"]
            archived_meta = dict(item.metadata)
            archived_meta["archived_at"] = time.time()
            archived_meta["original_importance"] = item.importance

            archived_item = MemoryItem(
                id=item.id,
                content=item.content,
                tags=archived_tags,
                importance=0.0,
                created_at=item.created_at,
                accessed_at=item.accessed_at,
                access_count=item.access_count,
                metadata=archived_meta,
            )
            store.upsert(archived_item)

            report.archived += 1
            report.archive_details.append({
                "id": item.id,
                "content": item.content[:100],
                "age_days": round((time.time() - item.created_at) / 86400, 1),
                "original_importance": archived_meta["original_importance"],
            })

    def _phase_stale_merge(
        self,
        store: StorageBackend,
        items: list[MemoryItem],
        report: CompactionReport,
    ) -> None:
        """Phase 3: Merge groups of stale, semantically related memories."""
        groups = self.find_stale_groups(items)
        budget_used = report.archived + report.dedup_merged + report.stale_merged
        remaining_budget = self._config.max_compact_per_run - budget_used

        for group in groups:
            if budget_used >= self._config.max_compact_per_run:
                break

            # Merge all memories in the group into one summary
            merged = self._merge_stale_group(group.memories)

            if not self._config.dry_run:
                store.upsert(merged)
                for m in group.memories:
                    if m.id != merged.id:
                        store.delete(m.id)

            report.stale_groups += 1
            report.stale_merged += len(group.memories) - 1  # -1 for the kept item
            report.total_added += 1
            budget_used += len(group.memories) - 1

    def _phase_cluster_compact(
        self,
        store: StorageBackend,
        items: list[MemoryItem],
        report: CompactionReport,
    ) -> None:
        """Phase 4: Compress large tag-based clusters."""
        # Group by tag to find large clusters
        by_tag: dict[str, list[MemoryItem]] = {}
        for item in items:
            if "archived" in item.tags:
                continue
            for tag in item.tags:
                by_tag.setdefault(tag, []).append(item)

        budget_used = report.archived + report.dedup_merged + report.stale_merged

        for tag, tag_items in by_tag.items():
            if len(tag_items) < self._config.cluster_min_size * 2:
                continue
            if budget_used >= self._config.max_compact_per_run:
                break

            # Sort by relevance (keep best, compress rest)
            tag_items.sort(
                key=lambda m: self._decay.adjusted_score(0.5, m),
                reverse=True,
            )

            # Keep top N, compress the rest into a summary
            keep_count = max(self._config.cluster_min_size, len(tag_items) // 3)
            to_compress = tag_items[keep_count:]

            if len(to_compress) < self._config.cluster_min_size:
                continue

            summary = self._create_cluster_summary(tag, to_compress)

            if not self._config.dry_run:
                store.upsert(summary)
                for m in to_compress:
                    if m.id != summary.id:
                        store.delete(m.id)

            report.clusters_compacted += 1
            report.total_removed += len(to_compress)
            report.total_added += 1
            budget_used += len(to_compress)
            report.cluster_details.append({
                "tag": tag,
                "cluster_size": len(tag_items),
                "kept": keep_count,
                "compressed": len(to_compress),
                "summary_preview": summary.content[:150],
            })

    # ── Helpers ────────────────────────────────────────────

    def _merge_stale_group(self, memories: list[MemoryItem]) -> MemoryItem:
        """Merge a group of stale memories into one summary memory."""
        # Sort by importance (descending) — keep best as base
        memories.sort(key=lambda m: m.importance, reverse=True)
        base = memories[0]

        # Collect unique content parts
        all_content = [base.content]
        base_tokens = self._tokenize(base.content)
        for m in memories[1:]:
            m_tokens = self._tokenize(m.content)
            new_ratio = len(m_tokens - base_tokens) / max(len(m_tokens), 1)
            if new_ratio > 0.3:
                all_content.append(m.content)

        # Merge tags
        all_tags = set()
        for m in memories:
            all_tags.update(m.tags)
        all_tags.discard("archived")

        # Merge metadata
        merged_meta: dict = {
            "compacted": True,
            "compacted_from": len(memories),
            "compacted_at": time.time(),
        }
        for m in memories:
            if m.metadata:
                for k, v in m.metadata.items():
                    if k not in merged_meta:
                        merged_meta[k] = v

        # Build merged content
        if len(all_content) == 1:
            content = all_content[0]
        else:
            content = "\n".join(f"• {c}" for c in all_content)

        # Create new item (new ID since content may differ)
        new_id = generate_id(content)
        max_importance = max(m.importance for m in memories)

        return MemoryItem(
            id=new_id,
            content=content,
            tags=sorted(all_tags),
            importance=min(max_importance + 0.05, 1.0),  # Slight boost
            created_at=min(m.created_at for m in memories),
            accessed_at=max(m.accessed_at for m in memories),
            access_count=sum(m.access_count for m in memories),
            metadata=merged_meta,
        )

    def _create_cluster_summary(
        self, tag: str, items: list[MemoryItem]
    ) -> MemoryItem:
        """Create a summary memory for a cluster of related items."""
        # Extract key phrases from each item
        key_points = []
        for item in items:
            content = item.content.strip()
            if len(content) > 200:
                # Truncate to first sentence or 200 chars
                first_sentence = re.split(r'[.!?]', content)[0]
                key_points.append(first_sentence.strip()[:200])
            else:
                key_points.append(content)

        summary_lines = [f"[{tag}] Summary ({len(items)} memories):"]
        for i, point in enumerate(key_points[:20], 1):
            summary_lines.append(f"{i}. {point}")
        if len(key_points) > 20:
            summary_lines.append(f"... and {len(key_points) - 20} more")

        content = "\n".join(summary_lines)

        return MemoryItem(
            id=generate_id(content),
            content=content,
            tags=[tag, "compacted"],
            importance=max(0.3, max(i.importance for i in items) * 0.7),
            created_at=min(i.created_at for i in items),
            accessed_at=time.time(),
            access_count=sum(i.access_count for i in items),
            metadata={
                "compacted": True,
                "compacted_from": len(items),
                "compacted_at": time.time(),
                "compaction_type": "cluster_summary",
            },
        )

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Tokenize text into meaningful word set."""
        words = re.findall(r"\w+", text.lower())
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "and", "but", "or", "not", "it", "its", "i",
            "me", "my", "we", "our", "you", "your", "he", "him", "his",
            "she", "her", "they", "them", "their", "this", "that",
        }
        return {w for w in words if len(w) > 2 and w not in stopwords}

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    @staticmethod
    def _dominant_tag(items: list[MemoryItem]) -> str:
        """Find the most common tag among items."""
        counts: dict[str, int] = {}
        for item in items:
            for tag in item.tags:
                if tag != "archived":
                    counts[tag] = counts.get(tag, 0) + 1
        if not counts:
            return ""
        return max(counts, key=counts.get)
