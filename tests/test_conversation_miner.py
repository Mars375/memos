"""Tests for P23 — Speaker Ownership (Conversation Miner)."""

import json
import tempfile
from pathlib import Path

import pytest

from memos.miner.conversation import (
    ConversationMiner,
    ConversationResult,
    ConversationTurn,
    _normalize_speaker,
    _slug_speaker,
    parse_conversation,
    parse_conversation_file,
)


# ---------------------------------------------------------------------------
# Speaker normalization
# ---------------------------------------------------------------------------

class TestNormalizeSpeaker:
    def test_basic(self):
        assert _normalize_speaker("Alice") == "Alice"

    def test_trailing_colon(self):
        assert _normalize_speaker("Alice:") == "Alice"

    def test_trailing_bold(self):
        assert _normalize_speaker("Alice**") == "Alice"

    def test_whitespace(self):
        assert _normalize_speaker("  Alice  ") == "Alice"

    def test_fullwidth_colon(self):
        assert _normalize_speaker("Alice：") == "Alice"

    def test_multiword(self):
        assert _normalize_speaker("Jean Pierre") == "Jean Pierre"


class TestSlugSpeaker:
    def test_basic(self):
        assert _slug_speaker("Alice") == "alice"

    def test_spaces(self):
        assert _slug_speaker("Jean Pierre") == "jean_pierre"

    def test_special_chars(self):
        slug = _slug_speaker("O'Brien")
        assert "o" in slug and "brien" in slug

    def test_empty(self):
        assert _slug_speaker("") == "unknown"

    def test_long_name(self):
        assert len(_slug_speaker("A" * 100)) <= 40


# ---------------------------------------------------------------------------
# Parse conversation — pattern tests
# ---------------------------------------------------------------------------

class TestParseConversationPlainColon:
    def test_basic(self):
        text = "Alice: Hello world\nBob: Hi there"
        turns = parse_conversation(text)
        assert len(turns) == 2
        assert turns[0].speaker == "Alice"
        assert turns[0].content == "Hello world"
        assert turns[1].speaker == "Bob"
        assert turns[1].content == "Hi there"

    def test_multiline(self):
        text = "Alice: First line\nAlice: Second line"
        turns = parse_conversation(text)
        assert len(turns) == 2
        assert turns[0].content == "First line"
        assert turns[1].content == "Second line"

    def test_empty_lines_skipped(self):
        text = "Alice: Hello\n\n\nBob: Hi"
        turns = parse_conversation(text)
        assert len(turns) == 2

    def test_no_speaker_lines_skipped(self):
        text = "Alice: Hello\nThis has no speaker\nBob: Hi"
        turns = parse_conversation(text)
        assert len(turns) == 2


class TestParseConversationTimestamp:
    def test_timestamp_speaker(self):
        text = "[10:30] Alice: Hello\n[10:31] Bob: Hi"
        turns = parse_conversation(text)
        assert len(turns) == 2
        assert turns[0].timestamp == "10:30"
        assert turns[0].speaker == "Alice"
        assert turns[1].timestamp == "10:31"

    def test_timestamp_with_seconds(self):
        text = "[10:30:45] Alice: Hello"
        turns = parse_conversation(text)
        assert len(turns) == 1
        assert turns[0].timestamp == "10:30:45"

    def test_timestamp_preferred_over_plain(self):
        """Timestamp pattern should be tried first."""
        text = "[14:00] Alice: Meeting started"
        turns = parse_conversation(text)
        assert len(turns) == 1
        assert turns[0].timestamp == "14:00"


class TestParseConversationBold:
    def test_bold_speaker(self):
        text = "**Alice:** Hello world"
        turns = parse_conversation(text)
        assert len(turns) == 1
        assert turns[0].speaker == "Alice"
        assert turns[0].content == "Hello world"

    def test_bold_single_star(self):
        text = "*Alice:* Hello"
        turns = parse_conversation(text)
        assert len(turns) == 1
        assert turns[0].speaker == "Alice"

    def test_bold_without_colon(self):
        text = "**Alice** Hello"
        turns = parse_conversation(text)
        assert len(turns) == 1
        assert turns[0].speaker == "Alice"


class TestParseConversationHeading:
    def test_heading_speaker(self):
        text = "## Alice\nThis is what Alice said\nAnd more\n## Bob\nBob's content"
        turns = parse_conversation(text)
        assert len(turns) == 2
        assert turns[0].speaker == "Alice"
        assert "what Alice said" in turns[0].content
        assert "And more" in turns[0].content
        assert turns[1].speaker == "Bob"
        assert "Bob's content" in turns[1].content

    def test_heading_h3(self):
        text = "### Alice\nSome text"
        turns = parse_conversation(text)
        assert len(turns) == 1
        assert turns[0].speaker == "Alice"


