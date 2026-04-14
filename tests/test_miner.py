"""Tests for smart memory miner (P8)."""

from __future__ import annotations

import json

import pytest

from memos.ingest.miner import (
    Miner,
    MineResult,
    _parse_chatgpt_export,
    _parse_claude_export,
    _parse_discord_export,
    _parse_openclaw_session,
    _parse_slack_jsonl,
    _parse_telegram_export,
    chunk_text,
    content_hash,
    detect_room,
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
        ],
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
    data = {"messages": [{"role": "human", "content": [{"type": "text", "text": "Block content here"}]}]}
    result = list(_parse_claude_export(data))
    assert len(result) == 1
    assert "Block content here" in result[0]["text"]


def test_parse_chatgpt():
    data = [
        {
            "title": "GPT Convo",
            "create_time": 1700000000,
            "mapping": {
                "node1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["What is Python?"]},
                    }
                },
                "node2": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["Python is a language."]},
                    }
                },
            },
        }
    ]
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


def test_miner_mine_file(tmp_path, memos_empty):
    md = tmp_path / "notes.md"
    md.write_text("## Python Tips\n\nUse list comprehensions.\n\n## Docker\n\nUse multi-stage builds.")
    miner = Miner(memos_empty)
    result = miner.mine_file(md)
    assert result.imported >= 1
    assert result.errors == []
    assert memos_empty.stats().total_memories >= 1


def test_miner_dry_run(tmp_path, memos_empty):
    md = tmp_path / "notes.md"
    md.write_text("## Tips\n\nPython is great for scripting and automation tasks.")
    miner = Miner(memos_empty, dry_run=True)
    result = miner.mine_file(md)
    assert result.imported >= 1
    assert memos_empty.stats().total_memories == 0  # nothing actually stored


def test_miner_deduplication(tmp_path, memos_empty):
    md = tmp_path / "notes.md"
    md.write_text("This is a unique memory about Python programming.")
    miner = Miner(memos_empty)
    r1 = miner.mine_file(md)
    r2 = miner.mine_file(md)  # same file again
    assert r1.imported >= 1
    assert r2.skipped_duplicates >= 1
    assert memos_empty.stats().total_memories == r1.imported  # no new memories


def test_miner_directory(tmp_path, memos_empty):
    (tmp_path / "a.md").write_text("Python async is powerful for IO-bound tasks.")
    (tmp_path / "b.md").write_text("Docker simplifies deployment and environment setup.")
    (tmp_path / "c.txt").write_text("Redis is great for caching and pub-sub messaging.")
    miner = Miner(memos_empty)
    result = miner.mine_directory(tmp_path)
    assert result.imported >= 3


def test_miner_extra_tags(tmp_path, memos_empty):
    md = tmp_path / "notes.md"
    md.write_text("FastAPI is a modern async Python web framework.")
    miner = Miner(memos_empty, extra_tags=["imported", "project-x"])
    miner.mine_file(md)
    results = memos_empty.recall("FastAPI", top=1)
    assert any("imported" in r.item.tags for r in results)


def test_miner_claude_export(tmp_path, memos_empty):
    export = tmp_path / "claude.json"
    data = [
        {
            "name": "coding-session",
            "messages": [
                {"role": "human", "content": "How do I use async in Python?"},
                {"role": "assistant", "content": "Use async def and await keywords."},
            ],
        }
    ]
    export.write_text(json.dumps(data))
    miner = Miner(memos_empty)
    result = miner.mine_claude_export(export)
    assert result.imported >= 1
    assert result.errors == []
    recalls = memos_empty.recall("async python", top=5)
    assert len(recalls) >= 1


def test_miner_chatgpt_export(tmp_path, memos_empty):
    export = tmp_path / "chatgpt.json"
    data = [
        {
            "title": "Python session",
            "create_time": 1700000000,
            "mapping": {
                "n1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["What is FastAPI?"]},
                    }
                },
                "n2": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["FastAPI is a high-performance web framework."]},
                    }
                },
            },
        }
    ]
    export.write_text(json.dumps(data))
    miner = Miner(memos_empty)
    result = miner.mine_chatgpt_export(export)
    assert result.imported >= 1
    assert result.errors == []


