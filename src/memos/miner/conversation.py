"""Conversation miner — parse generic conversation transcripts with speaker attribution.

Supports common formats:
- `Speaker: message` (plain colon separator)
- `[HH:MM] Speaker: message` (timestamp + speaker)
- `[HH:MM:SS] Speaker: message`
- `**Speaker:** message` (markdown bold)
- `## Speaker` heading + following lines (until next heading)

Each detected turn is attributed to its speaker. When `per_speaker=True`, each
speaker's turns are stored in a separate namespace (`{namespace_prefix}:{speaker}`),
enabling scoped recall per agent/person.

Usage:
    from memos.miner.conversation import ConversationMiner, parse_conversation

    # Low-level: parse a file into speaker-tagged turns
    turns = parse_conversation("meeting.txt")

    # High-level: mine into MemOS with per-speaker namespaces
    miner = ConversationMiner(memos)
    result = miner.mine_conversation("meeting.txt", per_speaker=True)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, List, Optional


# ---------------------------------------------------------------------------
# Turn data structure
# ---------------------------------------------------------------------------

@dataclass
class ConversationTurn:
    """A single speaker turn in a conversation."""
    speaker: str
    content: str
    timestamp: str = ""
    line_number: int = 0

    def __str__(self) -> str:
        ts = f"[{self.timestamp}] " if self.timestamp else ""
        return f"{ts}{self.speaker}: {self.content}"


@dataclass
class ConversationResult:
    """Result of mining a conversation file."""
    imported: int = 0
    skipped_empty: int = 0
    skipped_duplicates: int = 0
    errors: List[str] = field(default_factory=list)
    speakers_detected: List[str] = field(default_factory=list)
    turns_total: int = 0
    memory_ids: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"ConversationResult(imported={self.imported}, "
            f"speakers={len(self.speakers_detected)}, "
            f"turns={self.turns_total}, "
            f"errors={len(self.errors)})"
        )

    def merge(self, other: ConversationResult) -> None:
        self.imported += other.imported
        self.skipped_empty += other.skipped_empty
        self.skipped_duplicates += other.skipped_duplicates
        self.errors.extend(other.errors)
        self.turns_total += other.turns_total
        self.memory_ids.extend(other.memory_ids)
        for s in other.speakers_detected:
            if s not in self.speakers_detected:
                self.speakers_detected.append(s)


# ---------------------------------------------------------------------------
# Speaker detection patterns
# ---------------------------------------------------------------------------

# Pattern 1: [HH:MM] Speaker: message  or  [HH:MM:SS] Speaker: message
_RE_TIMESTAMP_SPEAKER = re.compile(
    r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.+?)[:\uff1a]\s*(.+)$"
)

# Pattern 2: Speaker: message (plain colon, speaker is word chars + spaces)
_RE_PLAIN_SPEAKER = re.compile(
    r"^([A-Za-z\u00C0-\u024F\u0400-\u04FF\u4e00-\u9fff][\w.\-\s\u00C0-\u024F\u0400-\u04FF\u4e00-\u9fff]{0,30}?)[\s]*[:\uff1a]\s*(.+)$"
)

# Pattern 3: **Speaker:** message (markdown bold)
_RE_BOLD_SPEAKER = re.compile(
    r"^\*{1,2}([^*]+)\*{1,2}[\s]*[:\uff1a]?\s*(.+)$"
)

# Pattern 4: ## Speaker heading
_RE_HEADING_SPEAKER = re.compile(
    r"^#{1,3}\s+(.+?)\s*$"
)

# Normalize speaker name
_RE_NORMALIZE = re.compile(r"[^\w.\-\u00C0-\u024F\u0400-\u04FF\u4e00-\u9fff]")


def _normalize_speaker(name: str) -> str:
    """Normalize a speaker name to a consistent form."""
    name = name.strip()
    # Remove trailing colon or bold markers
    name = name.rstrip(":：*")
    name = name.strip()
    # Collapse internal whitespace
    name = re.sub(r"\s+", " ", name)
    return name


def _slug_speaker(name: str) -> str:
    """Create a filesystem-safe slug from a speaker name for namespace use."""
    slug = _RE_NORMALIZE.sub("_", name.lower().strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:40] if slug else "unknown"


# ---------------------------------------------------------------------------
# Turn parser
# ---------------------------------------------------------------------------

def parse_conversation(text: str) -> List[ConversationTurn]:
    """Parse a conversation text into speaker-attributed turns.

    Tries multiple patterns in order:
    1. [timestamp] Speaker: message
    2. **Speaker:** message (markdown bold)
    3. Speaker: message (plain colon)
    4. ## Speaker heading (accumulates until next heading)

    Returns a list of ConversationTurn objects.
    """
    turns: List[ConversationTurn] = []
    lines = text.splitlines()
    current_heading_speaker: Optional[str] = None
    current_heading_lines: List[str] = []
    current_heading_start: int = 0

    def _flush_heading() -> None:
        nonlocal current_heading_speaker, current_heading_lines, current_heading_start
        if current_heading_speaker and current_heading_lines:
            content = "\n".join(current_heading_lines).strip()
            if content:
                turns.append(ConversationTurn(
                    speaker=current_heading_speaker,
                    content=content,
                    line_number=current_heading_start,
                ))
        current_heading_speaker = None
        current_heading_lines = []
        current_heading_start = 0

    for i, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        stripped = line.strip()

        # Skip empty lines (but flush heading accumulator)
        if not stripped:
            if current_heading_speaker:
                current_heading_lines.append("")
            continue

        # Try pattern 1: [timestamp] Speaker: message
        m = _RE_TIMESTAMP_SPEAKER.match(stripped)
        if m:
            _flush_heading()
            ts, speaker, content = m.group(1), _normalize_speaker(m.group(2)), m.group(3).strip()
            if content:
                turns.append(ConversationTurn(
                    speaker=speaker, content=content, timestamp=ts, line_number=i,
                ))
            continue

        # Try pattern 3: **Speaker:** message (markdown bold)
        m = _RE_BOLD_SPEAKER.match(stripped)
        if m:
            _flush_heading()
            speaker = _normalize_speaker(m.group(1))
            content = m.group(2).strip()
            if content:
                turns.append(ConversationTurn(
                    speaker=speaker, content=content, line_number=i,
                ))
            continue

        # Try pattern 4: ## Speaker heading
        m = _RE_HEADING_SPEAKER.match(stripped)
        if m:
            _flush_heading()
            current_heading_speaker = _normalize_speaker(m.group(1))
            current_heading_start = i
            continue

        # Try pattern 2: Speaker: message (plain colon)
        m = _RE_PLAIN_SPEAKER.match(stripped)
        if m:
            _flush_heading()
            speaker = _normalize_speaker(m.group(1))
            content = m.group(2).strip()
            # Heuristic: skip if "speaker" looks like a list marker or is too short
            if content and len(speaker) >= 2 and not re.match(r"^[\d\.\-\*]+$", speaker):
                turns.append(ConversationTurn(
                    speaker=speaker, content=content, line_number=i,
                ))
                continue

        # Continuation line under a heading
        if current_heading_speaker:
            current_heading_lines.append(stripped)
            continue

        # Fallback: no speaker detected, skip the line
        # (unattributed text is not stored to avoid polluting namespaces)

    _flush_heading()
    return turns


def parse_conversation_file(path: str | Path) -> List[ConversationTurn]:
    """Parse a conversation file into turns."""
    path = Path(path).expanduser()
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    return parse_conversation(text)


# ---------------------------------------------------------------------------
# Speaker-aware miner
# ---------------------------------------------------------------------------

class ConversationMiner:
    """Mine conversation files into MemOS with per-speaker attribution.

    Args:
        memos: A MemOS instance.
        namespace_prefix: Prefix for per-speaker namespaces (default "conv").
        per_speaker: If True, each speaker gets their own namespace.
        extra_tags: Additional tags to apply to all memories.
        dry_run: If True, don't actually store memories.
    """

    def __init__(
        self,
        memos: Any,
        namespace_prefix: str = "conv",
        per_speaker: bool = True,
        extra_tags: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> None:
        self._memos = memos
        self._namespace_prefix = namespace_prefix
        self._per_speaker = per_speaker
        self._extra_tags = extra_tags or []
        self._dry_run = dry_run
        self._seen_hashes: set[str] = set()

    @staticmethod
    def _content_hash(text: str) -> str:
        import hashlib
        normalized = re.sub(r"\s+", " ", text.lower().strip())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _is_duplicate(self, text: str) -> bool:
        h = self._content_hash(text)
        if h in self._seen_hashes:
            return True
        self._seen_hashes.add(h)
        return False

    def mine_conversation(
        self,
        path: str | Path,
        tags: Optional[List[str]] = None,
        importance: float = 0.55,
        per_speaker: Optional[bool] = None,
    ) -> ConversationResult:
        """Mine a conversation file with speaker attribution.

        Args:
            path: Path to the conversation file.
            tags: Extra tags to add.
            importance: Default importance for stored memories.
            per_speaker: Override per-speaker setting.

        Returns:
            ConversationResult with stats.
        """
        path = Path(path).expanduser()
        result = ConversationResult()

        if not path.exists():
            result.errors.append(f"Not found: {path}")
            return result

        turns = parse_conversation_file(path)
        result.turns_total = len(turns)

        if not turns:
            result.errors.append(f"No turns detected in {path}")
            return result

        # Detect date from filename if possible (YYYY-MM-DD pattern)
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.stem)
        date_tag = f"date:{date_match.group(1)}" if date_match else ""

        use_per_speaker = per_speaker if per_speaker is not None else self._per_speaker

        # Group turns by speaker
        speakers: dict[str, List[ConversationTurn]] = {}
        for turn in turns:
            speakers.setdefault(turn.speaker, []).append(turn)

        result.speakers_detected = sorted(speakers.keys())

        for speaker, speaker_turns in speakers.items():
            speaker_slug = _slug_speaker(speaker)

            # Build tags
            turn_tags = list(tags or [])
            turn_tags.append(f"speaker:{speaker_slug}")
            turn_tags.append("conversation")
            if date_tag:
                turn_tags.append(date_tag)
            for t in self._extra_tags:
                if t not in turn_tags:
                    turn_tags.append(t)

            # Build content for this speaker's turns
            # Group consecutive turns into chunks to avoid tiny memories
            chunks = self._chunk_turns(speaker_turns)
            for chunk_content in chunks:
                if len(chunk_content.strip()) < 5:
                    result.skipped_empty += 1
                    continue

                if self._is_duplicate(chunk_content):
                    result.skipped_duplicates += 1
                    continue

                if self._dry_run:
                    result.imported += 1
                    continue

                try:
                    # Switch namespace for per-speaker isolation
                    saved_ns = self._memos.namespace
                    if use_per_speaker:
                        self._memos.namespace = f"{self._namespace_prefix}:{speaker_slug}"

                    try:
                        item = self._memos.learn(
                            chunk_content,
                            tags=turn_tags,
                            importance=importance,
                        )
                    finally:
                        # Always restore original namespace
                        self._memos.namespace = saved_ns

                    result.imported += 1
                    if item is not None:
                        result.memory_ids.append(item.id)
                except Exception as exc:
                    result.errors.append(f"Speaker {speaker}: {exc}")

        return result

    @staticmethod
    def _chunk_turns(
        turns: List[ConversationTurn],
        max_chars: int = 800,
    ) -> List[str]:
        """Group consecutive turns into chunks of max_chars.

        Keeps turns from the same speaker together; splits when the chunk
        would exceed max_chars.
        """
        if not turns:
            return []

        chunks: List[str] = []
        current_parts: List[str] = []
        current_len = 0

        for turn in turns:
            turn_text = str(turn)
            turn_len = len(turn_text)

            if current_len + turn_len + 2 > max_chars and current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_len = 0

            current_parts.append(turn_text)
            current_len += turn_len + 2

        if current_parts:
            chunks.append("\n\n".join(current_parts))

        return [c for c in chunks if c.strip()]