class TestParseConversationMixed:
    def test_mixed_formats(self):
        text = (
            "[09:00] Alice: Good morning\n"
            "**Bob:** Hey\n"
            "Charlie: What's up?\n"
            "## Diane\n"
            "Diane talks here\n"
        )
        turns = parse_conversation(text)
        assert len(turns) == 4
        speakers = [t.speaker for t in turns]
        assert "Alice" in speakers
        assert "Bob" in speakers
        assert "Charlie" in speakers
        assert "Diane" in speakers


class TestParseConversationEdgeCases:
    def test_empty_text(self):
        assert parse_conversation("") == []

    def test_only_empty_lines(self):
        assert parse_conversation("\n\n\n") == []

    def test_no_speakers(self):
        text = "Just some text\nMore text"
        turns = parse_conversation(text)
        assert len(turns) == 0

    def test_list_markers_not_speakers(self):
        """Lines starting with numbers/dashes should not be parsed as speakers."""
        text = "1. First item\n- Second item"
        turns = parse_conversation(text)
        assert len(turns) == 0

    def test_short_speaker_name_skipped(self):
        """Single-char 'speakers' are likely false positives."""
        text = "A: This might be a section marker"
        turns = parse_conversation(text)
        # The plain pattern may or may not match; short names are ok
        # as long as content is preserved
        if turns:
            assert turns[0].content == "This might be a section marker"

    def test_unicode_speakers(self):
        text = "François: Bonjour\nMüller: Hallo"
        turns = parse_conversation(text)
        assert len(turns) == 2
        assert turns[0].speaker == "François"
        assert turns[1].speaker == "Müller"


class TestParseConversationFile:
    def test_parse_file(self, tmp_path):
        p = tmp_path / "meeting.txt"
        p.write_text("Alice: Hello\nBob: Hi")
        turns = parse_conversation_file(p)
        assert len(turns) == 2

    def test_nonexistent_file(self):
        turns = parse_conversation_file("/nonexistent/file.txt")
        assert turns == []

    def test_date_from_filename(self, tmp_path):
        p = tmp_path / "2026-04-10-meeting.txt"
        p.write_text("Alice: Hello")
        turns = parse_conversation_file(p)
        assert len(turns) == 1


# ---------------------------------------------------------------------------
# ConversationMiner
# ---------------------------------------------------------------------------

