"""MemOS CLI — write/modify memory commands."""

from __future__ import annotations

import argparse
import json
import sys
import sys as _sys
from pathlib import Path

from .. import __version__
from ..models import parse_ttl


def _get_memos(ns):
    return _sys.modules["memos.cli.commands_memory"]._get_memos(ns)


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
