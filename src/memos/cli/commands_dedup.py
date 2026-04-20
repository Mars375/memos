"""MemOS CLI — deduplication commands."""

from __future__ import annotations

import argparse
import sys as _sys


def _get_memos(ns):
    return _sys.modules["memos.cli.commands_memory"]._get_memos(ns)


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
