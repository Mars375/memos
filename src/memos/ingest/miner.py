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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, List, Optional

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class MineResult:
    imported: int = 0
    skipped_duplicates: int = 0
    skipped_empty: int = 0
    errors: List[str] = field(default_factory=list)
    chunks: List[dict] = field(default_factory=list)  # populated in dry_run

    def __str__(self) -> str:
        return (
            f"MineResult(imported={self.imported}, "
            f"dupes={self.skipped_duplicates}, "
            f"empty={self.skipped_empty}, "
            f"errors={len(self.errors)})"
        )

    def merge(self, other: "MineResult") -> None:
        self.imported += other.imported
        self.skipped_duplicates += other.skipped_duplicates
        self.skipped_empty += other.skipped_empty
        self.errors.extend(other.errors)
        self.chunks.extend(other.chunks)


# ---------------------------------------------------------------------------
# Core chunking — paragraph-aware with overlap (MemPalace style)
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    size: int = 800,
    overlap: int = 100,
) -> List[str]:
    """Split text into chunks respecting paragraph boundaries.

    Strategy (MemPalace-inspired):
    1. Split on double-newlines (paragraphs)
    2. Accumulate paragraphs until chunk is full
    3. When a chunk is committed, carry the last `overlap` chars into next chunk
    4. Never cut mid-paragraph unless a single paragraph > size

    Args:
        text: Raw text to chunk
        size: Target max chars per chunk (default 800)
        overlap: How many chars to carry over to next chunk (default 100)

    Returns:
        List of chunk strings
    """
    text = text.strip()
    if not text:
        return []

    # Split into paragraphs (preserve single-newline within paragraphs)
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]

    if not paragraphs:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)

        # Single paragraph larger than size — split by sentence
        if para_len > size:
            # Flush current buffer first
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0

            # Split oversized paragraph by sentences
            sentences = re.split(r'(?<=[.!?])\s+', para)
            buf = ""
            for sent in sentences:
                if len(buf) + len(sent) + 1 <= size:
                    buf = f"{buf} {sent}".strip() if buf else sent
                else:
                    if buf:
                        chunks.append(buf)
                    buf = sent
            if buf:
                chunks.append(buf)
            continue

        # Would adding this paragraph overflow the chunk?
        sep_len = 2 if current else 0  # "\n\n" separator
        if current_len + sep_len + para_len > size and current:
            # Commit current chunk
            chunk_text_str = "\n\n".join(current)
            chunks.append(chunk_text_str)

            # Overlap: carry last `overlap` chars as context for next chunk
            if overlap > 0 and chunk_text_str:
                overlap_text = chunk_text_str[-overlap:].strip()
                if overlap_text:
                    current = [overlap_text]
                    current_len = len(overlap_text)
                else:
                    current = []
                    current_len = 0
            else:
                current = []
                current_len = 0

        current.append(para)
        current_len += len(para) + (2 if len(current) > 1 else 0)

    if current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Content deduplication
# ---------------------------------------------------------------------------

def content_hash(text: str) -> str:
    """SHA-256 hash of normalized content (lowercase, collapsed whitespace)."""
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Room / tag auto-detection from file path + keyword frequency
# (MemPalace detect_room strategy)
# ---------------------------------------------------------------------------

_ROOM_KEYWORDS: dict[str, List[str]] = {
    "auth": ["auth", "login", "password", "token", "oauth", "jwt", "session", "credential"],
    "deployment": ["deploy", "docker", "kubernetes", "k8s", "ci", "cd", "pipeline", "release", "helm"],
    "database": ["sql", "postgres", "mysql", "sqlite", "redis", "mongo", "migration", "schema"],
    "api": ["api", "endpoint", "rest", "graphql", "webhook", "request", "response", "route"],
    "frontend": ["react", "vue", "angular", "css", "html", "component", "ui", "ux", "tailwind"],
    "backend": ["server", "fastapi", "flask", "django", "express", "node", "python", "go"],
    "testing": ["test", "pytest", "jest", "mock", "coverage", "assertion", "fixture"],
    "security": ["security", "ssl", "tls", "xss", "csrf", "vulnerability", "permission"],
    "performance": ["perf", "latency", "throughput", "cache", "optimize", "memory", "cpu"],
    "devops": ["infra", "terraform", "ansible", "monitoring", "grafana", "prometheus", "alert"],
    "docs": ["readme", "documentation", "wiki", "spec", "design", "architecture"],
    "ai": ["llm", "gpt", "claude", "embedding", "vector", "prompt", "model", "inference"],
}