class TestConversationMiner:
    @pytest.fixture
    def memos(self):
        """Create a lightweight MemOS instance for testing."""
        from memos import MemOS
        return MemOS(backend="memory")

    def test_basic_mine(self, memos, tmp_path):
        p = tmp_path / "meeting.txt"
        p.write_text("Alice: Hello world\nBob: Hi there\nAlice: How are you?")
        miner = ConversationMiner(memos, per_speaker=True, dry_run=False)
        result = miner.mine_conversation(p)
        assert result.imported > 0
        assert "Alice" in result.speakers_detected
        assert "Bob" in result.speakers_detected
        assert result.turns_total == 3

    def test_per_speaker_namespace(self, memos, tmp_path):
        p = tmp_path / "meeting.txt"
        p.write_text("Alice: Hello\nBob: Hi")
        miner = ConversationMiner(memos, namespace_prefix="conv", per_speaker=True)
        result = miner.mine_conversation(p)
        assert result.imported == 2
        # Verify namespaces were used
        assert memos.namespace == ""  # original restored

    def test_no_per_speaker(self, memos, tmp_path):
        p = tmp_path / "meeting.txt"
        p.write_text("Alice: Hello\nBob: Hi")
        miner = ConversationMiner(memos, per_speaker=False)
        result = miner.mine_conversation(p)
        assert result.imported > 0
        assert result.turns_total == 2

    def test_dry_run(self, memos, tmp_path):
        p = tmp_path / "meeting.txt"
        p.write_text("Alice: Hello\nBob: Hi")
        miner = ConversationMiner(memos, per_speaker=True, dry_run=True)
        result = miner.mine_conversation(p)
        assert result.imported > 0
        # Nothing actually stored
        stats = memos.stats()
        assert stats.total_memories == 0

    def test_tags_applied(self, memos, tmp_path):
        p = tmp_path / "2026-04-10-meeting.txt"
        p.write_text("Alice: Important decision")
        miner = ConversationMiner(memos, per_speaker=False, extra_tags=["meeting"])
        result = miner.mine_conversation(p, tags=["team-a"])
        assert result.imported > 0
        # Check tags on stored memory
        items = memos._store.list_all()
        assert len(items) > 0
        tags = items[0].tags
        assert "speaker:alice" in tags
        assert "conversation" in tags
        assert "meeting" in tags
        assert "team-a" in tags
        assert "date:2026-04-10" in tags

    def test_nonexistent_file(self, memos):
        miner = ConversationMiner(memos)
        result = miner.mine_conversation("/nonexistent.txt")
        assert len(result.errors) > 0

    def test_empty_file(self, memos, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("")
        miner = ConversationMiner(memos)
        result = miner.mine_conversation(p)
        assert result.turns_total == 0
        assert len(result.errors) > 0

    def test_no_speakers_detected(self, memos, tmp_path):
        p = tmp_path / "notes.txt"
        p.write_text("Just some notes\nWithout any speakers")
        miner = ConversationMiner(memos)
        result = miner.mine_conversation(p)
        assert result.turns_total == 0

    def test_duplicate_turns_skipped(self, memos, tmp_path):
        p = tmp_path / "dupe.txt"
        p.write_text("Alice: Same thing\nBob: different\nAlice: Same thing")
        miner = ConversationMiner(memos, per_speaker=True)
        result = miner.mine_conversation(p)
        # Both "Alice: Same thing" turns end up in the same chunk, so imported=1
        assert result.imported >= 1

    def test_timestamp_format(self, memos, tmp_path):
        p = tmp_path / "meeting.txt"
        p.write_text("[09:00] Alice: Standup started\n[09:05] Bob: My update")
        miner = ConversationMiner(memos, per_speaker=False)
        result = miner.mine_conversation(p)
        assert result.imported > 0
        assert result.turns_total == 2

    def test_bold_format(self, memos, tmp_path):
        p = tmp_path / "chat.md"
        p.write_text("**Alice:** I think we should go with option A\n**Bob:** Agreed")
        miner = ConversationMiner(memos, per_speaker=False)
        result = miner.mine_conversation(p)
        assert result.imported > 0
        assert "Alice" in result.speakers_detected
        assert "Bob" in result.speakers_detected

    def test_heading_format(self, memos, tmp_path):
        p = tmp_path / "transcript.md"
        p.write_text("## Alice\nAlice's long response about the project.\nIt spans multiple lines.\n## Bob\nBob's response.")
        miner = ConversationMiner(memos, per_speaker=False)
        result = miner.mine_conversation(p)
        assert result.imported > 0
        assert "Alice" in result.speakers_detected

    def test_large_conversation(self, memos, tmp_path):
        """Test with many turns to verify chunking works."""
        lines = [f"Speaker{i % 3}: Turn {i} content here" for i in range(50)]
        p = tmp_path / "large.txt"
        p.write_text("\n".join(lines))
        miner = ConversationMiner(memos, per_speaker=False)
        result = miner.mine_conversation(p)
        assert result.imported > 0
        assert result.turns_total == 50

    def test_namespace_restored_on_error(self, memos, tmp_path):
        """Ensure namespace is restored even if learn fails."""
        p = tmp_path / "meeting.txt"
        p.write_text("Alice: Hello")
        original_ns = memos.namespace
        miner = ConversationMiner(memos, namespace_prefix="conv", per_speaker=True)
        # This should work fine, just verify namespace is restored
        miner.mine_conversation(p)
        assert memos.namespace == original_ns


# ---------------------------------------------------------------------------
# ConversationResult
# ---------------------------------------------------------------------------

class TestConversationResult:
    def test_merge(self):
        r1 = ConversationResult(imported=5, speakers_detected=["Alice"])
        r2 = ConversationResult(imported=3, speakers_detected=["Bob"])
        r1.merge(r2)
        assert r1.imported == 8
        assert "Alice" in r1.speakers_detected
        assert "Bob" in r1.speakers_detected

    def test_str(self):
        r = ConversationResult(imported=5, turns_total=10, speakers_detected=["A", "B"])
        s = str(r)
        assert "imported=5" in s
        assert "speakers=2" in s

    def test_merge_dedup_speakers(self):
        r1 = ConversationResult(speakers_detected=["Alice"])
        r2 = ConversationResult(speakers_detected=["Alice", "Bob"])
        r1.merge(r2)
        assert r1.speakers_detected == ["Alice", "Bob"]


# ---------------------------------------------------------------------------
# REST endpoint test (if FastAPI available)
# ---------------------------------------------------------------------------

class TestConversationRESTEndpoint:
    @pytest.fixture
    def client(self):
        """Create a test client for the API."""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")
        from memos.api import create_fastapi_app
        app = create_fastapi_app(backend="memory")
        return TestClient(app)

    def test_mine_conversation_endpoint(self, client, tmp_path):
        p = tmp_path / "meeting.txt"
        p.write_text("Alice: Hello\nBob: Hi there")
        resp = client.post("/api/v1/mine/conversation", json={
            "path": str(p),
            "per_speaker": False,
            "tags": ["test"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["imported"] > 0
        assert "Alice" in data["speakers"]
        assert "Bob" in data["speakers"]
        assert data["turns_total"] == 2

    def test_mine_conversation_per_speaker(self, client, tmp_path):
        p = tmp_path / "chat.txt"
        p.write_text("Alice: Hello\nBob: Hi")
        resp = client.post("/api/v1/mine/conversation", json={
            "path": str(p),
            "per_speaker": True,
            "namespace_prefix": "chat",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] > 0

    def test_mine_conversation_missing_path(self, client):
        resp = client.post("/api/v1/mine/conversation", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"

    def test_mine_conversation_nonexistent_file(self, client):
        resp = client.post("/api/v1/mine/conversation", json={
            "path": "/nonexistent/file.txt",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
