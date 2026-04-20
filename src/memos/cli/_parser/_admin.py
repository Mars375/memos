"""Admin and maintenance commands: compact, prune, prune-expired, consolidate, cache-stats, benchmark, benchmark-quality, feedback/*, dedup-check, dedup-scan, decay, reinforce, compress, sync-check, sync-apply."""

from __future__ import annotations

from ._common import BACKEND_CHOICES_WITH_JSON, _add_backend_arg


def build(sub) -> None:
    # prune
    prune = sub.add_parser("prune", help="Remove decayed memories")
    prune.add_argument("--threshold", type=float, default=0.1)
    prune.add_argument("--max-age", type=float, default=90.0)
    prune.add_argument("--dry-run", action="store_true")
    prune.add_argument("--verbose", "-v", action="store_true")
    _add_backend_arg(prune)

    # prune-expired
    pe = sub.add_parser("prune-expired", help="Remove expired memories (past their TTL)")
    pe.add_argument("--dry-run", action="store_true", help="Preview only")
    _add_backend_arg(pe)

    # consolidate
    cons = sub.add_parser("consolidate", help="Find and merge duplicate memories")
    cons.add_argument("--threshold", type=float, default=0.75, help="Similarity threshold (0-1)")
    cons.add_argument("--merge", action="store_true", help="Merge content from duplicates")
    cons.add_argument("--dry-run", action="store_true", help="Report only, don't modify")
    cons.add_argument("--verbose", "-v", action="store_true")
    _add_backend_arg(cons)

    # compact
    compact_p = sub.add_parser("compact", help="Run memory compaction (dedup + archive + merge)")
    compact_p.add_argument("--dry-run", action="store_true", help="Preview only, don't modify")
    compact_p.add_argument("--archive-age", type=float, default=90.0, help="Min age (days) for archival")
    compact_p.add_argument("--importance-floor", type=float, default=0.3, help="Never archive above this importance")
    compact_p.add_argument("--stale-threshold", type=float, default=0.25, help="Decay score threshold for stale")
    compact_p.add_argument("--max-per-run", type=int, default=200, help="Max modifications per run")
    compact_p.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(compact_p)

    # benchmark
    bench = sub.add_parser("benchmark", help="Run performance benchmarks")
    bench.add_argument("--size", type=int, default=1000, help="Number of memories to insert (default: 1000)")
    bench.add_argument("--recall-queries", type=int, default=100, help="Number of recall queries (default: 100)")
    bench.add_argument("--search-queries", type=int, default=100, help="Number of search queries (default: 100)")
    bench.add_argument("--warmup", type=int, default=50, help="Warmup operations (default: 50)")
    _add_backend_arg(bench)
    bench.add_argument("--json", action="store_true", help="JSON output")

    # benchmark-quality
    bq = sub.add_parser("benchmark-quality", help="Run recall quality benchmarks (accuracy, MRR, NDCG)")
    bq.add_argument("--noise", type=int, default=50, help="Noise memories to add (default: 50)")
    bq.add_argument("--top", type=int, default=5, help="Top-K results per query (default: 5)")
    bq.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    bq.add_argument("--no-decay", action="store_true", help="Skip decay behavior test")
    bq.add_argument("--scalability", action="store_true", help="Run scalability test")
    _add_backend_arg(bq)
    bq.add_argument("--json", action="store_true", help="JSON output")

    # cache-stats
    cache_p = sub.add_parser("cache-stats", help="Show embedding cache statistics")
    cache_p.add_argument("--json", action="store_true", help="JSON output")
    cache_p.add_argument("--clear", action="store_true", help="Clear the cache")
    _add_backend_arg(cache_p)

    # feedback
    fb = sub.add_parser("feedback", help="Record relevance feedback for a memory")
    fb.add_argument("item_id", help="Memory item ID")
    fb.add_argument("rating", choices=["relevant", "not-relevant"], help="Feedback rating")
    fb.add_argument("--query", "-q", help="The query that triggered the recall")
    fb.add_argument("--score", type=float, default=0.0, help="Recall score at feedback time")
    fb.add_argument("--agent", help="Agent ID providing feedback")
    fb.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(fb)

    # feedback-list
    fb_list = sub.add_parser("feedback-list", help="List feedback entries")
    fb_list.add_argument("--item-id", dest="item_id", help="Filter by memory item ID")
    fb_list.add_argument("--limit", type=int, default=50, help="Max entries to show")
    fb_list.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(fb_list)

    # feedback-stats
    fb_stats = sub.add_parser("feedback-stats", help="Show feedback statistics")
    fb_stats.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(fb_stats)

    # decay
    decay_p = sub.add_parser("decay", help="Apply importance decay to memories")
    decay_p.add_argument("--apply", action="store_true", help="Apply decay (default is dry-run)")
    decay_p.add_argument("--min-age-days", type=float, default=None, help="Min age in days to be eligible")
    decay_p.add_argument("--floor", type=float, default=None, help="Minimum importance after decay")
    _add_backend_arg(decay_p, choices=BACKEND_CHOICES_WITH_JSON)

    # reinforce
    reinforce_p = sub.add_parser("reinforce", help="Boost a memory's importance")
    reinforce_p.add_argument("memory_id", help="Memory ID to reinforce")
    reinforce_p.add_argument("--strength", type=float, default=None, help="Boost amount (default: 0.05)")
    _add_backend_arg(reinforce_p, choices=BACKEND_CHOICES_WITH_JSON)

    # compress
    compress_p = sub.add_parser("compress", help="Compress decayed memories into aggregate summaries")
    compress_p.add_argument("--threshold", type=float, default=0.1, help="Importance threshold (default: 0.1)")
    compress_p.add_argument("--dry-run", action="store_true", help="Preview without modifying memories")
    compress_p.add_argument("--verbose", "-v", action="store_true")
    _add_backend_arg(compress_p, choices=BACKEND_CHOICES_WITH_JSON)

    # sync-check (P12 — Conflict Resolution)
    sync_check = sub.add_parser("sync-check", help="Check for conflicts with a remote memory export")
    sync_check.add_argument("remote_file", help="Path to remote JSON envelope file")
    sync_check.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(sync_check)

    # sync-apply (P12 — Conflict Resolution)
    sync_apply = sub.add_parser("sync-apply", help="Apply remote memories with conflict resolution")
    sync_apply.add_argument("remote_file", help="Path to remote JSON envelope file")
    sync_apply.add_argument(
        "--strategy",
        choices=["local_wins", "remote_wins", "merge", "manual"],
        default="merge",
        help="Conflict resolution strategy (default: merge)",
    )
    sync_apply.add_argument("--dry-run", action="store_true", help="Show what would be applied without writing")
    sync_apply.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(sync_apply)
