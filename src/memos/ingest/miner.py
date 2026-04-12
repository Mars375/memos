"""Smart memory miner — paragraph-aware chunking, deduplication, multi-format import.

Inspired by MemPalace's mining pipeline:
- 800-char chunks with 100-char overlap, respecting paragraph boundaries
- SHA-256 content deduplication (never store the same text twice)
- Room/tag auto-detection from file path → filename → keyword frequency
- Conversation importers: Claude JSON, ChatGPT export, Slack JSONL

Usage:
    from memos.ingest.miner import Miner
    miner = Miner(memos)
    miner.mine_directory("~/notes/")
    miner.mine_claude_export("~/.claude/projects/.../conversation.json")
    miner.mine_chatgpt_export("~/Downloads/conversations.json")
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, List, Optional

from .chunker import chunk_text, content_hash, detect_room, _ROOM_KEYWORDS
from .parsers import (
    _parse_claude_export,
    _parse_chatgpt_export,
    _parse_slack_jsonl,
    _parse_discord_export,
    _parse_telegram_export,
    _parse_openclaw_session,
)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class MineResult:
    imported: int = 0
    skipped_duplicates: int = 0
    skipped_empty: int = 0
    skipped_cached: int = 0
    errors: List[str] = field(default_factory=list)
    chunks: List[dict] = field(default_factory=list)  # populated in dry_run
    memory_ids: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"MineResult(imported={self.imported}, "
            f"dupes={self.skipped_duplicates}, "
            f"cached={self.skipped_cached}, "
            f"empty={self.skipped_empty}, "
            f"errors={len(self.errors)})"
        )

    def merge(self, other: "MineResult") -> None:
        self.imported += other.imported
        self.skipped_duplicates += other.skipped_duplicates
        self.skipped_empty += other.skipped_empty
        self.skipped_cached += other.skipped_cached
        self.errors.extend(other.errors)
        self.chunks.extend(other.chunks)
        self.memory_ids.extend(other.memory_ids)


# ---------------------------------------------------------------------------
# .gitignore-aware file iterator
# ---------------------------------------------------------------------------

_DEFAULT_IGNORE = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
    ".pytest_cache", "dist", "build", ".mypy_cache", ".ruff_cache",
    "*.pyc", "*.pyo", "*.egg-info",
}

_MINEABLE_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".rst",
    ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml",
    ".sql", ".sh", ".bash", ".zsh",
}


def iter_files(
    directory: Path,
    extensions: Optional[set] = None,
    max_files: int = 5000,
) -> Iterator[Path]:
    """Walk a directory yielding mineable files, respecting common ignores."""
    if extensions is None:
        extensions = _MINEABLE_EXTENSIONS

    count = 0
    for path in directory.rglob("*"):
        if count >= max_files:
            break
        if not path.is_file():
            continue
        # Skip ignored dirs
        if any(part.startswith(".") or part in _DEFAULT_IGNORE
               for part in path.parts):
            continue
        if path.suffix.lower() not in extensions:
            continue
        count += 1
        yield path


# ---------------------------------------------------------------------------
# Main Miner class
# ---------------------------------------------------------------------------

class Miner:
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
        # In-memory dedup set (hash → True)
        self._seen_hashes: set[str] = set()

    def _is_duplicate(self, text: str) -> bool:
        h = content_hash(text)
        if h in self._seen_hashes:
            return True
        self._seen_hashes.add(h)
        return False

    def _store_chunk(self, content: str, tags: List[str], importance: float = 0.5) -> bool:
        """Store one chunk. Returns True if stored, False if skipped."""
        content = content.strip()
        if len(content) < 20:
            return False
        if self._is_duplicate(content):
            return False
        if not self._dry_run:
            self._memos.learn(content, tags=tags, importance=importance)
        return True

    def _mine_chunks(
        self,
        text: str,
        base_tags: List[str],
        source_path: Optional[Path] = None,
        importance: float = 0.5,
        known_hashes: Optional[set] = None,
    ) -> MineResult:
        """Chunk text and store each chunk.

        Args:
            known_hashes: If provided (--diff mode), skip chunks whose content
                          hash is already in this set.
        """
        result = MineResult()
        chunks = chunk_text(text, size=self._chunk_size, overlap=self._chunk_overlap)

        batch: List[tuple[str, List[str], float]] = []

        for chunk in chunks:
            if len(chunk.strip()) < 20:
                result.skipped_empty += 1
                continue

            ch = content_hash(chunk)

            # --diff: skip chunks already in the persisted cache
            if known_hashes is not None and ch in known_hashes:
                result.skipped_cached += 1
                continue

            if self._is_duplicate(chunk):
                result.skipped_duplicates += 1
                continue

            tags = list(base_tags)
            if source_path:
                room_tags = detect_room(source_path, chunk)
                for t in room_tags:
                    if t not in tags:
                        tags.append(t)
            for t in self._extra_tags:
                if t not in tags:
                    tags.append(t)

            if self._dry_run:
                result.chunks.append({"content": chunk[:80] + "...", "tags": tags})
                result.imported += 1
            else:
                batch.append((chunk, tags, importance))
                if len(batch) >= self._batch_size:
                    self._flush_batch(batch, result)
                    batch = []

        if batch:
            self._flush_batch(batch, result)

        return result

    def _flush_batch(self, batch: List[tuple], result: MineResult) -> None:
        for content, tags, importance in batch:
            try:
                item = self._memos.learn(content, tags=tags, importance=importance)
                result.imported += 1
                if item is not None:
                    result.memory_ids.append(item.id)
            except Exception as exc:
                result.errors.append(str(exc))

    # ------------------------------------------------------------------
    # Public mining methods
    # ------------------------------------------------------------------

    def mine_file(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        diff: bool = False,
    ) -> MineResult:
        """Mine a single text/markdown/code file.

        Args:
            diff: If True, only mine chunks not previously seen for this file
                  (requires cache to be set).
        """
        path = Path(path).expanduser().resolve()
        result = MineResult()

        if not path.exists():
            result.errors.append(f"Not found: {path}")
            return result

        try:
            raw_bytes = path.read_bytes()
            text = raw_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            result.errors.append(f"Read error {path}: {exc}")
            return result

        file_sha256 = hashlib.sha256(raw_bytes).hexdigest()

        # Cache: skip entirely if file is unchanged (unless --update)
        if self._cache is not None and not self._update and not diff:
            if self._cache.is_fresh(str(path), file_sha256):
                result.skipped_cached += 1
                return result

        # --update: delete memories from the previous mine of this file
        if self._cache is not None and self._update:
            entry = self._cache.get(str(path))
            if entry and entry["memory_ids"]:
                for mid in entry["memory_ids"]:
                    try:
                        self._memos.forget(mid)
                    except Exception:
                        pass

        # --diff: collect hashes already stored for this file
        known_hashes: Optional[set] = None
        if diff and self._cache is not None:
            known_hashes = self._cache.get_chunk_hashes(str(path))

        base_tags = list(tags or [])
        base_tags += detect_room(path, text)

        chunk_result = self._mine_chunks(
            text, base_tags, source_path=path, importance=importance,
            known_hashes=known_hashes,
        )
        result.merge(chunk_result)

        # Record in cache after mining (skip in dry_run)
        if self._cache is not None and not self._dry_run:
            # Compute all chunk hashes for this file (union of old + new for diff mode)
            all_chunk_hashes: List[str] = []
            for c in chunk_text(text, size=self._chunk_size, overlap=self._chunk_overlap):
                if len(c.strip()) >= 20:
                    all_chunk_hashes.append(content_hash(c))
            if diff and known_hashes:
                # preserve hashes from previous mine that weren't overwritten
                merged = set(known_hashes) | set(all_chunk_hashes)
                all_chunk_hashes = list(merged)

            existing = self._cache.get(str(path))
            existing_ids: List[str] = (existing["memory_ids"] if existing else [])
            if self._update:
                existing_ids = []
            all_ids = existing_ids + result.memory_ids
            self._cache.record(
                str(path),
                file_sha256,
                memory_ids=all_ids,
                chunk_hashes=all_chunk_hashes,
            )

        return result

    def mine_directory(
        self,
        directory: str | Path,
        tags: Optional[List[str]] = None,
        extensions: Optional[set] = None,
        importance: float = 0.5,
        max_files: int = 500,
        diff: bool = False,
    ) -> MineResult:
        """Mine all files in a directory recursively."""
        directory = Path(directory).expanduser()
        result = MineResult()

        if not directory.is_dir():
            result.errors.append(f"Not a directory: {directory}")
            return result

        files = list(iter_files(directory, extensions=extensions, max_files=max_files))
        for f in files:
            r = self.mine_file(f, tags=tags, importance=importance, diff=diff)
            result.merge(r)

        return result

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
            result.merge(self._mine_chunks(
                convo["text"], convo_tags, importance=importance
            ))

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
            result.merge(self._mine_chunks(
                convo["text"], convo_tags, importance=importance
            ))

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
            result.merge(self._mine_chunks(
                convo["text"], base_tags, importance=importance
            ))

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
            result.merge(self._mine_chunks(
                convo["text"], convo_tags, importance=importance
            ))

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
            # Add channel type as tag (personal/group/channel)
            chat_type = convo.get("chat_type", "")
            if chat_type and chat_type not in convo_tags:
                convo_tags.append(chat_type.replace("_", "-"))
            result.merge(self._mine_chunks(
                convo["text"], convo_tags, importance=importance
            ))

        return result

    def mine_openclaw(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.7,
    ) -> MineResult:
        """Import OpenClaw session logs, agent summaries, or memory snapshots.

        Handles:
        - JSON session/cron logs ({"job": ..., "output": ...})
        - Agent summary JSON ({"summary": ..., "learnings": [...], "decisions": [...]})
        - Memory snapshot JSON ({"memories": [...]})
        - JSONL log files (one JSON object per line)
        - Directories of OpenClaw logs
        """
        path = Path(path).expanduser()
        result = MineResult()

        if path.is_dir():
            # Mine all JSON/JSONL/MD files in the directory
            for f in iter_files(path, extensions={".json", ".jsonl", ".md", ".txt"}):
                r = self.mine_openclaw(f, tags=tags, importance=importance)
                result.merge(r)
            return result

        base_tags = list(tags or []) + ["openclaw"]

        suffix = path.suffix.lower()

        # JSONL — one record per line
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
                    for convo in _parse_openclaw_session(item):
                        t = list(base_tags)
                        extra = convo.pop("_tags", [])
                        t.extend(extra)
                        result.merge(self._mine_chunks(convo["text"], t, importance=importance))
                except json.JSONDecodeError:
                    pass
            return result

        # JSON
        if suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:
                result.errors.append(str(exc))
                return result

            for convo in _parse_openclaw_session(data):
                t = list(base_tags)
                extra = convo.pop("_tags", [])
                t.extend(extra)
                result.merge(self._mine_chunks(convo["text"], t, importance=importance))
            return result

        # Markdown / text — fallback to mine_file
        return self.mine_file(path, tags=base_tags, importance=importance)

    def mine_auto(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.6,
    ) -> MineResult:
        """Auto-detect format and mine accordingly.

        Detection order:
        1. Directory → mine_directory
        2. .jsonl → Slack (default) or OpenClaw if path contains 'openclaw'/'cron'
        3. .json → sniff structure:
           - Discord: has "guild" + "channel" + "messages"
           - Telegram: has "messages" with Telegram fields (from_id, date as string)
           - OpenClaw: has "job"/"summary"/"memories"/"learnings"
           - Claude: has "messages" with role=human/assistant
           - ChatGPT: has "mapping"
        4. Otherwise → mine_file
        """
        path = Path(path).expanduser()

        if path.is_dir():
            # Check if it looks like an OpenClaw dir
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

            # Sniff structure
            root = data[0] if isinstance(data, list) and data else data

            if isinstance(root, dict):
                # Discord: guild + channel keys
                if "guild" in root and "channel" in root:
                    return self.mine_discord_export(path, tags=tags, importance=importance)

                # Telegram: messages list where items have "from_id" or "actor_id"
                if "messages" in root and isinstance(root["messages"], list):
                    msgs = root["messages"]
                    sample = next((m for m in msgs if isinstance(m, dict)), {})
                    if "from_id" in sample or "actor_id" in sample or "date" in sample:
                        # Check if date is ISO string (Telegram style) vs dict (Claude style)
                        if isinstance(sample.get("date"), str) and "from_id" in sample:
                            return self.mine_telegram_export(path, tags=tags, importance=importance)

                # OpenClaw: job/summary/memories/learnings fields
                if any(k in root for k in ("job", "summary", "learnings", "decisions", "memories")):
                    return self.mine_openclaw(path, tags=tags, importance=importance)

                # Claude: messages with role=human/assistant
                if "messages" in root or "chat_messages" in root:
                    return self.mine_claude_export(path, tags=tags, importance=importance)

                # ChatGPT: mapping tree
                if "mapping" in root:
                    return self.mine_chatgpt_export(path, tags=tags, importance=importance)

        return self.mine_file(path, tags=tags, importance=importance)
