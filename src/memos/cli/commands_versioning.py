"""MemOS CLI — versioning commands."""

from __future__ import annotations

import argparse
import json
import sys

from ._common import _get_memos, _parse_timestamp, _fmt_ts


def cmd_history(ns: argparse.Namespace) -> None:
    """Show version history for a memory item."""
    memos = _get_memos(ns)
    versions = memos.history(ns.item_id)
    if not versions:
        print(f"No version history for item {ns.item_id[:12]}...")
        return
    if getattr(ns, "json", False):
        print(json.dumps([v.to_dict() for v in versions], indent=2))
        return
    print(f"Version history for {ns.item_id[:12]}...  ({len(versions)} versions)\n")
    for v in versions:
        preview = v.content[:80].replace("\n", " ")
        print(f"  v{v.version_number:>3d}  {_fmt_ts(v.created_at)}  [{v.source:12s}]  {preview}")
    print()


def cmd_diff(ns: argparse.Namespace) -> None:
    """Show diff between two versions of a memory."""
    memos = _get_memos(ns)
    item_id = ns.item_id
    if getattr(ns, "latest", False):
        result = memos.diff_latest(item_id)
        if result is None:
            print(f"Fewer than 2 versions for item {item_id[:12]}...")
            return
    else:
        v1, v2 = ns.v1, ns.v2
        if v1 is None or v2 is None:
            print("Error: provide --v1 and --v2, or --latest", file=sys.stderr)
            sys.exit(1)
        result = memos.diff(item_id, v1, v2)
        if result is None:
            print(f"Version(s) not found for item {item_id[:12]}...")
            return
    if getattr(ns, "json", False):
        print(json.dumps(result.to_dict(), indent=2))
        return
    d = result.to_dict()
    print(f"Diff: {item_id[:12]}...  v{d['from_version']} -> v{d['to_version']}  "
          f"(delta {d['delta_seconds']:.1f}s)\n")
    if not d["changes"]:
        print("  (no changes)")
    else:
        for field, change in d["changes"].items():
            print(f"  {field}:")
            if field == "tags":
                old = ", ".join(change.get("from", []))
                new = ", ".join(change.get("to", []))
                added = change.get("added", [])
                removed = change.get("removed", [])
                print(f"    - {old or '(none)'}")
                print(f"    + {new or '(none)'}")
                if added:
                    print(f"    added: {', '.join(added)}")
                if removed:
                    print(f"    removed: {', '.join(removed)}")
            elif field == "content":
                print(f"    - {change['from'][:200]}")
                print(f"    + {change['to'][:200]}")
            else:
                print(f"    {change.get('from', '?')} -> {change.get('to', '?')}")
    print()


def cmd_rollback(ns: argparse.Namespace) -> None:
    """Roll back a memory item to a specific version."""
    memos = _get_memos(ns)
    if getattr(ns, "dry_run", False):
        ver = memos.get_version(ns.item_id, ns.version)
        if ver is None:
            print(f"Version {ns.version} not found for item {ns.item_id[:12]}...", file=sys.stderr)
            sys.exit(1)
        print(f"Would roll back {ns.item_id[:12]}... to v{ns.version}:")
        print(f"  Content: {ver.content[:120]}")
        print(f"  Tags: {', '.join(ver.tags) or '(none)'}")
        print("(dry-run)")
        return
    if not getattr(ns, "yes", False):
        ver = memos.get_version(ns.item_id, ns.version)
        if ver is None:
            print(f"Version {ns.version} not found for item {ns.item_id[:12]}...", file=sys.stderr)
            sys.exit(1)
        print(f"Will roll back {ns.item_id[:12]}... to v{ns.version}:")
        print(f"  Content: {ver.content[:120]}")
        print(f"  Tags: {', '.join(ver.tags) or '(none)'}")
        print(f"  Importance: {ver.importance}")
        print("Use --yes to confirm.")
        return
    result = memos.rollback(ns.item_id, ns.version)
    if result is None:
        print(f"X Rollback failed - version {ns.version} not found", file=sys.stderr)
        sys.exit(1)
    print(f"OK Rolled back {ns.item_id[:12]}... to v{ns.version}")


def cmd_snapshot_at(ns: argparse.Namespace) -> None:
    """Show all memories as they were at a given point in time."""
    memos = _get_memos(ns)
    ts = _parse_timestamp(ns.timestamp)
    versions = memos.snapshot_at(ts)
    if getattr(ns, "json", False):
        print(json.dumps([v.to_dict() for v in versions], indent=2))
        return
    print(f"Snapshot at {_fmt_ts(ts)}  ({len(versions)} memories)\n")
    if not versions:
        print("  (no memories existed at that time)")
        return
    for v in versions[:50]:
        tags_str = f" [{', '.join(v.tags[:3])}]" if v.tags else ""
        vc = v.content[:100].replace("\n", " ")
        print(f"  [{v.item_id[:8]}] {vc}{tags_str}  (v{v.version_number})")
    if len(versions) > 50:
        print(f"\n  ... and {len(versions) - 50} more")
    print()


def cmd_recall_at(ns: argparse.Namespace) -> None:
    """Time-travel recall - query memories at a past time."""
    memos = _get_memos(ns)
    ts = _parse_timestamp(ns.timestamp)
    results = memos.recall_at(ns.query, ts, top=ns.top, min_score=ns.min_score)
    if getattr(ns, "json", False):
        print(json.dumps([{"id": r.item.id, "content": r.item.content,
                           "score": round(r.score, 4), "tags": r.item.tags,
                           "match_reason": r.match_reason} for r in results], indent=2))
        return
    if not results:
        print(f"No memories found at {_fmt_ts(ts)}.")
        return
    print(f"Recall at {_fmt_ts(ts)}  ({len(results)} results)\n")
    for r in results:
        tags_str = f" [{', '.join(r.item.tags)}]" if r.item.tags else ""
        print(f"  {r.score:.3f} {r.item.content[:120]}{tags_str}")
    print(f"\n{len(results)} result(s)")


def cmd_version_stats(ns: argparse.Namespace) -> None:
    """Show versioning statistics."""
    memos = _get_memos(ns)
    s = memos.versioning_stats()
    if getattr(ns, "json", False):
        print(json.dumps(s, indent=2))
        return
    print("Versioning Statistics\n")
    print(f"  Total versions:        {s.get('total_versions', 0)}")
    print(f"  Tracked items:         {s.get('total_items', 0)}")
    print(f"  Avg versions/item:     {s.get('avg_versions_per_item', 0):.1f}")
    print(f"  Max versions/item:     {s.get('max_versions_per_item', 0)}")
    oldest = s.get('oldest_version')
    print(f"  Oldest version:        {_fmt_ts(oldest) if oldest else 'N/A'}")
    print(f"  Estimated memory (KB): {s.get('estimated_size_kb', 0):.1f}")


def cmd_version_gc(ns: argparse.Namespace) -> None:
    """Garbage collect old memory versions."""
    memos = _get_memos(ns)
    if getattr(ns, "dry_run", False):
        sb = memos.versioning_stats()
        print(f"Current: {sb.get('total_versions', 0)} versions")
        print(f"Would remove versions older than {ns.max_age_days} days "
              f"(keeping latest {ns.keep_latest}/item)")
        return
    removed = memos.versioning_gc(max_age_days=ns.max_age_days, keep_latest=ns.keep_latest)
    print(f"OK Garbage collected {removed} old versions")