def test_miner_auto_claude(tmp_path, memos_empty):
    export = tmp_path / "export.json"
    data = [{"name": "test", "messages": [{"role": "human", "content": "Tell me about MemOS memory system."}]}]
    export.write_text(json.dumps(data))
    miner = Miner(memos_empty)
    result = miner.mine_auto(export)
    assert result.imported >= 1


def test_miner_auto_directory(tmp_path, memos_empty):
    (tmp_path / "readme.md").write_text("Project documentation for testing purposes.")
    miner = Miner(memos_empty)
    result = miner.mine_auto(tmp_path)
    assert result.imported >= 1


def test_miner_missing_file(memos_empty):
    from pathlib import Path

    miner = Miner(memos_empty)
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


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------


def test_parse_discord_basic():
    data = {
        "guild": {"name": "MyServer"},
        "channel": {"name": "general", "type": "GuildTextChat"},
        "messages": [
            {
                "id": "1",
                "timestamp": "2024-01-01T10:00:00+00:00",
                "author": {"name": "alice"},
                "content": "Hello everyone!",
            },
            {"id": "2", "timestamp": "2024-01-01T10:01:00+00:00", "author": {"name": "bob"}, "content": "Hey Alice!"},
        ],
    }
    result = list(_parse_discord_export(data))
    assert len(result) == 1
    assert "[alice]" in result[0]["text"]
    assert "[bob]" in result[0]["text"]
    assert result[0]["format"] == "discord"
    assert "MyServer" in result[0]["source"]


def test_parse_discord_window_split():
    data = {
        "guild": {"name": "S"},
        "channel": {"name": "c"},
        "messages": [
            {"id": "1", "timestamp": "2024-01-01T10:00:00+00:00", "author": {"name": "a"}, "content": "First message"},
            {
                "id": "2",
                "timestamp": "2024-01-01T11:00:00+00:00",  # 1h later
                "author": {"name": "b"},
                "content": "Different window",
            },
        ],
    }
    result = list(_parse_discord_export(data))
    assert len(result) == 2  # different 10-min windows


def test_parse_discord_list():
    data = [
        {
            "guild": {"name": "S"},
            "channel": {"name": "c1"},
            "messages": [
                {"id": "1", "timestamp": "2024-01-01T10:00:00+00:00", "author": {"name": "a"}, "content": "Hi"}
            ],
        },
        {
            "guild": {"name": "S"},
            "channel": {"name": "c2"},
            "messages": [
                {"id": "2", "timestamp": "2024-01-01T10:00:00+00:00", "author": {"name": "b"}, "content": "Hello"}
            ],
        },
    ]
    result = list(_parse_discord_export(data))
    assert len(result) == 2


def test_miner_discord_export(tmp_path, memos_empty):
    export = tmp_path / "discord.json"
    data = {
        "guild": {"name": "DevServer"},
        "channel": {"name": "python", "type": "GuildTextChat"},
        "messages": [
            {
                "id": "1",
                "timestamp": "2024-01-01T10:00:00+00:00",
                "author": {"name": "dev1"},
                "content": "FastAPI is great for building REST APIs.",
            },
            {
                "id": "2",
                "timestamp": "2024-01-01T10:02:00+00:00",
                "author": {"name": "dev2"},
                "content": "Agreed, async support is excellent.",
            },
        ],
    }
    export.write_text(json.dumps(data))
    miner = Miner(memos_empty)
    result = miner.mine_discord_export(export)
    assert result.imported >= 1
    assert result.errors == []


