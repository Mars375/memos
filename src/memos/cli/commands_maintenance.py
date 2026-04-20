"""MemOS CLI — maintenance/housekeeping commands."""

from __future__ import annotations

import argparse
import json
import sys
import sys as _sys


def _get_memos(ns):
    return _sys.modules["memos.cli.commands_memory"]._get_memos(ns)


def cmd_prune(ns: argparse.Namespace) -> None:
    """Prune decayed memories."""
    memos = _get_memos(ns)
    candidates = memos.prune(
        threshold=ns.threshold,
        max_age_days=ns.max_age,
        dry_run=ns.dry_run,
    )
    label = "would be pruned" if ns.dry_run else "pruned"
    print(f"✓ {len(candidates)} memories {label}")
    if ns.verbose:
        for c in candidates[:10]:
            print(f"  - [{c.id[:8]}] {c.content[:80]}")


def cmd_prune_expired(ns: argparse.Namespace) -> None:
    """Remove expired memories."""
    memos = _get_memos(ns)
    expired = memos.prune_expired(dry_run=ns.dry_run)
    if not expired:
        print("No expired memories.")
        return
    label = " (dry-run)" if ns.dry_run else ""
    print(f"{'Would remove' if ns.dry_run else 'Removed'} {len(expired)} expired memories{label}:")
    for item in expired[:10]:
        print(f"  [{item.id[:8]}] {item.content[:80]}")
    if len(expired) > 10:
        print(f"  ... and {len(expired) - 10} more")


def cmd_consolidate(ns: argparse.Namespace) -> None:
    """Find and merge semantically similar memories."""
    memos = _get_memos(ns)
    result = memos.consolidate(
        similarity_threshold=ns.threshold,
        merge_content=ns.merge,
        dry_run=ns.dry_run,
    )
    label = "would be" if ns.dry_run else ""
    print(f"Groups found: {result.groups_found}")
    print(f"Memories {label} merged: {result.memories_merged}")
    if not ns.dry_run:
        print(f"Space freed: {result.space_freed} memories removed")
    if ns.verbose:
        for g in result.details[:10]:
            print(f"  [{g.reason}] sim={g.similarity:.2f} keep=[{g.keep.id[:8]}] {g.keep.content[:60]}")
            for d in g.duplicates:
                print(f"    dup=[{d.id[:8]}] {d.content[:60]}")


def cmd_compact(ns: argparse.Namespace) -> None:
    """Run memory compaction."""
    memos = _get_memos(ns)
    report = memos.compact(
        archive_age_days=ns.archive_age,
        archive_importance_floor=ns.importance_floor,
        stale_score_threshold=ns.stale_threshold,
        max_compact_per_run=ns.max_per_run,
        dry_run=ns.dry_run,
    )
    if getattr(ns, "json", False):
        print(json.dumps(report, indent=2))
        return
    prefix = "[DRY RUN] " if ns.dry_run else ""
    print(f"{prefix}Compaction complete:")
    print(f"  Dedup groups:    {report['dedup_groups']} ({report['dedup_merged']} merged)")
    print(f"  Archived:        {report['archived']}")
    print(f"  Stale merged:    {report['stale_merged']} in {report['stale_groups']} groups")
    print(f"  Clusters:        {report['clusters_compacted']} compacted")
    print(f"  Net delta:       {report['net_delta']:+d} memories")
    print(f"  Duration:        {report['duration_seconds']:.3f}s")


def cmd_cache_stats(ns: argparse.Namespace) -> None:
    """Show embedding cache statistics."""
    memos = _get_memos(ns)
    if getattr(ns, "clear", False):
        cleared = memos.cache_clear()
        if cleared < 0:
            print("Cache is not enabled")
        else:
            print(f"Cleared {cleared} entries")
        return
    stats = memos.cache_stats()
    if stats is None:
        print("Cache is not enabled. Use cache_enabled=True to enable.")
        return
    if getattr(ns, "json", False):
        print(json.dumps(stats, indent=2))
        return
    print(f"  Cache entries:   {stats['size']}/{stats['max_size']}")
    print(f"  Hits:            {stats['hits']}")
    print(f"  Misses:          {stats['misses']}")
    print(f"  Hit rate:        {stats['hit_rate']:.1%}")
    print(f"  Evictions:       {stats['evictions']}")


