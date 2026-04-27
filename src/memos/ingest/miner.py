"""Smart memory miner compatibility facade.

The implementation is split across focused modules:
- ``_miner_common`` for result types and file iteration.
- ``_miner_files`` for file/directory chunk mining.
- ``_miner_conversations`` for conversation importers and auto-detection.

Public imports from ``memos.ingest.miner`` remain supported.
"""

from __future__ import annotations

from typing import Any, List, Optional

from ._miner_common import MineResult, iter_files
from ._miner_conversations import ConversationMiningMixin
from ._miner_files import FileMiningMixin
from .chunker import chunk_text, content_hash, detect_room
from .parsers import (
    _parse_chatgpt_export,
    _parse_claude_export,
    _parse_discord_export,
    _parse_openclaw_session,
    _parse_slack_jsonl,
    _parse_telegram_export,
)


class Miner(FileMiningMixin, ConversationMiningMixin):
    """Smart memory miner — import conversations and projects into MemOS.

    Example:
        miner = Miner(memos)
        miner.mine_directory("~/notes/")
        miner.mine_claude_export("~/.claude/projects/.../conversation.json")
        result = miner.mine_chatgpt_export("~/Downloads/conversations.json")
        print(result)
    """

    def __init__(
        self,
        memos: Any,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        dry_run: bool = False,
        extra_tags: Optional[List[str]] = None,
        batch_size: int = 20,
        cache: Optional[Any] = None,
        update: bool = False,
    ) -> None:
        self._memos = memos
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._dry_run = dry_run
        self._extra_tags = extra_tags or []
        self._batch_size = batch_size
        self._cache = cache
        self._update = update
        self._seen_hashes: set[str] = set()


__all__ = [
    "Miner",
    "MineResult",
    "iter_files",
    "chunk_text",
    "content_hash",
    "detect_room",
    "_parse_chatgpt_export",
    "_parse_claude_export",
    "_parse_discord_export",
    "_parse_openclaw_session",
    "_parse_slack_jsonl",
    "_parse_telegram_export",
]