def test_miner_auto_discord(tmp_path, memos_empty):
    export = tmp_path / "discord_export.json"
    data = {
        "guild": {"name": "S"},
        "channel": {"name": "c"},
        "messages": [
            {
                "id": "1",
                "timestamp": "2024-01-01T10:00:00+00:00",
                "author": {"name": "a"},
                "content": "Testing auto-detection of discord format.",
            }
        ],
    }
    export.write_text(json.dumps(data))
    miner = Miner(memos_empty)
    result = miner.mine_auto(export)
    assert result.imported >= 1


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------


def test_parse_telegram_basic():
    data = {
        "name": "My Chat",
        "type": "personal_chat",
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2024-01-01T10:00:00",
                "from": "alice",
                "from_id": "user123",
                "text": "Hello!",
            },
            {
                "id": 2,
                "type": "message",
                "date": "2024-01-01T10:01:00",
                "from": "bob",
                "from_id": "user456",
                "text": "Hey there!",
            },
        ],
    }
    result = list(_parse_telegram_export(data))
    assert len(result) >= 1
    assert "[alice]" in result[0]["text"]
    assert result[0]["format"] == "telegram"


def test_parse_telegram_formatted_text():
    """Telegram text can be a list of entity objects."""
    data = {
        "name": "Chat",
        "type": "personal_chat",
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2024-01-01T10:00:00",
                "from": "user",
                "from_id": "u1",
                "text": [
                    {"type": "plain", "text": "Check out "},
                    {"type": "link", "text": "this link"},
                    " for more info.",
                ],
            }
        ],
    }
    result = list(_parse_telegram_export(data))
    assert len(result) == 1
    assert "Check out" in result[0]["text"]
    assert "this link" in result[0]["text"]


def test_parse_telegram_skips_non_messages():
    data = {
        "name": "Chat",
        "type": "personal_chat",
        "messages": [
            {"id": 1, "type": "service", "date": "2024-01-01T10:00:00", "from": "system", "action": "pin_message"},
            {
                "id": 2,
                "type": "message",
                "date": "2024-01-01T10:01:00",
                "from": "alice",
                "from_id": "u1",
                "text": "Valid message content here.",
            },
        ],
    }
    result = list(_parse_telegram_export(data))
    assert len(result) == 1
    assert "Valid message" in result[0]["text"]


def test_miner_telegram_export(tmp_path, memos_empty):
    export = tmp_path / "result.json"
    data = {
        "name": "Dev Chat",
        "type": "private_supergroup",
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2024-01-01T10:00:00",
                "from": "alice",
                "from_id": "u1",
                "text": "We should use PostgreSQL for this project data storage.",
            },
            {
                "id": 2,
                "type": "message",
                "date": "2024-01-01T10:02:00",
                "from": "bob",
                "from_id": "u2",
                "text": "Agreed, it handles relations well.",
            },
        ],
    }
    export.write_text(json.dumps(data))
    miner = Miner(memos_empty)
    result = miner.mine_telegram_export(export)
    assert result.imported >= 1
    assert result.errors == []


# ---------------------------------------------------------------------------
# OpenClaw
# ---------------------------------------------------------------------------


def test_parse_openclaw_cron_log():
    data = {
        "job": "forge-chantier-memos",
        "status": "done",
        "ts": 1700000000,
        "output": "Implemented wiki compile mode with 10 tests.",
    }
    result = list(_parse_openclaw_session(data))
    assert len(result) == 1
    assert "forge-chantier-memos" in result[0]["text"]
    assert "wiki compile" in result[0]["text"]
    assert result[0]["format"] == "openclaw"


def test_parse_openclaw_summary():
    data = {
        "summary": "Session focused on MCP server implementation.",
        "learnings": [
            "JSON-RPC 2.0 requires exact id matching",
            "FastAPI Request type must be imported at module level",
        ],
        "decisions": ["Use stdio transport for Claude Code integration"],
    }
    result = list(_parse_openclaw_session(data))
    assert len(result) == 1
    assert "MCP server" in result[0]["text"]
    assert "JSON-RPC" in result[0]["text"]
    assert "stdio transport" in result[0]["text"]


