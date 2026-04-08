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

    def mine_auto(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.6,
    ) -> MineResult:
        """Auto-detect format and mine accordingly.

        Detection order:
        1. .jsonl → Slack
        2. .json with Claude structure → Claude
        3. .json with ChatGPT structure → ChatGPT
        4. Directory → mine_directory
        5. Otherwise → mine_file
        """
        path = Path(path).expanduser()

        if path.is_dir():
            return self.mine_directory(path, tags=tags, importance=importance)

        if path.suffix.lower() == ".jsonl":
            return self.mine_slack_export(path, tags=tags, importance=importance)

        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                return self.mine_file(path, tags=tags, importance=importance)

            # Detect Claude: has "messages" with "role": "human"|"assistant"
            if isinstance(data, list) and data and isinstance(data[0], dict):
                if "messages" in data[0] or "chat_messages" in data[0]:
                    return self.mine_claude_export(path, tags=tags, importance=importance)
                # ChatGPT: has "mapping" key
                if "mapping" in data[0]:
                    return self.mine_chatgpt_export(path, tags=tags, importance=importance)
            elif isinstance(data, dict):
                if "messages" in data or "chat_messages" in data:
                    return self.mine_claude_export(path, tags=tags, importance=importance)
                if "mapping" in data:
                    return self.mine_chatgpt_export(path, tags=tags, importance=importance)

        return self.mine_file(path, tags=tags, importance=importance)