def detect_room(path: Path, text: str = "", top_n: int = 2) -> List[str]:
    """Detect room tags from file path → filename → keyword frequency.

    Strategy:
    1. Path components (e.g. src/auth/login.py → "auth")
    2. Filename keywords
    3. Top-N keyword matches in text content
    4. Fallback: file extension as tag
    """
    tags: List[str] = []

    # 1. Path components
    parts = [p.lower() for p in path.parts]
    for room, keywords in _ROOM_KEYWORDS.items():
        if any(kw in part for part in parts for kw in keywords):
            if room not in tags:
                tags.append(room)

    # 2. Filename
    stem = path.stem.lower()
    for room, keywords in _ROOM_KEYWORDS.items():
        if any(kw in stem for kw in keywords) and room not in tags:
            tags.append(room)

    if len(tags) >= top_n:
        return tags[:top_n]

    # 3. Keyword frequency in text
    if text:
        text_lower = text.lower()
        scores: dict[str, int] = {}
        for room, keywords in _ROOM_KEYWORDS.items():
            if room in tags:
                continue
            score = sum(text_lower.count(kw) for kw in keywords)
            if score > 0:
                scores[room] = score
        for room in sorted(scores, key=lambda r: -scores[r]):
            if room not in tags:
                tags.append(room)
            if len(tags) >= top_n:
                break

    # 4. Extension fallback
    ext = path.suffix.lstrip(".")
    if ext and ext not in ("md", "txt", "json") and ext not in tags:
        tags.append(ext)

    return tags[:top_n] if tags else []


# ---------------------------------------------------------------------------
# Conversation format parsers
# ---------------------------------------------------------------------------

def _parse_claude_export(data: Any) -> Iterator[dict]:
    """Parse Claude conversation export JSON.

    Claude exports are either:
    - A single conversation object with "messages" array
    - An array of conversations
    Each message has "role" and "content" (string or array of content blocks).
    """
    if isinstance(data, dict):
        # Single conversation
        convos = [data]
    elif isinstance(data, list):
        convos = data
    else:
        return

    for convo in convos:
        if not isinstance(convo, dict):
            continue
        name = convo.get("name") or convo.get("title") or "conversation"
        messages = convo.get("messages") or convo.get("chat_messages") or []
        created = convo.get("created_at") or convo.get("updated_at") or ""

        turns: List[str] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Content can be string or list of blocks
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                content = "\n".join(text_parts)

            if content and isinstance(content, str) and content.strip():
                prefix = "[Q]" if role == "human" else "[A]"
                turns.append(f"{prefix} {content.strip()}")

        if turns:
            yield {
                "text": "\n\n".join(turns),
                "source": name,
                "created": created,
                "format": "claude",
            }