def test_parse_openclaw_memory_snapshot():
    data = {
        "memories": [
            {"content": "Python async is essential for IO-bound tasks.", "tags": ["python", "async"]},
            {"content": "Docker multi-stage builds reduce image size.", "tags": ["docker"]},
        ]
    }
    result = list(_parse_openclaw_session(data))
    assert len(result) == 2
    assert result[0]["_tags"] == ["python", "async"]


def test_parse_openclaw_list():
    data = [
        {"job": "job1", "output": "Result of first job execution."},
        {"job": "job2", "output": "Result of second job execution."},
    ]
    result = list(_parse_openclaw_session(data))
    assert len(result) == 2


def test_miner_openclaw_json(tmp_path, memos_empty):
    log = tmp_path / "session.json"
    data = {
        "job": "forge-chantier-memos",
        "status": "done",
        "output": "Added temporal knowledge graph with SQLite backend and validity windows.",
    }
    log.write_text(json.dumps(data))
    miner = Miner(memos_empty)
    result = miner.mine_openclaw(log)
    assert result.imported >= 1
    assert "openclaw" in memos_empty.recall("knowledge graph", top=1)[0].item.tags


def test_miner_openclaw_jsonl(tmp_path, memos_empty):
    log = tmp_path / "cron.jsonl"
    lines = [
        json.dumps({"job": "forge-gate", "status": "ok", "output": "Spawned memos chantier."}),
        json.dumps({"job": "forge-scout", "status": "ok", "output": "Found 3 new signals."}),
    ]
    log.write_text("\n".join(lines))
    miner = Miner(memos_empty)
    result = miner.mine_openclaw(log)
    assert result.imported >= 2


def test_miner_openclaw_directory(tmp_path, memos_empty):
    (tmp_path / "session1.json").write_text(
        json.dumps({"job": "j1", "output": "Implemented first feature successfully."})
    )
    (tmp_path / "notes.md").write_text("## Learnings\n\nAlways validate before building.")
    miner = Miner(memos_empty)
    result = miner.mine_openclaw(tmp_path)
    assert result.imported >= 2


def test_miner_auto_openclaw(tmp_path, memos_empty):
    log = tmp_path / "openclaw_session.json"
    data = {
        "summary": "Session implementing the wiki compile mode for MemOS.",
        "learnings": ["WikiEngine groups by tag efficiently"],
        "decisions": ["Use ~/.memos/wiki as default output dir"],
    }
    log.write_text(json.dumps(data))
    miner = Miner(memos_empty)
    result = miner.mine_auto(log)
    assert result.imported >= 1


# ---------------------------------------------------------------------------
# mine CLI format option
# ---------------------------------------------------------------------------


def test_miner_format_choices(tmp_path, memos_empty):
    """Verify each format can be explicitly forced."""
    # Discord
    discord_file = tmp_path / "d.json"
    discord_file.write_text(
        json.dumps(
            {
                "guild": {"name": "S"},
                "channel": {"name": "c"},
                "messages": [
                    {
                        "id": "1",
                        "timestamp": "2024-01-01T10:00:00+00:00",
                        "author": {"name": "u"},
                        "content": "Discord message content here.",
                    }
                ],
            }
        )
    )
    miner = Miner(memos_empty)
    r = miner.mine_discord_export(discord_file)
    assert r.imported >= 1

    # Telegram
    tg_file = tmp_path / "t.json"
    tg_file.write_text(
        json.dumps(
            {
                "name": "C",
                "type": "personal_chat",
                "messages": [
                    {
                        "id": 1,
                        "type": "message",
                        "date": "2024-01-01T10:00:00",
                        "from": "u",
                        "from_id": "u1",
                        "text": "Telegram message content here.",
                    }
                ],
            }
        )
    )
    r = miner.mine_telegram_export(tg_file)
    assert r.imported >= 1

    # OpenClaw
    oc_file = tmp_path / "oc.json"
    oc_file.write_text(json.dumps({"job": "test", "output": "OpenClaw job completed successfully."}))
    r = miner.mine_openclaw(oc_file)
    assert r.imported >= 1
