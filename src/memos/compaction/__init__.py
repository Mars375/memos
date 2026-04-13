"""Compaction engine — auto-merge stale memories and reclaim space.

Unlike consolidation (which deduplicates exact/near-duplicate memories),
compaction handles the broader lifecycle:
- Merge clusters of semantically related but non-identical memories
- Archive very old, low-relevance memories
- Compress frequently-accessed memory groups into summaries
- Produce actionable compaction reports

Compaction is designed to run periodically (e.g., daily cron) and keep
the memory store healthy as it grows.
"""

from .engine import CompactionConfig, CompactionEngine, CompactionReport

__all__ = ["CompactionEngine", "CompactionConfig", "CompactionReport"]
