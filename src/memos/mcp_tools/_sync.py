"""Sync tools: memory_sync_check, memory_sync_apply."""

from __future__ import annotations

from typing import Any

from ._registry import _error, _text, register_tool

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_MEMORY_SYNC_CHECK = {
    "name": "memory_sync_check",
    "description": (
        "Check for conflicts between local memory store and a remote export envelope. "
        "Returns a report of new, unchanged, and conflicting memories."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "envelope": {
                "type": "object",
                "description": "Remote memory envelope (JSON object with source_agent, target_agent, memories)",
            },
        },
        "required": ["envelope"],
    },
}

_MEMORY_SYNC_APPLY = {
    "name": "memory_sync_apply",
    "description": (
        "Apply remote memories to the local store with conflict resolution. "
        "Strategies: local_wins, remote_wins, merge (default). "
        "Merge unions tags, takes most recent content, max importance."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "envelope": {
                "type": "object",
                "description": "Remote memory envelope (JSON object with source_agent, target_agent, memories)",
            },
            "strategy": {
                "type": "string",
                "default": "merge",
                "description": "Conflict resolution: local_wins, remote_wins, merge, manual",
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "If true, report what would happen without applying changes",
            },
        },
        "required": ["envelope"],
    },
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_memory_sync_check(args: dict, memos: Any) -> dict:
    from ..conflict import ConflictDetector
    from ..sharing.models import MemoryEnvelope

    envelope_data = args.get("envelope", {})
    if not envelope_data:
        return _error("envelope is required")
    try:
        envelope = MemoryEnvelope.from_dict(envelope_data)
    except Exception as exc:
        return _error(f"Invalid envelope: {exc}")
    detector = ConflictDetector()
    report = detector.detect(memos, envelope)
    rdict = report.to_dict()
    lines = [
        f"Sync check: {rdict['total_remote']} remote, {rdict['new_memories']} new, {rdict['unchanged']} unchanged, {rdict['conflict_count']} conflicts"
    ]
    for c in report.conflicts:
        types = ", ".join(t.value for t in c.conflict_types)
        lines.append(f"  \u26a0 {c.memory_id[:12]}\u2026 [{types}]")
    if rdict["errors"]:
        lines.append(f"  Errors: {len(rdict['errors'])}")
    return _text("\n".join(lines))


def _handle_memory_sync_apply(args: dict, memos: Any) -> dict:
    from ..conflict import ConflictDetector, ResolutionStrategy
    from ..sharing.models import MemoryEnvelope

    envelope_data = args.get("envelope", {})
    if not envelope_data:
        return _error("envelope is required")
    try:
        envelope = MemoryEnvelope.from_dict(envelope_data)
    except Exception as exc:
        return _error(f"Invalid envelope: {exc}")
    strategy_name = args.get("strategy", "merge")
    try:
        strategy = ResolutionStrategy(strategy_name)
    except ValueError:
        return _error(f"Invalid strategy: {strategy_name}")
    detector = ConflictDetector()
    report = detector.detect(memos, envelope)
    if args.get("dry_run", False):
        detector.resolve(report.conflicts, strategy)
        return _text(
            f"Dry run: {len(report.conflicts)} conflicts would be resolved with {strategy.value}, {report.new_memories} new memories added"
        )
    report = detector.apply(memos, report, strategy)
    return _text(
        f"Sync applied ({strategy.value}): {report.applied} applied, {report.skipped} skipped, {len(report.conflicts)} conflicts resolved"
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_tool("memory_sync_check", _MEMORY_SYNC_CHECK, _handle_memory_sync_check)
register_tool("memory_sync_apply", _MEMORY_SYNC_APPLY, _handle_memory_sync_apply)