def _parse_chatgpt_export(data: Any) -> Iterator[dict]:
    """Parse ChatGPT conversation export JSON.

    ChatGPT exports are a list of conversations, each with:
    - "title": string
    - "mapping": dict of node_id → {message: {author, content}}
    - "create_time": float timestamp
    """
    if isinstance(data, dict):
        convos = [data]
    elif isinstance(data, list):
        convos = data
    else:
        return

    for convo in convos:
        if not isinstance(convo, dict):
            continue
        title = convo.get("title", "conversation")
        mapping = convo.get("mapping", {})
        create_time = convo.get("create_time")

        turns: List[str] = []
        for node in mapping.values():
            if not isinstance(node, dict):
                continue
            msg = node.get("message")
            if not msg:
                continue
            author = msg.get("author", {}).get("role", "")
            content_obj = msg.get("content", {})

            # Content has "content_type" and "parts"
            if isinstance(content_obj, dict):
                parts = content_obj.get("parts", [])
                text = " ".join(str(p) for p in parts if p)
            elif isinstance(content_obj, str):
                text = content_obj
            else:
                continue

            if text.strip() and author in ("user", "assistant"):
                prefix = "[Q]" if author == "user" else "[A]"
                turns.append(f"{prefix} {text.strip()}")

        if turns:
            created = ""
            if create_time:
                import datetime
                created = datetime.datetime.fromtimestamp(create_time).isoformat()
            yield {
                "text": "\n\n".join(turns),
                "source": title,
                "created": created,
                "format": "chatgpt",
            }


def _parse_slack_jsonl(lines: List[str]) -> Iterator[dict]:
    """Parse Slack JSONL export (one JSON object per line).

    Slack messages have: ts, user, text, (optionally thread_ts).
    """
    messages: List[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if isinstance(msg, dict) and "text" in msg and msg["text"].strip():
                messages.append(msg)
        except json.JSONDecodeError:
            continue

    if not messages:
        return

    # Group messages into conversations by time proximity (5-minute windows)
    messages.sort(key=lambda m: float(m.get("ts", 0)))
    window = 300  # 5 minutes
    group: List[dict] = []
    group_start = float(messages[0].get("ts", 0)) if messages else 0

    for msg in messages:
        ts = float(msg.get("ts", 0))
        if ts - group_start > window and group:
            text = "\n".join(
                f"[{m.get('user', 'user')}] {m['text']}"
                for m in group if m.get("text", "").strip()
            )
            if text.strip():
                yield {
                    "text": text,
                    "source": "slack",
                    "created": "",
                    "format": "slack",
                }
            group = []
            group_start = ts
        group.append(msg)

    if group:
        text = "\n".join(
            f"[{m.get('user', 'user')}] {m['text']}"
            for m in group if m.get("text", "").strip()
        )
        if text.strip():
            yield {
                "text": text,
                "source": "slack",
                "created": "",
                "format": "slack",
            }


# ---------------------------------------------------------------------------
# Discord export parser
# ---------------------------------------------------------------------------

def _parse_discord_export(data: Any) -> Iterator[dict]:
    """Parse Discord export JSON (DiscordChatExporter format).

    Top-level structure:
    {
      "guild": {"name": "..."},
      "channel": {"name": "...", "type": "..."},
      "messages": [
        {"id": "...", "timestamp": "...", "author": {"name": "..."}, "content": "...",
         "embeds": [...], "attachments": [...]}
      ]
    }
    Also handles exported arrays of channels.
    """
    if isinstance(data, list):
        for item in data:
            yield from _parse_discord_export(item)
        return

    if not isinstance(data, dict):
        return

    guild_name = data.get("guild", {}).get("name", "")
    channel = data.get("channel", {})
    channel_name = channel.get("name", "")
    channel_type = channel.get("type", "")

    messages = data.get("messages", [])
    if not messages:
        return

    # Group messages into conversation windows (10-min windows)
    parsed: List[dict] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "").strip()
        # Also grab embed descriptions
        for embed in msg.get("embeds", []):
            if isinstance(embed, dict):
                desc = embed.get("description", "")
                if desc:
                    content += f"\n{desc}"
        if not content:
            continue
        author = msg.get("author", {}).get("name", "user")
        ts_str = msg.get("timestamp", "")
        # Parse ISO timestamp to float
        ts = 0.0
        if ts_str:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts = dt.timestamp()
            except Exception:
                pass
        parsed.append({"ts": ts, "author": author, "content": content})

    if not parsed:
        return

    parsed.sort(key=lambda m: m["ts"])
    window = 600  # 10 minutes
    group: List[dict] = []
    group_start = parsed[0]["ts"]

    def _emit(g: List[dict]) -> dict:
        lines = [f"[{m['author']}] {m['content']}" for m in g]
        created = ""
        if g[0]["ts"]:
            import datetime
            created = datetime.datetime.fromtimestamp(g[0]["ts"]).isoformat()
        return {
            "text": "\n".join(lines),
            "source": f"{guild_name}#{channel_name}" if guild_name else channel_name,
            "created": created,
            "format": "discord",
            "channel_type": channel_type,
        }

    for msg in parsed:
        if msg["ts"] - group_start > window and group:
            yield _emit(group)
            group = []
            group_start = msg["ts"]
        group.append(msg)

    if group:
        yield _emit(group)


