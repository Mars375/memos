"""MemOS MCP Server — JSON-RPC 2.0 bridge for OpenClaw, Claude Code, Cursor.

Supports two transports:
  - stdio          : for Claude Code / Cursor direct integration
  - Streamable HTTP: MCP 2025-03-26 spec, usable by any HTTP client
      POST  /mcp   — JSON-RPC call (JSON or SSE response)
      GET   /mcp   — SSE keepalive stream
      OPTIONS /mcp — CORS preflight
      GET /.well-known/mcp.json — discovery
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Any

from .mcp_tools import TOOLS
from .mcp_tools import dispatch as _registry_dispatch

try:
    from fastapi import FastAPI
    from fastapi.requests import Request
    from fastapi.responses import JSONResponse, StreamingResponse

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

__all__ = ["create_mcp_app", "run_stdio", "TOOLS", "_dispatch", "_dispatch_inner", "add_mcp_routes"]

_MCP_VERSION = "2025-03-26"

_CORS_ALLOWED_ORIGINS = os.environ.get("MEMOS_CORS_ORIGINS", "")


def _cors_headers(request_origin: str | None = None) -> dict[str, str]:
    """Build CORS headers. When MEMOS_CORS_ORIGINS is unset/empty, reflect
    the request Origin only (same-origin policy). When set to ``*``, allow
    all. Otherwise treat it as a comma-separated allowlist."""
    allowed = _CORS_ALLOWED_ORIGINS.strip()
    if allowed == "*":
        origin = "*"
    elif allowed:
        allowed_set = {o.strip() for o in allowed.split(",") if o.strip()}
        origin = request_origin if request_origin in allowed_set else ""
    else:
        origin = request_origin or ""

    hdrs: dict[str, str] = {
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, Mcp-Session-Id",
        "Access-Control-Expose-Headers": "Mcp-Session-Id",
    }
    if origin:
        hdrs["Access-Control-Allow-Origin"] = origin
    return hdrs


def _dispatch_inner(memos: Any, tool: str, args: dict) -> dict:
    """Core tool dispatch — delegates to the registry."""
    return _registry_dispatch(tool, args, memos)


def _dispatch(memos: Any, tool: str, args: dict, hooks: Any = None) -> dict:
    """Dispatch a tool call with optional pre/post hooks.

    Parameters
    ----------
    hooks:
        Optional :class:`~memos.mcp_hooks.MCPHookRegistry`.
        Pre-hooks run first and may short-circuit; post-hooks run after.
    """
    if hooks is not None:
        early = hooks.run_pre(tool, args, memos)
        if early is not None:
            return early

    result = _dispatch_inner(memos, tool, args)

    if hooks is not None:
        result = hooks.run_post(tool, args, result, memos)

    return result


def add_mcp_routes(app: Any, memos: Any, hooks: Any = None) -> None:
    """Mount MCP Streamable HTTP 2025-03-26 routes onto an existing FastAPI app.

    Routes added:
      OPTIONS /mcp                  — CORS preflight
      POST    /mcp                  — JSON-RPC (plain JSON or SSE)
      GET     /mcp                  — SSE keepalive for server→client notifications
      GET     /.well-known/mcp.json — discovery document
    """
    if not _FASTAPI_AVAILABLE:
        raise ImportError("Install memos[server]: pip install memos[server]")

    def _h(session_id: str | None = None, request: Request | None = None) -> dict:
        origin = request.headers.get("origin") if request else None
        h = _cors_headers(origin)
        if session_id:
            h["Mcp-Session-Id"] = session_id
        return h

    def _ok(req_id: Any, result: Any, sid: str | None = None, request: Request | None = None) -> JSONResponse:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "result": result},
            headers=_h(sid, request),
        )

    def _err(
        req_id: Any, code: int, msg: str, status: int = 200, sid: str | None = None, request: Request | None = None
    ) -> JSONResponse:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}},
            status_code=status,
            headers=_h(sid, request),
        )

    async def _handle(body: dict, sid: str, request: Request) -> JSONResponse:
        req_id = body.get("id")
        method = body.get("method", "")
        params = body.get("params") or {}
        if method == "initialize":
            return _ok(
                req_id,
                {
                    "protocolVersion": _MCP_VERSION,
                    "capabilities": {"tools": {}, "experimental": {}},
                    "serverInfo": {"name": "memos-mcp", "version": "1.0.0"},
                },
                sid,
                request,
            )
        elif method in ("notifications/initialized", "initialized"):
            return JSONResponse({}, headers=_h(sid, request))
        elif method == "tools/list":
            return _ok(req_id, {"tools": TOOLS}, sid, request)
        elif method == "tools/call":
            result = _dispatch(memos, params.get("name", ""), params.get("arguments") or {}, hooks=hooks)
            return _ok(req_id, result, sid, request)
        elif method == "ping":
            return _ok(req_id, {}, sid, request)
        else:
            return _err(req_id, -32601, f"Method not found: {method}", 404, sid, request)

    @app.options("/mcp")
    async def mcp_options(request: Request) -> JSONResponse:
        return JSONResponse({}, headers=_h(request=request))

    @app.post("/mcp")
    async def mcp_post(request: Request):
        sid = request.headers.get("Mcp-Session-Id") or str(uuid.uuid4())
        try:
            body = await request.json()
        except Exception:
            return _err(None, -32700, "Parse error", 400, sid, request)

        if "text/event-stream" in request.headers.get("Accept", ""):
            resp = await _handle(body, sid, request)
            data = resp.body.decode() if hasattr(resp, "body") else "{}"

            async def _sse():
                yield f"data: {data}\n\n"

            return StreamingResponse(
                _sse(),
                media_type="text/event-stream",
                headers={
                    **_h(sid, request),
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        return await _handle(body, sid, request)

    @app.get("/mcp")
    async def mcp_get(request: Request):
        """SSE keepalive stream — server→client notifications channel."""
        sid = request.headers.get("Mcp-Session-Id") or str(uuid.uuid4())

        async def _keepalive():
            while True:
                yield ": keepalive\n\n"
                await asyncio.sleep(15)

        return StreamingResponse(
            _keepalive(),
            media_type="text/event-stream",
            headers={**_h(sid, request), "Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/.well-known/mcp.json")
    async def mcp_discovery(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "schema_version": "1.0",
                "name": "memos-mcp",
                "description": "MemOS — Memory Operating System. Search, save, and recall memories for AI agents.",
                "version": "1.0.0",
                "protocol_version": _MCP_VERSION,
                "endpoint": "/mcp",
                "capabilities": {"tools": True},
            },
            headers=_h(request=request),
        )


def create_mcp_app(memos: Any) -> Any:
    """Create a standalone FastAPI MCP HTTP server."""
    if not _FASTAPI_AVAILABLE:
        raise ImportError("Install memos[server]: pip install memos[server]")

    app = FastAPI(title="MemOS MCP Server", version="1.0.0")

    @app.get("/health")
    def health() -> dict:
        s = memos.stats()
        return {"status": "ok", "memories": s.total_memories}

    # Legacy root endpoint (backward compat)
    @app.post("/")
    async def handle_root(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                status_code=400,
            )
        # inline minimal dispatch for legacy path
        req_id = body.get("id")
        method = body.get("method", "")
        params = body.get("params") or {}
        if method == "initialize":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": _MCP_VERSION,
                        "capabilities": {"tools": {}, "experimental": {}},
                        "serverInfo": {"name": "memos-mcp", "version": "1.0.0"},
                    },
                }
            )
        elif method == "tools/list":
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            result = _dispatch(memos, params.get("name", ""), params.get("arguments") or {})
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})
        elif method == "ping":
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}},
            status_code=404,
        )

    add_mcp_routes(app, memos)
    return app


def run_stdio(memos: Any) -> None:
    """Run MCP server over stdio (for Claude Code / Cursor direct integration)."""

    def _send(obj: dict) -> None:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            body = json.loads(line)
        except json.JSONDecodeError:
            _send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue

        req_id = body.get("id")
        method = body.get("method", "")
        params = body.get("params", {})

        if method == "initialize":
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": _MCP_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "memos-mcp", "version": "1.0.0"},
                    },
                }
            )
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            result = _dispatch(memos, params.get("name", ""), params.get("arguments", {}))
            _send({"jsonrpc": "2.0", "id": req_id, "result": result})
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {}})
        else:
            _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})
