"""Tests for P23 — ConversationMiner (speaker-attributed transcript ingestion)."""

from __future__ import annotations

import json
import textwrap
>>>>>>> fa8bf8a (feat(P23): Speaker Ownership — conversation miner with per-speaker namespaces (v0.38.0))
from pathlib import Path

import pytest

from memos.ingest.conversation import (
    ConversationMiner,
    ConversationMineResult,
    Turn,
    _slug,
    parse_transcript,
>>>>>>> fa8bf8a (feat(P23): Speaker Ownership — conversation miner with per-speaker namespaces (v0.38.0))
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeMemory:
    def __init__(self, id: str, content: str, tags: list):
        self.id = id
        self.content = content
        self.tags = tags


class _FakeMemos:
    """Minimal MemOS stub that records learn() calls."""

    def __init__(self):
        self._stored: list[dict] = []
        self.namespace: str = ""

    def learn(self, content: str, tags=None, importance: float = 0.5, **kw) -> _FakeMemory:
        mem = _FakeMemory(id=f"id{len(self._stored)}", content=content, tags=tags or [])
        self._stored.append({
            "content": content,
            "tags": list(tags or []),
            "namespace": self.namespace,
            "importance": importance,
        })
        return mem


# ---------------------------------------------------------------------------
# parse_transcript tests
# ---------------------------------------------------------------------------

def test_parse_plain_format():
    text = textwrap.dedent("""\
        Alice: Hello there!
        Bob: Hi Alice, how are you?
        Alice: I'm doing great, thanks.
    """)
    turns, date = parse_transcript(text)
    assert len(turns) == 3
    assert turns[0].speaker == "Alice"
    assert turns[0].text == "Hello there!"
    assert turns[1].speaker == "Bob"
    assert turns[2].speaker == "Alice"
    assert date is None


def test_parse_timestamped_format():
    text = textwrap.dedent("""\
        [09:15] Alice: Good morning.
        [09:16] Bob: Morning! Ready to start?
        [09:17] Alice: Yes, let's go.
    """)
    turns, date = parse_transcript(text)
    assert len(turns) == 3
    assert turns[0].speaker == "Alice"
    assert turns[1].speaker == "Bob"


def test_parse_bold_markdown_format():
    text = textwrap.dedent("""\
        **Alice:** Welcome to the meeting.
        **Bob:** Thanks for having me.
        **Alice:** Let's start with the agenda.
    """)
    turns, date = parse_transcript(text)
    assert len(turns) == 3
    assert turns[0].speaker == "Alice"
    assert "Welcome to the meeting" in turns[0].text
    assert turns[1].speaker == "Bob"


def test_parse_date_extracted_from_header():
    text = textwrap.dedent("""\
        Meeting — 2026-04-09
        Alice: First point.
        Bob: Agreed.
    """)
    turns, date = parse_transcript(text)
    assert date == "2026-04-09"
    assert len(turns) == 2


def test_parse_multiline_turn():
    text = textwrap.dedent("""\
        Alice: This is a long message.
        It continues on the next line.
        Bob: Short reply.
    """)
    turns, date = parse_transcript(text)
    assert len(turns) == 2
    assert "continues on the next line" in turns[0].text


def test_parse_no_turns_returns_empty():
    text = "This is just plain text without any speaker pattern.\n"
    turns, date = parse_transcript(text)
    assert turns == []


def test_parse_mixed_formats():
    """Parse should handle multiple patterns in one file."""
    text = textwrap.dedent("""\
        **Alice:** Hello.
        Bob: Hi there.
        [10:00] Carol: Good morning.
    """)
    turns, date = parse_transcript(text)
    speakers = [t.speaker for t in turns]
    assert "Alice" in speakers
    assert "Bob" in speakers
    assert "Carol" in speakers


# ---------------------------------------------------------------------------
# _slug tests
# ---------------------------------------------------------------------------

def test_slug_basic():
    assert _slug("Alice") == "alice"


def test_slug_spaces_and_special_chars():
    assert _slug("Jean-Luc Picard") == "jean_luc_picard"


def test_slug_max_length():
    long_name = "A" * 50
    assert len(_slug(long_name)) <= 40


# ---------------------------------------------------------------------------
# ConversationMiner — per_speaker mode
# ---------------------------------------------------------------------------

@pytest.fixture
def transcript_file(tmp_path):
    content = textwrap.dedent("""\
        Meeting — 2026-04-09

        Alice: I think we should go with option A.
        Bob: I prefer option B, it is more scalable.
        Alice: Let me explain why option A is better for our use case.
        Bob: Fair enough, let's discuss further.
    """)
    f = tmp_path / "meeting.txt"
    f.write_text(content)
    return f


def test_mine_per_speaker_namespaces(transcript_file):
    memos = _FakeMemos()
    miner = ConversationMiner(memos)
    result = miner.mine_conversation(
        transcript_file,
        namespace_prefix="conv",
        per_speaker=True,
    )

    assert result.imported > 0
    assert "Alice" in result.speakers
    assert "Bob" in result.speakers

    # Memories stored under per-speaker namespaces
    alice_mems = [m for m in memos._stored if m["namespace"] == "conv:alice"]
    bob_mems = [m for m in memos._stored if m["namespace"] == "conv:bob"]
    assert len(alice_mems) > 0
    assert len(bob_mems) > 0


def test_mine_per_speaker_tags(transcript_file):
    memos = _FakeMemos()
    miner = ConversationMiner(memos)
    miner.mine_conversation(transcript_file, per_speaker=True)

    # Each stored memory should have speaker tag + conversation tag
    for mem in memos._stored:
        assert "conversation" in mem["tags"]
        assert any(t.startswith("speaker:") for t in mem["tags"])


def test_mine_per_speaker_date_tag(transcript_file):
    memos = _FakeMemos()
    miner = ConversationMiner(memos)
    miner.mine_conversation(transcript_file, per_speaker=True)

    # Date from header should appear in tags
    assert any("date:2026-04-09" in m["tags"] for m in memos._stored)


def test_mine_per_speaker_namespace_restored(transcript_file):
    memos = _FakeMemos()
    memos.namespace = "original"
    miner = ConversationMiner(memos)
    miner.mine_conversation(transcript_file, per_speaker=True)
    assert memos.namespace == "original"


# ---------------------------------------------------------------------------
# ConversationMiner — combined (non-per-speaker) mode
# ---------------------------------------------------------------------------

def test_mine_combined_single_namespace(transcript_file):
    memos = _FakeMemos()
    miner = ConversationMiner(memos)
    result = miner.mine_conversation(
        transcript_file,
        per_speaker=False,
    )

    assert result.imported > 0
    # All stored in the same namespace (default "")
    namespaces = {m["namespace"] for m in memos._stored}
    assert namespaces == {""}  # original namespace restored


def test_mine_combined_all_speaker_tags(transcript_file):
    memos = _FakeMemos()
    miner = ConversationMiner(memos)
    miner.mine_conversation(transcript_file, per_speaker=False)

    # Every memory has all speaker tags
    for mem in memos._stored:
        assert "speaker:alice" in mem["tags"]
        assert "speaker:bob" in mem["tags"]


def test_mine_combined_speaker_prefix_in_content(transcript_file):
    memos = _FakeMemos()
    miner = ConversationMiner(memos)
    miner.mine_conversation(transcript_file, per_speaker=False)

    # Content should be prefixed with [SpeakerName]
    contents = [m["content"] for m in memos._stored]
    assert any("[Alice]" in c or "[Bob]" in c for c in contents)


# ---------------------------------------------------------------------------
# ConversationMiner — dry run
# ---------------------------------------------------------------------------

def test_mine_dry_run_stores_nothing(transcript_file):
    memos = _FakeMemos()
    miner = ConversationMiner(memos, dry_run=True)
    result = miner.mine_conversation(transcript_file)
    assert result.imported > 0  # counts as "would import"
    assert memos._stored == []  # nothing actually stored


# ---------------------------------------------------------------------------
# ConversationMiner — error handling
# ---------------------------------------------------------------------------

def test_mine_file_not_found():
    memos = _FakeMemos()
    miner = ConversationMiner(memos)
    result = miner.mine_conversation("/nonexistent/path.txt")
    assert result.imported == 0
    assert len(result.errors) == 1
    assert "not found" in result.errors[0].lower()


def test_mine_no_speaker_turns(tmp_path):
    f = tmp_path / "plain.txt"
    f.write_text("This is just a plain text with no speakers.")
    memos = _FakeMemos()
    miner = ConversationMiner(memos)
    result = miner.mine_conversation(f)
    assert result.imported == 0
    assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# ConversationMiner — custom extra tags
# ---------------------------------------------------------------------------

def test_mine_extra_tags_propagated(transcript_file):
    memos = _FakeMemos()
    miner = ConversationMiner(memos)
    miner.mine_conversation(transcript_file, tags=["project:alpha", "q2"])

    for mem in memos._stored:
        assert "project:alpha" in mem["tags"]
        assert "q2" in mem["tags"]


# ---------------------------------------------------------------------------
# ConversationMineResult __str__
# ---------------------------------------------------------------------------

def test_result_str():
    r = ConversationMineResult(imported=5, skipped_duplicates=1, speakers=["Alice", "Bob"])
    s = str(r)
    assert "5" in s
    assert "Alice" in s
>>>>>>> fa8bf8a (feat(P23): Speaker Ownership — conversation miner with per-speaker namespaces (v0.38.0))
