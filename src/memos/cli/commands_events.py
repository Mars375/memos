"""MemOS CLI — event streaming commands."""

from __future__ import annotations

import argparse
import json
import os


def cmd_watch(ns: argparse.Namespace) -> None:
    """Watch live memory events via the SSE stream."""
    import httpx

    server = getattr(ns, "server", None) or os.environ.get("MEMOS_URL", "http://127.0.0.1:8000")
    params: dict[str, str] = {}
    if ns.event_types:
        params["event_types"] = ns.event_types
    if ns.tags:
        params["tags"] = ns.tags
    if ns.namespace:
        params["namespace"] = ns.namespace

    url = f"{server.rstrip('/')}/api/v1/events/stream"

    def _emit(event_name: str, payload: str) -> None:
        if ns.json:
            print(payload)
            return
        try:
            data = json.loads(payload)
        except Exception:
            print(f"{event_name}: {payload}")
            return
        if isinstance(data, dict):
            content = data.get("data", {})
            tags = content.get("tags") or []
            tags_txt = f" [{', '.join(tags)}]" if tags else ""
            preview = content.get("content") or content.get("query") or content.get("message") or ""
            ns_txt = f" @{data.get('namespace')}" if data.get("namespace") else ""
            print(f"{event_name}{ns_txt}{tags_txt} {preview}".strip())
        else:
            print(f"{event_name}: {payload}")

    seen = 0
    with httpx.stream("GET", url, params=params, timeout=None) as resp:
        resp.raise_for_status()
        event_name = "message"
        data_lines: list[str] = []
        for line in resp.iter_lines():
            if line is None:
                continue
            line = line.decode() if isinstance(line, bytes) else line
            if line.startswith("event: "):
                event_name = line.split(": ", 1)[1]
            elif line.startswith("data: "):
                data_lines.append(line.split(": ", 1)[1])
            elif line == "":
                if data_lines:
                    _emit(event_name, "\n".join(data_lines))
                    seen += 1
                    data_lines = []
                    event_name = "message"
                    if ns.max_events and seen >= ns.max_events:
                        break


def cmd_subscribe(ns: argparse.Namespace) -> None:
    """Alias for watch, more explicit for subscription-style usage."""
    cmd_watch(ns)
