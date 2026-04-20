"""MemOS CLI — read/query memory commands."""

from __future__ import annotations

import argparse
import json
import sys
import sys as _sys
import time


def _get_memos(ns):
    return _sys.modules["memos.cli.commands_memory"]._get_memos(ns)


def _get_kg_bridge(ns, memos=None):
    return _sys.modules["memos.cli.commands_memory"]._get_kg_bridge(ns, memos=memos)


def _fmt_ts(epoch: float) -> str:
    return _sys.modules["memos.cli.commands_memory"]._fmt_ts(epoch)


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
