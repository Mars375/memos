"""Server and config commands: serve, mcp-serve, mcp-stdio, watch, subscribe, config."""

from __future__ import annotations

import os

from ._common import _add_backend_arg


def build(sub) -> None:
    # serve
    serve = sub.add_parser("serve", help="Start REST API server")
    serve.add_argument("--host", default=os.environ.get("MEMOS_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("MEMOS_PORT", "8000")))
    _add_backend_arg(serve)
    serve.add_argument("--chroma-host", default="localhost")
    serve.add_argument("--chroma-port", type=int, default=8000)

    # mcp-serve (HTTP JSON-RPC 2.0)
    mcp_serve = sub.add_parser("mcp-serve", help="Start MCP server (HTTP JSON-RPC 2.0) for agent integration")
    mcp_serve.add_argument("--host", default="127.0.0.1")
    mcp_serve.add_argument("--port", type=int, default=8200)
    _add_backend_arg(mcp_serve)

    # mcp-stdio (stdin/stdout for Claude Code / Cursor direct integration)
    sub.add_parser("mcp-stdio", help="Start MCP server over stdio (for Claude Code / Cursor)")

    # watch / subscribe
    watch = sub.add_parser("watch", help="Watch live memory events from the SSE stream")
    watch.add_argument("--server", help="MemOS server URL (default: MEMOS_URL or http://127.0.0.1:8000)")
    watch.add_argument("--event-types", help="Comma-separated event types filter")
    watch.add_argument("--tags", help="Comma-separated tag filter")
    watch.add_argument("--namespace", help="Namespace filter")
    watch.add_argument("--json", action="store_true", help="Print raw JSON payloads")
    watch.add_argument("--max-events", type=int, default=0, help="Stop after N events (0 = infinite)")

    subscribe = sub.add_parser("subscribe", help="Alias for watch")
    subscribe.add_argument("--server", help="MemOS server URL (default: MEMOS_URL or http://127.0.0.1:8000)")
    subscribe.add_argument("--event-types", help="Comma-separated event types filter")
    subscribe.add_argument("--tags", help="Comma-separated tag filter")
    subscribe.add_argument("--namespace", help="Namespace filter")
    subscribe.add_argument("--json", action="store_true", help="Print raw JSON payloads")
    subscribe.add_argument("--max-events", type=int, default=0, help="Stop after N events (0 = infinite)")

    # config
    cfg_p = sub.add_parser("config", help="View or set CLI configuration")
    cfg_sub = cfg_p.add_subparsers(dest="config_action")
    cfg_show = cfg_sub.add_parser("show", help="Show current resolved config")
    cfg_show.add_argument("--json", action="store_true", help="JSON output")
    cfg_sub.add_parser("path", help="Show config file path")
    cfg_set = cfg_sub.add_parser("set", help="Set a config value")
    cfg_set.add_argument("key_value", nargs="+", help="key=value pairs")
    cfg_init = cfg_sub.add_parser("init", help="Create default config file")
    cfg_init.add_argument("--force", action="store_true", help="Overwrite existing")
