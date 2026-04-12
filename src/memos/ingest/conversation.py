"""Conversation Miner — speaker-aware transcript ingestion for MemOS (P23).

Parses plain-text transcripts with speaker attribution in common formats:
  - ``Speaker: message``
  - ``[HH:MM] Speaker: message``  /  ``[HH:MM:SS] Speaker: message``
  - ``**Speaker:** message``  (Markdown bold)

When ``per_speaker=True`` (default), each speaker's lines are stored under a
dedicated namespace (``{namespace_prefix}:{speaker_slug}``) so recall can be
scoped per speaker.  Auto-tags added to every memory:
  ``speaker:{name}``, ``conversation``, ``date:{YYYY-MM-DD}``

Usage::

    from memos.ingest.conversation import ConversationMiner
    miner = ConversationMiner(memos)
    result = miner.mine_conversation("transcript.txt", per_speaker=True)
    print(result)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ConversationMineResult:
    imported: int = 0
    skipped_duplicates: int = 0
    skipped_empty: int = 0
    errors: List[str] = field(default_factory=list)
    speakers: List[str] = field(default_factory=list)  # detected speakers

    def __str__(self) -> str:
        return (
            f"ConversationMineResult(imported={self.imported}, "
            f"dupes={self.skipped_duplicates}, "
            f"empty={self.skipped_empty}, "
            f"speakers={self.speakers}, "
            f"errors={len(self.errors)})"
        )


# ---------------------------------------------------------------------------
# Transcript parser
# ---------------------------------------------------------------------------

# [HH:MM] or [HH:MM:SS] optional timestamp prefix
_TS_PREFIX = r"(?:\[[\d]{1,2}:[\d]{2}(?::[\d]{2})?\]\s*)?"

# Speaker name: starts with letter, up to 40 chars (letters, digits, space, hyphen, underscore, dot)
_SPEAKER_PAT = r"([A-Za-z\u00C0-\u024F\u0400-\u04FF\u4e00-\u9fff][A-Za-z0-9\u00C0-\u024F\u0400-\u04FF\u4e00-\u9fff _\-\.]{0,39})"

# Pattern 1: [HH:MM] Speaker: message
_RE_PLAIN = re.compile(
    r"^" + _TS_PREFIX + _SPEAKER_PAT + r":\s+(.+)$"
)

# Pattern 2: **Speaker:** message  (Markdown bold)
_RE_BOLD = re.compile(
    r"^\*\*" + _SPEAKER_PAT + r":\*\*\s+(.+)$"
)

# Date-only line detector (to extract conversation date)
_RE_DATE_LINE = re.compile(
    r"(\d{4}-\d{2}-\d{2})"
)


def _slug(name: str) -> str:
    """Convert speaker name to safe namespace/tag slug."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower().strip())[:40].strip("_")


@dataclass
class Turn:
    speaker: str
    text: str
    line_no: int


def parse_transcript(text: str) -> Tuple[List[Turn], Optional[str]]:
    """Parse a transcript into speaker turns.

    Returns:
        turns: ordered list of Turn objects
        date_str: ISO date (YYYY-MM-DD) found in transcript header, or None
    """
    turns: List[Turn] = []
    date_str: Optional[str] = None
    current_speaker: Optional[str] = None
    current_lines: List[str] = []

    def _flush(speaker: str, lines: List[str], line_no: int) -> None:
        text = " ".join(lines).strip()
        if text:
            turns.append(Turn(speaker=speaker, text=text, line_no=line_no))

    for i, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()

        # Try to find a date in header lines (first 10 lines)
        if date_str is None and i < 10:
            m = _RE_DATE_LINE.search(line)
            if m:
                date_str = m.group(1)

        # Try bold pattern first (more specific)
        m_bold = _RE_BOLD.match(line)
        if m_bold:
            if current_speaker is not None:
                _flush(current_speaker, current_lines, i)
            current_speaker = m_bold.group(1).strip()
            current_lines = [m_bold.group(2).strip()]
            continue

        # Try plain / timestamped pattern
        m_plain = _RE_PLAIN.match(line)
        if m_plain:
            if current_speaker is not None:
                _flush(current_speaker, current_lines, i)
            current_speaker = m_plain.group(1).strip()
            current_lines = [m_plain.group(2).strip()]
            continue

        # Continuation line
        if current_speaker is not None and line:
            current_lines.append(line)

    # Flush last speaker
    if current_speaker is not None:
        _flush(current_speaker, current_lines, len(text.splitlines()))

    return turns, date_str


# ---------------------------------------------------------------------------
# ConversationMiner
# ---------------------------------------------------------------------------