def cmd_benchmark(ns: argparse.Namespace) -> None:
    """Run performance benchmarks."""
    from ..benchmark import run_benchmark

    memos = _get_memos(ns)
    report = run_benchmark(
        memos=memos,
        memories=ns.size,
        recall_queries=ns.recall_queries,
        search_queries=ns.search_queries,
        warmup=ns.warmup,
    )
    if getattr(ns, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.to_text())


def cmd_benchmark_quality(ns: argparse.Namespace) -> None:
    """Run recall quality benchmarks."""
    from ..benchmark_quality import run_quality_benchmark

    report = run_quality_benchmark(
        memories_per_category=10,
        extra_noise=ns.noise,
        top_k=ns.top,
        seed=ns.seed,
        run_decay=not ns.no_decay,
        run_scalability=ns.scalability,
        scalability_sizes=[50, 200, 500, 1000] if ns.scalability else None,
        backend=ns.backend,
    )
    if getattr(ns, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.to_text())


def cmd_decay(ns: argparse.Namespace) -> None:
    """Apply importance decay to memories."""
    m = _get_memos(ns)
    items = m._store.list_all(namespace=m._namespace)
    report = m._decay.run_decay(
        items,
        min_age_days=ns.min_age_days,
        floor=ns.floor,
        dry_run=not ns.apply,
    )
    # Persist changes if not dry-run
    if ns.apply:
        for item in items:
            m._store.upsert(item, namespace=m._namespace)
    mode = "APPLIED" if ns.apply else "DRY RUN"
    print(f"Decay report ({mode}):")
    print(f"  Total memories:    {report.total}")
    print(f"  Decayed:           {report.decayed}")
    print(f"  Avg importance:    {report.avg_importance_before:.3f} → {report.avg_importance_after:.3f}")
    if report.details:
        print("")
        print("Top decayed:")
        for d in report.details[:10]:
            print(
                f"  [{d['id'][:8]}] {d['importance_before']:.3f} → {d['importance_after']:.3f} (age {d['age_days']}d)"
            )


def cmd_reinforce(ns: argparse.Namespace) -> None:
    """Boost a memory's importance."""
    m = _get_memos(ns)
    item = m._store.get(ns.memory_id, namespace=m._namespace)
    if item is None:
        print(f"Memory not found: {ns.memory_id}", file=sys.stderr)
        sys.exit(1)
    old_imp = item.importance
    new_imp = m._decay.reinforce(item, strength=ns.strength)
    m._store.upsert(item, namespace=m._namespace)
    print(f"✓ Reinforced [{item.id[:8]}] importance: {old_imp:.3f} → {new_imp:.3f}")


def cmd_compress(ns: argparse.Namespace) -> None:
    """Compress very low-importance memories into aggregate summaries."""
    m = _get_memos(ns)
    result = m.compress(threshold=ns.threshold, dry_run=ns.dry_run)
    prefix = "DRY RUN " if ns.dry_run else ""
    print(f"{prefix}Compression complete:")
    print(f"  Compressed memories: {result.compressed_count}")
    print(f"  Summary memories:    {result.summary_count}")
    print(f"  Freed bytes:         {result.freed_bytes}")
    if getattr(ns, "verbose", False) and result.details:
        for detail in result.details[:10]:
            tags = ", ".join(detail["tags"])
            print(f"  - [{tags}] {detail['source_count']} → {detail['summary_id'][:8]} ({detail['freed_bytes']} bytes)")
