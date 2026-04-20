"""MemOS CLI — feedback commands."""

from __future__ import annotations

import argparse
import json
import sys
import sys as _sys
from datetime import datetime


def _get_memos(ns):
    return _sys.modules["memos.cli.commands_memory"]._get_memos(ns)


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