# ---------------------------------------------------------------------------
# Telegram export parser
# ---------------------------------------------------------------------------

def _parse_telegram_export(data: Any) -> Iterator[dict]:
    """Parse Telegram export JSON (result.json from Telegram Desktop).

    Structure:
    {
      "name": "Chat Name",
      "type": "personal_chat" | "private_group" | "private_supergroup" | "public_channel",
      "messages": [
        {
          "id": 123, "type": "message", "date": "2024-01-01T10:00:00",
          "from": "Alice", "from_id": "user123",
          "text": "Hello!" | [{"type": "plain", "text": "Hello"}, ...]
        }
      ]
    }
    """
    if not isinstance(data, dict):
        return

    chat_name = data.get("name", "")
    chat_type = data.get("type", "")
    messages = data.get("messages", [])

    def _extract_text(text_obj: Any) -> str:
        """Telegram text can be a plain string or a list of text entities."""
        if isinstance(text_obj, str):
            return text_obj
        if isinstance(text_obj, list):
            parts = []
            for part in text_obj:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    parts.append(part.get("text", ""))
            return "".join(parts)
        return ""

    # Group into 15-min conversation windows
    parsed: List[dict] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("type") != "message":
            continue
        text = _extract_text(msg.get("text", ""))
        if not text.strip():
            continue
        sender = msg.get("from") or msg.get("actor") or "user"
        date_str = msg.get("date", "")
        ts = 0.0
        if date_str:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(date_str)
                ts = dt.timestamp()
            except Exception:
                pass
        parsed.append({"ts": ts, "from": sender, "text": text.strip()})

    if not parsed:
        return

    parsed.sort(key=lambda m: m["ts"])
    window = 900  # 15 minutes
    group: List[dict] = []
    group_start = parsed[0]["ts"]

    def _emit_tg(g: List[dict]) -> dict:
        lines = [f"[{m['from']}] {m['text']}" for m in g]
        created = ""
        if g[0]["ts"]:
            import datetime
            created = datetime.datetime.fromtimestamp(g[0]["ts"]).isoformat()
        return {
            "text": "\n".join(lines),
            "source": chat_name,
            "created": created,
            "format": "telegram",
            "chat_type": chat_type,
        }

    for msg in parsed:
        if msg["ts"] - group_start > window and group:
            yield _emit_tg(group)
            group = []
            group_start = msg["ts"]
        group.append(msg)

    if group:
        yield _emit_tg(group)


# ---------------------------------------------------------------------------
# OpenClaw session/log parser
# ---------------------------------------------------------------------------

