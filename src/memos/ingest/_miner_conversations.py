"""Conversation import and auto-detection mixin for memory mining."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from ._miner_common import MineResult, iter_files
from .parsers import (
    _parse_chatgpt_export,
    _parse_claude_export,
    _parse_discord_export,
    _parse_openclaw_session,
    _parse_slack_jsonl,
    _parse_telegram_export,
)

logger = logging.getLogger(__name__)


class ConversationMiningMixin:
    """Mine supported conversation export formats."""

    def mine_claude_export(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.65,
    ) -> MineResult:
        """Import a Claude conversation export JSON file."""
        path = Path(path).expanduser()
        result = MineResult()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            result.errors.append(f"Parse error {path}: {exc}")
            return result

        base_tags = list(tags or []) + ["claude", "conversation"]

        for convo in _parse_claude_export(data):
            convo_tags = list(base_tags)
            if convo.get("source") and convo["source"] != "conversation":
                slug = re.sub(r"[^a-z0-9_]", "_", convo["source"].lower())[:30]
                if slug:
                    convo_tags.append(slug)
            result.merge(self._mine_chunks(convo["text"], convo_tags, importance=importance))

        return result

    def mine_chatgpt_export(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.65,
    ) -> MineResult:
        """Import a ChatGPT conversation export JSON file."""
        path = Path(path).expanduser()
        result = MineResult()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            result.errors.append(f"Parse error {path}: {exc}")
            return result

        base_tags = list(tags or []) + ["chatgpt", "conversation"]

        for convo in _parse_chatgpt_export(data):
            convo_tags = list(base_tags)
            if convo.get("source") and convo["source"] != "conversation":
                slug = re.sub(r"[^a-z0-9_]", "_", convo["source"].lower())[:30]
                if slug:
                    convo_tags.append(slug)
            result.merge(self._mine_chunks(convo["text"], convo_tags, importance=importance))

        return result

    def mine_slack_export(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
    ) -> MineResult:
        """Import a Slack JSONL export file."""
        path = Path(path).expanduser()
        result = MineResult()

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            result.errors.append(f"Read error {path}: {exc}")
            return result

        base_tags = list(tags or []) + ["slack", "conversation"]
        channel = path.stem
        if channel:
            base_tags.append(channel)

        for convo in _parse_slack_jsonl(lines):
            result.merge(self._mine_chunks(convo["text"], base_tags, importance=importance))

        return result

    def mine_discord_export(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.6,
    ) -> MineResult:
        """Import a Discord export JSON file (DiscordChatExporter format)."""
        path = Path(path).expanduser()
        result = MineResult()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            result.errors.append(f"Parse error {path}: {exc}")
            return result

        base_tags = list(tags or []) + ["discord", "conversation"]

        for convo in _parse_discord_export(data):
            convo_tags = list(base_tags)
            source = convo.get("source", "")
            if source and source not in ("", "discord"):
                slug = re.sub(r"[^a-z0-9_#]", "_", source.lower())[:40]
                if slug:
                    convo_tags.append(slug)
            result.merge(self._mine_chunks(convo["text"], convo_tags, importance=importance))

        return result

    def mine_telegram_export(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.6,
    ) -> MineResult:
        """Import a Telegram export JSON file (result.json from Telegram Desktop)."""
        path = Path(path).expanduser()
        result = MineResult()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            result.errors.append(f"Parse error {path}: {exc}")
            return result

        base_tags = list(tags or []) + ["telegram", "conversation"]

        for convo in _parse_telegram_export(data):
            convo_tags = list(base_tags)
            source = convo.get("source", "")
            if source:
                slug = re.sub(r"[^a-z0-9_]", "_", source.lower())[:30]
                if slug:
                    convo_tags.append(slug)
            chat_type = convo.get("chat_type", "")
            if chat_type and chat_type not in convo_tags:
                convo_tags.append(chat_type.replace("_", "-"))
            result.merge(self._mine_chunks(convo["text"], convo_tags, importance=importance))

        return result

    def mine_openclaw(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.7,
    ) -> MineResult:
        """Import OpenClaw session logs, agent summaries, or memory snapshots."""
        path = Path(path).expanduser()
        result = MineResult()

        if path.is_dir():
            for file_path in iter_files(path, extensions={".json", ".jsonl", ".md", ".txt"}):
                file_result = self.mine_openclaw(file_path, tags=tags, importance=importance)
                result.merge(file_result)
            return result

        base_tags = list(tags or []) + ["openclaw"]
        suffix = path.suffix.lower()

        if suffix == ".jsonl":
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                result.errors.append(str(exc))
                return result
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("JSON decode error in OpenClaw session", exc_info=True)
                    continue
                for convo in _parse_openclaw_session(item):
                    convo_tags = list(base_tags)
                    extra = convo.pop("_tags", [])
                    convo_tags.extend(extra)
                    result.merge(self._mine_chunks(convo["text"], convo_tags, importance=importance))
            return result

        if suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:
                result.errors.append(str(exc))
                return result

            for convo in _parse_openclaw_session(data):
                convo_tags = list(base_tags)
                extra = convo.pop("_tags", [])
                convo_tags.extend(extra)
                result.merge(self._mine_chunks(convo["text"], convo_tags, importance=importance))
            return result

        return self.mine_file(path, tags=base_tags, importance=importance)

    def mine_auto(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.6,
    ) -> MineResult:
        """Auto-detect format and mine accordingly."""
        path = Path(path).expanduser()

        if path.is_dir():
            path_lower = str(path).lower()
            if "openclaw" in path_lower or "cron" in path_lower:
                return self.mine_openclaw(path, tags=tags, importance=importance)
            return self.mine_directory(path, tags=tags, importance=importance)

        if path.suffix.lower() == ".jsonl":
            path_lower = str(path).lower()
            if "openclaw" in path_lower or "cron" in path_lower or "agent" in path_lower:
                return self.mine_openclaw(path, tags=tags, importance=importance)
            return self.mine_slack_export(path, tags=tags, importance=importance)

        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                return self.mine_file(path, tags=tags, importance=importance)

            root = data[0] if isinstance(data, list) and data else data

            if isinstance(root, dict):
                if "guild" in root and "channel" in root:
                    return self.mine_discord_export(path, tags=tags, importance=importance)

                if "messages" in root and isinstance(root["messages"], list):
                    messages = root["messages"]
                    sample = next((message for message in messages if isinstance(message, dict)), {})
                    if "from_id" in sample or "actor_id" in sample or "date" in sample:
                        if isinstance(sample.get("date"), str) and "from_id" in sample:
                            return self.mine_telegram_export(path, tags=tags, importance=importance)

                if any(key in root for key in ("job", "summary", "learnings", "decisions", "memories")):
                    return self.mine_openclaw(path, tags=tags, importance=importance)

                if "messages" in root or "chat_messages" in root:
                    return self.mine_claude_export(path, tags=tags, importance=importance)

                if "mapping" in root:
                    return self.mine_chatgpt_export(path, tags=tags, importance=importance)

        return self.mine_file(path, tags=tags, importance=importance)


__all__ = ["ConversationMiningMixin"]