class ConversationMiner:
    """Mine speaker-attributed transcripts into MemOS.

    Args:
        memos: MemOS instance
        chunk_size: max chars per stored memory chunk (default 800)
        dry_run: if True, don't store anything
        min_turn_len: minimum chars per turn to store (default 20)
    """

    def __init__(
        self,
        memos: Any,
        chunk_size: int = 800,
        dry_run: bool = False,
        min_turn_len: int = 20,
    ) -> None:
        self._memos = memos
        self._chunk_size = chunk_size
        self._dry_run = dry_run
        self._min_turn_len = min_turn_len
        self._seen_hashes: set[str] = set()

    def _content_hash(self, text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _is_duplicate(self, text: str) -> bool:
        h = self._content_hash(text)
        if h in self._seen_hashes:
            return True
        self._seen_hashes.add(h)
        return False

    def _chunk_turn(self, text: str) -> List[str]:
        """Split a long turn into sub-chunks of at most chunk_size chars."""
        if len(text) <= self._chunk_size:
            return [text]
        chunks = []
        while text:
            chunks.append(text[: self._chunk_size])
            text = text[self._chunk_size :]
        return chunks

    def mine_conversation(
        self,
        path: str | Path,
        namespace_prefix: str = "conv",
        per_speaker: bool = True,
        tags: Optional[List[str]] = None,
        importance: float = 0.6,
    ) -> ConversationMineResult:
        """Parse a transcript file and ingest it into MemOS.

        Args:
            path: Path to the transcript text file.
            namespace_prefix: Prefix for per-speaker namespaces.
                              Final namespace = ``{namespace_prefix}:{speaker_slug}``.
                              Ignored when ``per_speaker=False``.
            per_speaker: When True, store each speaker's turns under a
                         dedicated namespace so recall can be scoped.
            tags: Extra tags to attach to every memory.
            importance: Base importance score (default 0.6).

        Returns:
            ConversationMineResult with import stats.
        """
        path = Path(path).expanduser().resolve()
        result = ConversationMineResult()

        if not path.exists():
            result.errors.append(f"File not found: {path}")
            return result

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            result.errors.append(f"Read error {path}: {exc}")
            return result

        turns, date_str = parse_transcript(text)

        if not turns:
            result.errors.append(f"No speaker turns found in {path}")
            return result

        # Collect unique speakers
        all_speakers = list(dict.fromkeys(t.speaker for t in turns))
        result.speakers = all_speakers

        # Build base tags
        base_tags = list(tags or []) + ["conversation"]
        if date_str:
            base_tags.append(f"date:{date_str}")

        # Save original namespace so we can restore it
        original_ns = getattr(self._memos, "namespace", "")

        try:
            if per_speaker:
                # Group turns by speaker and store under per-speaker namespaces
                by_speaker: Dict[str, List[str]] = {s: [] for s in all_speakers}
                for turn in turns:
                    by_speaker[turn.speaker].append(turn.text)

                for speaker, messages in by_speaker.items():
                    speaker_slug = _slug(speaker)
                    ns = f"{namespace_prefix}:{speaker_slug}"
                    speaker_tags = list(base_tags) + [f"speaker:{speaker_slug}"]

                    if not self._dry_run:
                        self._memos.namespace = ns

                    for msg in messages:
                        msg = msg.strip()
                        if len(msg) < self._min_turn_len:
                            result.skipped_empty += 1
                            continue
                        for chunk in self._chunk_turn(msg):
                            if self._is_duplicate(chunk):
                                result.skipped_duplicates += 1
                                continue
                            if not self._dry_run:
                                try:
                                    self._memos.learn(
                                        chunk,
                                        tags=speaker_tags,
                                        importance=importance,
                                    )
                                    result.imported += 1
                                except Exception as exc:
                                    result.errors.append(str(exc))
                            else:
                                result.imported += 1
            else:
                # All turns in the same namespace, tag all speakers
                if not self._dry_run:
                    self._memos.namespace = original_ns

                all_speaker_tags = [f"speaker:{_slug(s)}" for s in all_speakers]
                combined_tags = list(base_tags) + all_speaker_tags

                for turn in turns:
                    msg = turn.text.strip()
                    if len(msg) < self._min_turn_len:
                        result.skipped_empty += 1
                        continue
                    # Prefix with speaker name for context
                    content = f"[{turn.speaker}] {msg}"
                    for chunk in self._chunk_turn(content):
                        if self._is_duplicate(chunk):
                            result.skipped_duplicates += 1
                            continue
                        if not self._dry_run:
                            try:
                                self._memos.learn(
                                    chunk,
                                    tags=combined_tags,
                                    importance=importance,
                                )
                                result.imported += 1
                            except Exception as exc:
                                result.errors.append(str(exc))
                        else:
                            result.imported += 1
        finally:
            # Always restore original namespace
            if not self._dry_run:
                self._memos.namespace = original_ns

        return result
