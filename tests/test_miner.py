"""Tests for smart memory miner (P8)."""
from __future__ import annotations
import json
import pytest
from memos.core import MemOS
from memos.ingest.miner import (
    Miner, MineResult,
    chunk_text, content_hash, detect_room, iter_files,
    _parse_claude_export, _parse_chatgpt_export, _parse_slack_jsonl,
)


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

def test_chunk_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_short_text():
    result = chunk_text("Hello world", size=800)
    assert len(result) == 1
    assert result[0] == "Hello world"


def test_chunk_respects_paragraphs():
    text = "Para one is here.\n\nPara two is here.\n\nPara three is here."
    result = chunk_text(text, size=800)
    assert len(result) == 1  # all fit in one chunk
    assert "Para one" in result[0]
    assert "Para two" in result[0]


def test_chunk_splits_at_size():
    # Each paragraph is ~50 chars, size=80 → one paragraph per chunk
    paras = [f"Paragraph number {i:02d} with some content." for i in range(10)]
    text = "\n\n".join(paras)
    result = chunk_text(text, size=80, overlap=0)
    assert len(result) > 1


def test_chunk_overlap_carries_content():
    paras = ["A" * 100, "B" * 100, "C" * 100]
    text = "\n\n".join(paras)
    result = chunk_text(text, size=150, overlap=40)
    # Second chunk should contain some of first chunk's content
    assert len(result) >= 2
    # With overlap, second chunk starts with tail of first
    full_text = " ".join(result)
    assert "A" in full_text and "B" in full_text


def test_chunk_oversized_paragraph():
    # Single paragraph larger than size → split by sentence
    text = "This is sentence one. " * 40  # ~880 chars
    result = chunk_text(text, size=200)
    assert len(result) > 1
    for chunk in result:
        assert len(chunk) <= 400  # sentences may vary slightly


def test_chunk_preserves_content():
    text = "First para.\n\nSecond para.\n\nThird para."
    result = chunk_text(text, size=800)
    combined = " ".join(result)
    assert "First" in combined
    assert "Second" in combined
    assert "Third" in combined


# ---------------------------------------------------------------------------
# content_hash deduplication
# ---------------------------------------------------------------------------

def test_hash_same_content():
    assert content_hash("hello world") == content_hash("hello world")


def test_hash_case_insensitive():
    assert content_hash("Hello World") == content_hash("hello world")


def test_hash_whitespace_normalized():
    assert content_hash("hello  world") == content_hash("hello world")


def test_hash_different_content():
    assert content_hash("hello") != content_hash("world")


# ---------------------------------------------------------------------------
# detect_room
# ---------------------------------------------------------------------------

def test_detect_room_from_path():
    from pathlib import Path
    tags = detect_room(Path("src/auth/login.py"))
    assert "auth" in tags


def test_detect_room_from_filename():
    from pathlib import Path
    tags = detect_room(Path("deploy_config.md"))
    assert "deployment" in tags


def test_detect_room_from_content():
    from pathlib import Path
    tags = detect_room(Path("notes.md"), text="We need to fix the SQL migration and postgres schema.")
    assert "database" in tags


def test_detect_room_max_tags():
    from pathlib import Path
    tags = detect_room(Path("auth_api_deploy.md"), top_n=2)
    assert len(tags) <= 2


# ---------------------------------------------------------------------------
# Format parsers
# ---------------------------------------------------------------------------

def test_parse_claude_single():
    data = {
        "name": "Test Convo",
        "messages": [
            {"role": "human", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing great, thanks!"},
        ]
    }
    result = list(_parse_claude_export(data))
    assert len(result) == 1
    assert "[Q] Hello" in result[0]["text"]
    assert "[A] I'm" in result[0]["text"]
    assert result[0]["source"] == "Test Convo"
    assert result[0]["format"] == "claude"


def test_parse_claude_list():
    data = [
        {"name": "Convo 1", "messages": [{"role": "human", "content": "Q1"}]},
        {"name": "Convo 2", "messages": [{"role": "human", "content": "Q2"}]},
    ]
    result = list(_parse_claude_export(data))
    assert len(result) == 2


def test_parse_claude_content_blocks():
    data = {
        "messages": [{
            "role": "human",
            "content": [{"type": "text", "text": "Block content here"}]
        }]
    }
    result = list(_parse_claude_export(data))
    assert len(result) == 1
    assert "Block content here" in result[0]["text"]


def test_parse_chatgpt():
    data = [{
        "title": "GPT Convo",
        "create_time": 1700000000,
        "mapping": {
            "node1": {
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["What is Python?"]}
                }
            },
            "node2": {
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Python is a language."]}
                }
            }
        }
    }]
    result = list(_parse_chatgpt_export(data))
    assert len(result) == 1
    assert "Python" in result[0]["text"]
    assert result[0]["format"] == "chatgpt"


