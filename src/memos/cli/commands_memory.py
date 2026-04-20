"""MemOS CLI — memory commands (backward-compat shim).

All cmd_* functions have been moved to per-domain modules.
This file re-exports them so existing imports continue to work.
"""

from __future__ import annotations

from ._common import _fmt_ts, _get_kg, _get_kg_bridge, _get_memos  # noqa: F401
from .commands_context import cmd_classify, cmd_context_for, cmd_identity, cmd_wake_up
from .commands_dedup import cmd_dedup_check, cmd_dedup_scan
from .commands_events import cmd_subscribe, cmd_watch
from .commands_feedback import cmd_feedback, cmd_feedback_list, cmd_feedback_stats
from .commands_maintenance import (
    cmd_benchmark,
    cmd_benchmark_quality,
    cmd_cache_stats,
    cmd_compact,
    cmd_compress,
    cmd_consolidate,
    cmd_decay,
    cmd_prune,
    cmd_prune_expired,
    cmd_reinforce,
)
from .commands_read import cmd_analytics, cmd_get, cmd_recall, cmd_search, cmd_stats, cmd_tags
from .commands_wiki import cmd_brain_search, cmd_wiki_graph, cmd_wiki_living
from .commands_write import cmd_batch_learn, cmd_forget, cmd_init, cmd_learn

__all__ = [
    "cmd_analytics",
    "cmd_batch_learn",
    "cmd_benchmark",
    "cmd_benchmark_quality",
    "cmd_brain_search",
    "cmd_cache_stats",
    "cmd_classify",
    "cmd_compact",
    "cmd_compress",
    "cmd_consolidate",
    "cmd_context_for",
    "cmd_decay",
    "cmd_dedup_check",
    "cmd_dedup_scan",
    "cmd_feedback",
    "cmd_feedback_list",
    "cmd_feedback_stats",
    "cmd_forget",
    "cmd_get",
    "cmd_identity",
    "cmd_init",
    "cmd_learn",
    "cmd_prune",
    "cmd_prune_expired",
    "cmd_recall",
    "cmd_reinforce",
    "cmd_search",
    "cmd_stats",
    "cmd_subscribe",
    "cmd_tags",
    "cmd_wake_up",
    "cmd_watch",
    "cmd_wiki_graph",
    "cmd_wiki_living",
]
