"""MemOS CLI — context/identity commands."""

from __future__ import annotations

import argparse
import sys
import sys as _sys


def _get_memos(ns):
    return _sys.modules["memos.cli.commands_memory"]._get_memos(ns)


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