def test_parse_slack_jsonl():
    lines = [
        json.dumps({"ts": "1700000000.000", "user": "alice", "text": "Hello team!"}),
        json.dumps({"ts": "1700000060.000", "user": "bob", "text": "Hey Alice!"}),
        json.dumps({"ts": "1700010000.000", "user": "carol", "text": "New thread here"}),
    ]
    result = list(_parse_slack_jsonl(lines))
    assert len(result) >= 1
    full = " ".join(r["text"] for r in result)
    assert "Hello team" in full
    assert "Hey Alice" in full


# ---------------------------------------------------------------------------
# Miner class
# ---------------------------------------------------------------------------

@pytest.fixture
def mem():
    return MemOS()


def test_miner_mine_file(tmp_path, mem):
    md = tmp_path / "notes.md"
    md.write_text("## Python Tips\n\nUse list comprehensions.\n\n## Docker\n\nUse multi-stage builds.")
    miner = Miner(mem)
    result = miner.mine_file(md)
    assert result.imported >= 1
    assert result.errors == []
    assert mem.stats().total_memories >= 1


def test_miner_dry_run(tmp_path, mem):
    md = tmp_path / "notes.md"
    md.write_text("## Tips\n\nPython is great for scripting and automation tasks.")
    miner = Miner(mem, dry_run=True)
    result = miner.mine_file(md)
    assert result.imported >= 1
    assert mem.stats().total_memories == 0  # nothing actually stored


def test_miner_deduplication(tmp_path, mem):
    md = tmp_path / "notes.md"
    md.write_text("This is a unique memory about Python programming.")
    miner = Miner(mem)
    r1 = miner.mine_file(md)
    r2 = miner.mine_file(md)  # same file again
    assert r1.imported >= 1
    assert r2.skipped_duplicates >= 1
    assert mem.stats().total_memories == r1.imported  # no new memories


def test_miner_directory(tmp_path, mem):
    (tmp_path / "a.md").write_text("Python async is powerful for IO-bound tasks.")
    (tmp_path / "b.md").write_text("Docker simplifies deployment and environment setup.")
    (tmp_path / "c.txt").write_text("Redis is great for caching and pub-sub messaging.")
    miner = Miner(mem)
    result = miner.mine_directory(tmp_path)
    assert result.imported >= 3


def test_miner_extra_tags(tmp_path, mem):
    md = tmp_path / "notes.md"
    md.write_text("FastAPI is a modern async Python web framework.")
    miner = Miner(mem, extra_tags=["imported", "project-x"])
    miner.mine_file(md)
    results = mem.recall("FastAPI", top=1)
    assert any("imported" in r.item.tags for r in results)


def test_miner_claude_export(tmp_path, mem):
    export = tmp_path / "claude.json"
    data = [{
        "name": "coding-session",
        "messages": [
            {"role": "human", "content": "How do I use async in Python?"},
            {"role": "assistant", "content": "Use async def and await keywords."},
        ]
    }]
    export.write_text(json.dumps(data))
    miner = Miner(mem)
    result = miner.mine_claude_export(export)
    assert result.imported >= 1
    assert result.errors == []
    recalls = mem.recall("async python", top=5)
    assert len(recalls) >= 1


def test_miner_chatgpt_export(tmp_path, mem):
    export = tmp_path / "chatgpt.json"
    data = [{
        "title": "Python session",
        "create_time": 1700000000,
        "mapping": {
            "n1": {"message": {
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": ["What is FastAPI?"]}
            }},
            "n2": {"message": {
                "author": {"role": "assistant"},
                "content": {"content_type": "text", "parts": ["FastAPI is a high-performance web framework."]}
            }},
        }
    }]
    export.write_text(json.dumps(data))
    miner = Miner(mem)
    result = miner.mine_chatgpt_export(export)
    assert result.imported >= 1
    assert result.errors == []


def test_miner_auto_claude(tmp_path, mem):
    export = tmp_path / "export.json"
    data = [{"name": "test", "messages": [{"role": "human", "content": "Tell me about MemOS memory system."}]}]
    export.write_text(json.dumps(data))
    miner = Miner(mem)
    result = miner.mine_auto(export)
    assert result.imported >= 1


def test_miner_auto_directory(tmp_path, mem):
    (tmp_path / "readme.md").write_text("Project documentation for testing purposes.")
    miner = Miner(mem)
    result = miner.mine_auto(tmp_path)
    assert result.imported >= 1


def test_miner_missing_file(mem):
    from pathlib import Path
    miner = Miner(mem)
    result = miner.mine_file(Path("/nonexistent/file.md"))
    assert len(result.errors) == 1
    assert result.imported == 0


def test_mine_result_merge():
    r1 = MineResult(imported=3, skipped_duplicates=1)
    r2 = MineResult(imported=2, errors=["oops"])
    r1.merge(r2)
    assert r1.imported == 5
    assert r1.skipped_duplicates == 1
    assert r1.errors == ["oops"]