def _parse_openclaw_session(data: Any) -> Iterator[dict]:
    """Parse OpenClaw session logs and agent memory files.

    Handles multiple OpenClaw formats:

    1. Session JSONL/JSON — cron execution logs:
       {"ts": ..., "job": "...", "output": "...", "status": "..."}

    2. Agent summary JSON — produced by forge-* crons:
       {"summary": "...", "decisions": [...], "learnings": [...], "session_id": "..."}

    3. Memory snapshot JSON — agent state dumps:
       {"memories": [{"content": "...", "tags": [...]}]}

    4. Plain text / markdown session output (handled by mine_file)
    """
    if isinstance(data, list):
        # Could be JSONL array or batch of sessions
        for item in data:
            if isinstance(item, dict):
                yield from _parse_openclaw_session(item)
        return

    if not isinstance(data, dict):
        return

    # Format 1: cron job execution log
    if "job" in data and ("output" in data or "result" in data):
        job = data.get("job", "")
        output = data.get("output") or data.get("result") or ""
        status = data.get("status", "")
        ts = data.get("ts") or data.get("timestamp") or ""
        if isinstance(output, dict):
            output = json.dumps(output)
        if output and str(output).strip():
            created = ""
            if ts:
                try:
                    import datetime
                    if isinstance(ts, (int, float)):
                        created = datetime.datetime.fromtimestamp(ts).isoformat()
                    else:
                        created = str(ts)
                except Exception:
                    pass
            yield {
                "text": f"[{job}] {status}\n{output}".strip(),
                "source": f"openclaw/{job}",
                "created": created,
                "format": "openclaw",
            }
        return

    # Format 2: agent summary
    if "summary" in data or "learnings" in data or "decisions" in data:
        parts: List[str] = []
        if data.get("summary"):
            parts.append(str(data["summary"]))
        for field_name in ("learnings", "decisions", "insights", "actions"):
            items_field = data.get(field_name, [])
            if isinstance(items_field, list) and items_field:
                parts.append(f"\n{field_name.title()}:")
                for item in items_field:
                    parts.append(f"- {item}")
            elif isinstance(items_field, str) and items_field:
                parts.append(f"{field_name.title()}: {items_field}")
        text = "\n".join(parts).strip()
        if text:
            yield {
                "text": text,
                "source": data.get("session_id") or data.get("agent") or "openclaw",
                "created": data.get("timestamp") or data.get("ts") or "",
                "format": "openclaw",
            }
        return

    # Format 3: memory snapshot
    if "memories" in data:
        for mem_item in data.get("memories", []):
            if isinstance(mem_item, dict) and mem_item.get("content"):
                yield {
                    "text": str(mem_item["content"]),
                    "source": "openclaw/memory-snapshot",
                    "created": "",
                    "format": "openclaw",
                    "_tags": mem_item.get("tags", []),
                }
        return

    # Format 4: generic key-value agent state
    # Try to extract any meaningful text fields
    for key in ("content", "text", "message", "output", "result", "note"):
        val = data.get(key)
        if val and isinstance(val, str) and len(val.strip()) > 20:
            yield {
                "text": val.strip(),
                "source": f"openclaw/{key}",
                "created": data.get("ts") or data.get("timestamp") or "",
                "format": "openclaw",
            }
            return


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
    ) -> None:
        self._memos = memos
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._dry_run = dry_run
        self._extra_tags = extra_tags or []
        self._batch_size = batch_size
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
    ) -> MineResult:
        """Chunk text and store each chunk."""
        result = MineResult()
        chunks = chunk_text(text, size=self._chunk_size, overlap=self._chunk_overlap)

        batch: List[tuple[str, List[str], float]] = []

        for chunk in chunks:
            if len(chunk.strip()) < 20:
                result.skipped_empty += 1
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
                self._memos.learn(content, tags=tags, importance=importance)
                result.imported += 1
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
    ) -> MineResult:
        """Mine a single text/markdown/code file."""
        path = Path(path).expanduser()
        result = MineResult()

        if not path.exists():
            result.errors.append(f"Not found: {path}")
            return result

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            result.errors.append(f"Read error {path}: {exc}")
            return result

        base_tags = list(tags or [])
        base_tags += detect_room(path, text)

        result.merge(self._mine_chunks(text, base_tags, source_path=path, importance=importance))
        return result

    def mine_directory(
        self,
        directory: str | Path,
        tags: Optional[List[str]] = None,
        extensions: Optional[set] = None,
        importance: float = 0.5,
        max_files: int = 500,
    ) -> MineResult:
        """Mine all files in a directory recursively."""
        directory = Path(directory).expanduser()
        result = MineResult()

        if not directory.is_dir():
            result.errors.append(f"Not a directory: {directory}")
            return result

        files = list(iter_files(directory, extensions=extensions, max_files=max_files))
        for f in files:
            r = self.mine_file(f, tags=tags, importance=importance)
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
