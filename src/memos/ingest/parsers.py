"""Conversation format parsers — Claude, ChatGPT, Slack, Discord, Telegram, OpenClaw."""

from __future__ import annotations

import json
from typing import Any, Iterator, List


def _parse_claude_export(data: Any) -> Iterator[dict]:
    """Parse Claude conversation export JSON.

    Claude exports are either:
    - A single conversation object with "messages" array
    - An array of conversations
    Each message has "role" and "content" (string or array of content blocks).
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
            text = "\n".join(f"[{m.get('user', 'user')}] {m['text']}" for m in group if m.get("text", "").strip())
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
        text = "\n".join(f"[{m.get('user', 'user')}] {m['text']}" for m in group if m.get("text", "").strip())
        if text.strip():
            yield {
                "text": text,
                "source": "slack",
                "created": "",
                "format": "slack",
            }


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
