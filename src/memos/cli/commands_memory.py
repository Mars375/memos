"""MemOS CLI — memory commands."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..models import parse_ttl
from ._common import _fmt_ts, _get_kg, _get_kg_bridge, _get_memos


def cmd_init(ns: argparse.Namespace) -> None:
    """Initialize a MemOS data directory."""
    path = Path(ns.directory)
    path.mkdir(parents=True, exist_ok=True)
    cfg = path / "memos.json"
    if cfg.exists() and not ns.force:
        print(f"Already initialized: {cfg}")
        return
    config = {
        "backend": getattr(ns, "backend", "memory"),
        "version": __version__,
    }
    cfg.write_text(json.dumps(config, indent=2))
    print(f"✓ Initialized MemOS in {path}/")


def cmd_learn(ns: argparse.Namespace) -> None:
    """Learn (store) a new memory."""
    memos = _get_memos(ns)
    content = ns.content
    if ns.file:
        content = Path(ns.file).read_text().strip()
    elif getattr(ns, "stdin", False):
        content = sys.stdin.read().strip()
    if not content:
        print("Error: no content provided (use positional arg, --file, or --stdin)", file=sys.stderr)
        sys.exit(1)
    tags = ns.tags.split(",") if ns.tags else []
    ttl = None
    if hasattr(ns, "ttl") and ns.ttl:
        ttl = parse_ttl(ns.ttl)
    item = memos.learn(content, tags=tags, importance=ns.importance, ttl=ttl)
    ttl_str = f", ttl={ns.ttl}" if ns.ttl else ""
    print(f"✓ Learned [{item.id[:8]}...] ({len(item.content)} chars, tags={item.tags}{ttl_str})")


def cmd_batch_learn(ns: argparse.Namespace) -> None:
    """Batch learn — store multiple memories from a JSON file."""
    memos = _get_memos(ns)
    src = ns.input
    text = Path(src).read_text(encoding="utf-8") if src != "-" else sys.stdin.read()
    data = json.loads(text)
    items = data if isinstance(data, list) else data.get("items", [])
    if not items:
        print("No items found in input", file=sys.stderr)
        sys.exit(1)
    result = memos.batch_learn(
        items=items,
        continue_on_error=not ns.strict,
    )
    label = " (dry-run)" if ns.dry_run else ""
    print(
        f"{label}Batch learn: {result['learned']} learned, {result['skipped']} skipped, {len(result['errors'])} errors"
    )
    if ns.verbose and result["items"]:
        for item in result["items"][:10]:
            print(f"  ✓ [{item['id'][:8]}] {item['content'][:80]}")
        if len(result["items"]) > 10:
            print(f"  ... and {len(result['items']) - 10} more")
    if result["errors"]:
        for err in result["errors"][:5]:
            print(f"  ⚠ {err.get('reason', err)}", file=sys.stderr)


def cmd_recall(ns: argparse.Namespace) -> None:
    """Recall memories matching a query."""
    from datetime import datetime as _dt

    def _split_csv(value: str | None) -> list[str]:
        if not value:
            return []
        return [t.strip() for t in value.split(",") if t.strip()]

    memos = _get_memos(ns)
    filter_tags = _split_csv(getattr(ns, "tags", None))
    require_tags = _split_csv(getattr(ns, "require_tags", None))
    exclude_tags = _split_csv(getattr(ns, "exclude_tags", None))
    if (getattr(ns, "tag_mode", "any") or "any").lower() == "all" and filter_tags:
        require_tags.extend(filter_tags)
        filter_tags = []

    filter_after = None
    filter_before = None
    if ns.after:
        try:
            filter_after = _dt.fromisoformat(ns.after).timestamp()
        except ValueError:
            print(f"Error: Invalid --after date format: {ns.after!r}. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM")
            return
    if ns.before:
        try:
            filter_before = _dt.fromisoformat(ns.before).timestamp()
        except ValueError:
            print(f"Error: Invalid --before date format: {ns.before!r}. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM")
            return
    fmt = getattr(ns, "format", "text") or "text"
    if getattr(ns, "enriched", False):
        bridge = _get_kg_bridge(ns, memos=memos)
        try:
            payload = bridge.recall_enriched(
                ns.query,
                top=ns.top,
                filter_tags=filter_tags or require_tags,
                min_score=ns.min_score,
                filter_after=filter_after,
                filter_before=filter_before,
            )
        finally:
            bridge.close()
        if fmt == "json":
            print(json.dumps(payload, indent=2))
            return
        memories = payload["memories"]
        facts = payload["facts"]
        if not memories and not facts:
            print("No memories or KG facts found.")
            return
        if memories:
            print("Memories:")
            for r in memories:
                tags_str = f" [{', '.join(r['tags'])}]" if r["tags"] else ""
                print(f"  {r['score']:.3f} {r['content'][:120]}{tags_str}")
            print(f"\n{len(memories)} memory result(s)")
        if facts:
            print("\nKG facts:")
            for f in facts:
                print(f"  [{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']}")
            print(f"\n{len(facts)} fact(s)")
        return
    retrieval_mode = getattr(ns, "retrieval_mode", "semantic") or "semantic"
    results = memos.recall(
        ns.query,
        top=ns.top,
        min_score=ns.min_score,
        filter_tags=filter_tags,
        filter_after=filter_after,
        filter_before=filter_before,
        retrieval_mode=retrieval_mode,
        tag_filter={"require": require_tags, "exclude": exclude_tags} if (require_tags or exclude_tags) else None,
        min_importance=getattr(ns, "min_importance", None),
        max_importance=getattr(ns, "max_importance", None),
    )
    if not results:
        if fmt == "json":
            print(json.dumps({"results": [], "total": 0}))
        else:
            print("No memories found.")
        return
    if fmt == "json":
        json_results = []
        for r in results:
            entry = {
                "id": r.item.id,
                "content": r.item.content,
                "score": round(r.score, 4),
                "tags": r.item.tags,
                "match_reason": r.match_reason,
                "importance": r.item.importance,
                "created_at": r.item.created_at,
            }
            if getattr(ns, "explain", False) and r.score_breakdown:
                entry["score_breakdown"] = r.score_breakdown.to_dict()
            json_results.append(entry)
        print(json.dumps({"results": json_results, "total": len(results)}, indent=2))
        return
    for r in results:
        tags_str = f" [{', '.join(r.item.tags)}]" if r.item.tags else ""
        print(f"  {r.score:.3f} {r.item.content[:120]}{tags_str}")
        if getattr(ns, "explain", False) and r.score_breakdown:
            bd = r.score_breakdown
            print(
                f"    breakdown: semantic={bd.semantic:.3f} keyword={bd.keyword:.3f} importance={bd.importance:.3f} recency={bd.recency:.3f} tag_bonus={bd.tag_bonus:.3f} backend={bd.backend}"
            )
    print(f"\n{len(results)} result(s)")


def cmd_search(ns: argparse.Namespace) -> None:
    """Keyword-only search across all memories (no embeddings required)."""
    memos = _get_memos(ns)
    items = memos.search(q=ns.query, limit=ns.limit)
    fmt = getattr(ns, "format", "text") or "text"
    if not items:
        if fmt == "json":
            print(json.dumps({"results": [], "total": 0}))
        else:
            print("No memories found.")
        return
    if fmt == "json":
        print(
            json.dumps(
                {
                    "results": [
                        {
                            "id": item.id,
                            "content": item.content[:200],
                            "tags": item.tags,
                            "importance": item.importance,
                        }
                        for item in items
                    ],
                    "total": len(items),
                },
                indent=2,
            )
        )
        return
    for item in items:
        tags_str = f" [{', '.join(item.tags)}]" if item.tags else ""
        print(f"  [{item.id[:8]}] {item.content[:120]}{tags_str}")
    print(f"\n{len(items)} result(s)")


def cmd_stats(ns: argparse.Namespace) -> None:
    """Show memory store statistics."""
    memos = _get_memos(ns)
    s = memos.stats()
    if ns.json:
        print(
            json.dumps(
                {
                    "total_memories": s.total_memories,
                    "total_tags": s.total_tags,
                    "avg_relevance": round(s.avg_relevance, 3),
                    "avg_importance": round(s.avg_importance, 3),
                    "decay_candidates": s.decay_candidates,
                    "top_tags": s.top_tags,
                    "token_stats": {
                        "total_chars": s.total_chars,
                        "total_tokens": s.total_tokens,
                        "prunable_tokens": s.prunable_tokens,
                        "expired_tokens": s.expired_tokens,
                    },
                },
                indent=2,
            )
        )
        return
    print(f"  Total memories:  {s.total_memories}")
    print(f"  Total tags:      {s.total_tags}")
    print(f"  Avg relevance:   {s.avg_relevance:.3f}")
    print(f"  Avg importance:  {s.avg_importance:.3f}")
    print(f"  Decay candidates:{s.decay_candidates}")
    if s.top_tags:
        print(f"  Top tags:        {', '.join(s.top_tags[:5])}")
    # Token compression reporting (P9)
    if s.total_tokens > 0:
        print(f"\n  Token estimate:  ~{s.total_tokens:,} tokens ({s.total_chars:,} chars)")
        if s.prunable_tokens > 0:
            pct = round(s.prunable_tokens / s.total_tokens * 100)
            print(f"  Prunable tokens: ~{s.prunable_tokens:,} ({pct}% of total, run: memos decay)")
        if s.expired_tokens > 0:
            print(f"  Expired tokens:  ~{s.expired_tokens:,} (run: memos prune --expired)")


def cmd_analytics(ns: argparse.Namespace) -> None:
    """Show recall analytics."""
    memos = _get_memos(ns)
    action = getattr(ns, "analytics_action", None)
    if not action:
        print("Error: analytics subcommand required", file=sys.stderr)
        sys.exit(1)

    if action == "top":
        results = memos.analytics.top_recalled(n=ns.n)
        if ns.json:
            print(json.dumps({"results": results}, indent=2))
            return
        for row in results:
            print(f"  {row['count']:>3} {row['memory_id'][:8]}")
        print(f"\n{len(results)} result(s)")
        return

    if action == "patterns":
        results = memos.analytics.query_patterns(n=ns.n)
        if ns.json:
            print(json.dumps({"results": results}, indent=2))
            return
        for row in results:
            print(f"  {row['count']:>3} {row['query']}")
        print(f"\n{len(results)} result(s)")
        return

    if action == "latency":
        stats = memos.analytics.latency_stats()
        if ns.json:
            print(json.dumps(stats, indent=2))
            return
        print(f"  Count:   {stats['count']}")
        print(f"  Avg:     {stats['avg']:.2f} ms")
        print(f"  p50:     {stats['p50']:.2f} ms")
        print(f"  p95:     {stats['p95']:.2f} ms")
        print(f"  p99:     {stats['p99']:.2f} ms")
        return

    if action == "success-rate":
        stats = memos.analytics.recall_success_rate_stats(days=ns.days)
        if ns.json:
            print(json.dumps(stats, indent=2))
            return
        print(f"  Success rate: {stats['success_rate']:.1f}%")
        print(f"  Total recalls: {stats['total_recalls']}")
        print(f"  Successful:    {stats['successful_recalls']}")
        print(f"  Failed:        {stats['failed_recalls']}")
        return

    if action == "daily":
        results = memos.analytics.daily_activity(days=ns.days)
        if ns.json:
            print(json.dumps({"results": results}, indent=2))
            return
        for row in results:
            print(f"  {row['date']}  {row['count']}")
        print(f"\n{len(results)} day(s)")
        return

    if action == "zero":
        results = memos.analytics.zero_result_queries(n=ns.n)
        if ns.json:
            print(json.dumps({"results": results}, indent=2))
            return
        for row in results:
            print(f"  {row['count']:>3} {row['query']}")
        print(f"\n{len(results)} result(s)")
        return

    if action == "summary":
        summary = memos.analytics.summary(days=ns.days)
        if ns.json:
            print(json.dumps(summary, indent=2))
            return
        success = summary["success"]
        print(
            f"  Success rate: {success['success_rate']:.1f}% ({success['successful_recalls']}/{success['total_recalls']})"
        )
        latency = summary["latency"]
        print(f"  Latency p95:  {latency['p95']:.2f} ms")
        print(f"  Top queries:  {len(summary['top_queries'])}")
        print(f"  Zero-result:   {len(summary['zero_result_queries'])}")
        print(f"  Daily points:  {len(summary['daily_activity'])}")
        return

    print(f"Error: unknown analytics action: {action}", file=sys.stderr)
    sys.exit(1)


def cmd_forget(ns: argparse.Namespace) -> None:
    """Forget (delete) a memory by ID/content or by tag."""
    memos = _get_memos(ns)
    if ns.tag:
        removed = memos.forget_tag(ns.tag)
        print(f"✓ Forgotten {removed} memory(s) with tag '{ns.tag}'" if removed else "✗ Not found")
        return
    if not ns.target:
        print("Error: target or --tag required", file=sys.stderr)
        sys.exit(1)
    ok = memos.forget(ns.target)
    print("✓ Forgotten" if ok else "✗ Not found")


def cmd_get(ns: argparse.Namespace) -> None:
    """Retrieve and display a single memory by ID."""
    memos = _get_memos(ns)
    item = memos.get(ns.item_id)
    if item is None:
        print(f"✗ Memory not found: {ns.item_id}", file=sys.stderr)
        sys.exit(1)
    if getattr(ns, "json", False):
        out = {
            "id": item.id,
            "content": item.content,
            "tags": item.tags,
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
            "relevance_score": item.relevance_score,
        }
        if item.ttl is not None:
            out["ttl"] = item.ttl
            out["expires_at"] = item.expires_at
            out["is_expired"] = item.is_expired
        public_meta = {k: v for k, v in item.metadata.items() if not k.startswith("_")}
        if public_meta:
            out["metadata"] = public_meta
        print(json.dumps(out, indent=2))
        return
    # Human-readable output
    age_days = (time.time() - item.created_at) / 86400
    print(f"  ID:           {item.id}")
    print(f"  Content:      {item.content}")
    print(f"  Tags:         {', '.join(item.tags) if item.tags else '(none)'}")
    print(f"  Importance:   {item.importance:.2f}")
    print(f"  Relevance:    {item.relevance_score:.3f}")
    print(f"  Created:      {_fmt_ts(item.created_at)}  ({age_days:.1f} days ago)")
    print(f"  Last access:  {_fmt_ts(item.accessed_at)}")
    print(f"  Access count: {item.access_count}")
    if item.ttl is not None:
        print(f"  TTL:          {item.ttl:.0f}s")
        if item.expires_at:
            print(f"  Expires at:   {_fmt_ts(item.expires_at)}")
        print(f"  Expired:      {'Yes' if item.is_expired else 'No'}")
    public_meta = {k: v for k, v in item.metadata.items() if not k.startswith("_")}
    if public_meta:
        print(f"  Metadata:     {json.dumps(public_meta)}")


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


def cmd_watch(ns: argparse.Namespace) -> None:
    """Watch live memory events via the SSE stream."""
    import httpx

    server = getattr(ns, "server", None) or os.environ.get("MEMOS_URL", "http://127.0.0.1:8000")
    params: dict[str, str] = {}
    if ns.event_types:
        params["event_types"] = ns.event_types
    if ns.tags:
        params["tags"] = ns.tags
    if ns.namespace:
        params["namespace"] = ns.namespace

    url = f"{server.rstrip('/')}/api/v1/events/stream"

    def _emit(event_name: str, payload: str) -> None:
        if ns.json:
            print(payload)
            return
        try:
            data = json.loads(payload)
        except Exception:
            print(f"{event_name}: {payload}")
            return
        if isinstance(data, dict):
            content = data.get("data", {})
            tags = content.get("tags") or []
            tags_txt = f" [{', '.join(tags)}]" if tags else ""
            preview = content.get("content") or content.get("query") or content.get("message") or ""
            ns_txt = f" @{data.get('namespace')}" if data.get("namespace") else ""
            print(f"{event_name}{ns_txt}{tags_txt} {preview}".strip())
        else:
            print(f"{event_name}: {payload}")

    seen = 0
    with httpx.stream("GET", url, params=params, timeout=None) as resp:
        resp.raise_for_status()
        event_name = "message"
        data_lines: list[str] = []
        for line in resp.iter_lines():
            if line is None:
                continue
            line = line.decode() if isinstance(line, bytes) else line
            if line.startswith("event: "):
                event_name = line.split(": ", 1)[1]
            elif line.startswith("data: "):
                data_lines.append(line.split(": ", 1)[1])
            elif line == "":
                if data_lines:
                    _emit(event_name, "\n".join(data_lines))
                    seen += 1
                    data_lines = []
                    event_name = "message"
                    if ns.max_events and seen >= ns.max_events:
                        break


def cmd_subscribe(ns: argparse.Namespace) -> None:
    """Alias for watch, more explicit for subscription-style usage."""
    cmd_watch(ns)


def cmd_feedback(ns: argparse.Namespace) -> None:
    """Record relevance feedback for a recalled memory."""
    memos = _get_memos(ns)
    try:
        entry = memos.record_feedback(
            item_id=ns.item_id,
            feedback=ns.rating,
            query=getattr(ns, "query", "") or "",
            score_at_recall=getattr(ns, "score", 0.0),
            agent_id=getattr(ns, "agent", "") or "",
        )
        if getattr(ns, "json", False):
            print(json.dumps(entry.to_dict(), indent=2))
        else:
            print(f"✓ Feedback recorded: {ns.item_id[:12]}... → {ns.rating}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_feedback_list(ns: argparse.Namespace) -> None:
    """List feedback entries."""
    memos = _get_memos(ns)
    entries = memos.get_feedback(item_id=getattr(ns, "item_id", None), limit=ns.limit)
    if getattr(ns, "json", False):
        print(json.dumps([e.to_dict() for e in entries], indent=2))
        return
    if not entries:
        print("No feedback entries.")
        return
    for e in entries:
        ts = datetime.fromtimestamp(e.created_at).strftime("%Y-%m-%d %H:%M")
        print(f"  {ts}  [{e.item_id[:8]}]  {e.feedback}  q={e.query[:40]}  score={e.score_at_recall:.3f}")
    print(f"\n{len(entries)} entries")


def cmd_feedback_stats(ns: argparse.Namespace) -> None:
    """Show feedback statistics."""
    memos = _get_memos(ns)
    stats = memos.feedback_stats()
    if getattr(ns, "json", False):
        print(json.dumps(stats.to_dict(), indent=2))
        return
    print(f"  Total feedback:      {stats.total_feedback}")
    print(f"  Relevant:            {stats.relevant_count}")
    print(f"  Not relevant:        {stats.not_relevant_count}")
    print(f"  Items with feedback: {stats.items_with_feedback}")
    print(f"  Avg feedback score:  {stats.avg_feedback_score:.3f}")


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


def cmd_tags(ns: argparse.Namespace) -> None:
    """Tag management commands."""
    action = getattr(ns, "tags_action", "list") or "list"
    memos = _get_memos(ns)

    if action == "delete":
        count = memos.delete_tag(ns.tag)
        print(f"✓ Deleted tag '{ns.tag}' ({count} memory(s) updated)")
        return

    if action == "rename":
        count = memos.rename_tag(ns.old_tag, ns.new_tag)
        print(f"✓ Renamed tag '{ns.old_tag}' → '{ns.new_tag}' ({count} memory(s) updated)")
        return

    # Default: list
    sort_by = getattr(ns, "tags_sort", "count") or "count"
    limit = getattr(ns, "tags_limit", 0) or 0
    tags = memos.list_tags(sort=sort_by, limit=limit)

    if getattr(ns, "json", False):
        out = [{"tag": t, "count": c} for t, c in tags]
        print(json.dumps(out, ensure_ascii=False))
    else:
        if not tags:
            print("No tags found.")
            return
        max_tag_len = max(len(t) for t, _ in tags)
        for tag, count in tags:
            print(f"  {tag:<{max_tag_len}}  {count}")


def cmd_wake_up(ns: argparse.Namespace) -> None:
    """Print L0 (identity) + L1 (top memories) context for session priming."""
    from ..context import ContextStack

    memos = _get_memos(ns)
    cs = ContextStack(memos)
    output = cs.wake_up(
        max_chars=ns.max_chars,
        l1_top=ns.l1_top,
        include_stats=not ns.no_stats,
        compact=getattr(ns, "compact", False),
    )
    print(output)


def cmd_identity(ns: argparse.Namespace) -> None:
    """Manage agent identity (L0 context)."""
    from ..context import ContextStack

    action = getattr(ns, "identity_action", None) or "show"
    # identity uses its own path, not a memos backend
    # We instantiate ContextStack with a dummy memos only if needed
    # For show/set we only need the file path

    class _Stub:
        """Minimal stub so ContextStack can be constructed without a full backend."""

        namespace = ""

        def _store(self):  # pragma: no cover
            pass

    cs = ContextStack(_Stub())  # type: ignore[arg-type]

    if action == "set":
        text = ns.text
        if text is None or text == "-":
            text = sys.stdin.read()
        cs.set_identity(text)
        print(f"Identity written to {cs._identity_path}")
    else:
        content = cs.get_identity()
        if content:
            print(content)
        else:
            print(f"(no identity file at {cs._identity_path})")


def cmd_context_for(ns: argparse.Namespace) -> None:
    """Print context optimised for a specific query (L0 + L3)."""
    from ..context import ContextStack

    memos = _get_memos(ns)
    cs = ContextStack(memos)
    output = cs.context_for(
        query=ns.query,
        max_chars=ns.max_chars,
        top=ns.top,
    )
    print(output)


def cmd_classify(ns: argparse.Namespace) -> None:
    """Classify text into memory type tags."""
    from ..tagger import AutoTagger

    tagger = AutoTagger()
    text = ns.text

    if ns.detailed:
        result = tagger.tag_detailed(text)
        if not result:
            print("No type tags detected.")
            return
        for tag, matches in result.items():
            print(f"  {tag}: {', '.join(matches)}")
    else:
        tags = tagger.tag(text)
        if not tags:
            print("No type tags detected.")
        else:
            print(f"Tags: {', '.join(tags)}")


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


def cmd_wiki_living(ns: argparse.Namespace) -> None:
    """Living wiki commands."""
    from ..wiki_living import LivingWikiEngine

    memos = _get_memos(ns)
    wiki_dir = getattr(ns, "wiki_dir", None)
    engine = LivingWikiEngine(memos, wiki_dir=wiki_dir)

    action = getattr(ns, "wl_action", None)
    if action == "init":
        result = engine.init()
        print(f"Living wiki initialized: {result['wiki_dir']}")
        print(f"  Pages dir: {result['pages_dir']}")
        print(f"  DB: {result['db']}")

    elif action == "update":
        result = engine.update(force=getattr(ns, "force", False))
        print("Living wiki updated:")
        print(f"  Pages created: {result.pages_created}")
        print(f"  Pages updated: {result.pages_updated}")
        print(f"  Entities found: {result.entities_found}")
        print(f"  Memories indexed: {result.memories_indexed}")
        print(f"  Backlinks added: {result.backlinks_added}")

    elif action == "lint":
        report = engine.lint()
        issues = 0
        if report.orphan_pages:
            print(f"🟡 Orphan pages ({len(report.orphan_pages)}):")
            for p in report.orphan_pages:
                print(f"  - {p}")
            issues += len(report.orphan_pages)
        if report.empty_pages:
            print(f"🔵 Empty pages ({len(report.empty_pages)}):")
            for p in report.empty_pages:
                print(f"  - {p}")
            issues += len(report.empty_pages)
        if report.contradictions:
            print(f"🔴 Contradictions ({len(report.contradictions)}):")
            for c in report.contradictions:
                print(f"  - {c['entity']}: {c['conflicting_terms']}")
            issues += len(report.contradictions)
        if report.stale_pages:
            print(f"🟠 Stale pages ({len(report.stale_pages)}):")
            for p in report.stale_pages:
                print(f"  - {p}")
            issues += len(report.stale_pages)
        if report.missing_backlinks:
            print(f"⚪ Missing backlinks ({len(report.missing_backlinks)}):")
            for src, tgt in report.missing_backlinks:
                print(f"  - {src} → {tgt}")
            issues += len(report.missing_backlinks)
        if issues == 0:
            print("✅ Living wiki is clean — no issues found.")
        else:
            print(f"\nTotal issues: {issues}")

    elif action == "index":
        content = engine.regenerate_index()
        print(content)

    elif action == "log":
        entries = engine.get_log(limit=getattr(ns, "limit", 20))
        if not entries:
            print("No activity log entries.")
        for e in entries:
            print(f"  {e['time']} [{e['action']}] {e['entity']} — {e['detail']}")

    elif action == "read":
        content = engine.read_page(ns.entity)
        if content is None:
            print(f"No living page found for '{ns.entity}'.", file=sys.stderr)
            sys.exit(1)
        print(content)

    elif action == "search":
        results = engine.search(ns.query)
        if not results:
            print(f"No matches for '{ns.query}'.")
        for r in results:
            print(f"  [{r['type']}] {r['entity']} ({r['matches']} matches)")
            print(f"    ...{r['snippet']}...")

    elif action == "list":
        pages = engine.list_pages()
        if not pages:
            print("No living pages. Run: memos wiki-living update")
        for p in pages:
            bl = f" ←{len(p.backlinks)}" if p.backlinks else ""
            mc = len(p.memory_ids)
            print(f"  [{p.entity_type}] {p.entity} ({mc} mems{bl})")

    elif action == "stats":
        s = engine.stats()
        print("Living Wiki Stats:")
        print(f"  Entities: {s['total_entities']}")
        print(f"  Memory links: {s['total_memory_links']}")
        print(f"  Backlinks: {s['total_backlinks']}")
        print(f"  Types: {s['type_distribution']}")

    else:
        print("No wiki-living action specified. Use: init, update, lint, index, log, read, search, list, stats")


def cmd_wiki_graph(ns: argparse.Namespace) -> None:
    """Generate or read graph-community wiki pages."""
    from ..wiki_graph import GraphWikiEngine

    kg = _get_kg(ns)
    try:
        engine = GraphWikiEngine(kg, output_dir=getattr(ns, "output", None))
        community_id = getattr(ns, "community", None)
        if community_id:
            content = engine.read_community(community_id)
            if content is None:
                print(f"No graph community found for '{community_id}'.", file=sys.stderr)
                sys.exit(1)
            print(content)
            return

        result = engine.build(update=getattr(ns, "update", False))
        print("Graph wiki built:")
        print(f"  Communities: {result.community_count}")
        print(f"  Facts indexed: {result.facts_indexed}")
        print(f"  Pages written: {result.pages_written}")
        print(f"  Pages skipped: {result.pages_skipped}")
        print(f"  Pages removed: {result.pages_removed}")
        print(f"  God nodes: {result.god_nodes}")
        print(f"  Output: {result.output_dir}")
    finally:
        kg.close()


def cmd_brain_search(ns: argparse.Namespace) -> None:
    """Run unified search across memories, living wiki pages, and the knowledge graph."""
    from ..brain import BrainSearch

    memos = _get_memos(ns)
    kg = _get_kg(ns)
    try:
        searcher = BrainSearch(memos, kg=kg, wiki_dir=getattr(ns, "wiki_dir", None))
        tags = ns.tags.split(",") if getattr(ns, "tags", None) else None
        result = searcher.search(ns.query, top_k=ns.top, filter_tags=tags)
        print(f"Brain search: {ns.query}")
        if result.entities:
            print("Entities:", ", ".join(result.entities))
        print(f"Memories: {len(result.memories)}")
        for item in result.memories:
            print(f"  [{item.score:.2f}] {item.content}")
        print(f"Wiki pages: {len(result.wiki_pages)}")
        for item in result.wiki_pages:
            print(f"  [{item.score:.2f}] {item.entity}: {item.snippet}")
        print(f"KG facts: {len(result.kg_facts)}")
        for item in result.kg_facts:
            print(f"  [{item.confidence_label}] {item.subject} -{item.predicate}-> {item.object}")
        print("Context:")
        print(result.context)
    finally:
        kg.close()


def cmd_dedup_check(ns: argparse.Namespace) -> None:
    """Check if a text would be a duplicate of existing memories."""
    m = _get_memos(ns)
    result = m.dedup_check(ns.content, threshold=getattr(ns, "threshold", None))
    if result.is_duplicate:
        match_id = result.match.id if result.match else "N/A"
        print(f"DUPLICATE ({result.reason}, similarity={result.similarity:.3f})")
        print(f"  Match ID: {match_id}")
        if result.match:
            print(f"  Content:  {result.match.content[:200]}")
    else:
        print("NO DUPLICATE FOUND")


def cmd_dedup_scan(ns: argparse.Namespace) -> None:
    """Scan all memories for duplicates."""
    m = _get_memos(ns)
    result = m.dedup_scan(
        fix=getattr(ns, "fix", False),
        threshold=getattr(ns, "threshold", None),
    )
    print("Dedup scan complete:")
    print(f"  Total scanned:     {result.total_scanned}")
    print(f"  Exact duplicates:  {result.exact_duplicates}")
    print(f"  Near duplicates:   {result.near_duplicates}")
    print(f"  Total duplicates:  {result.total_duplicates}")
    if getattr(ns, "fix", False):
        print(f"  Removed:           {result.fixed}")
    if result.groups:
        print("\nDuplicates found:")
        for g in result.groups[:20]:
            print(f"  [{g['reason']}] {g['duplicate_id'][:8]} → {g['original_id'][:8]} (sim={g['similarity']:.3f})")
            print(f"    {g['content_preview'][:80]}")
