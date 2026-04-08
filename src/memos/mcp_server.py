"""MemOS MCP Server — JSON-RPC 2.0 bridge for OpenClaw, Claude Code, Cursor."""

from __future__ import annotations

import json
import sys
from typing import Any

try:
    from fastapi import FastAPI
    from fastapi.requests import Request
    from fastapi.responses import JSONResponse
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

__all__ = ["create_mcp_app", "run_stdio", "TOOLS", "_dispatch"]

TOOLS = [
    {
        "name": "memory_search",
        "description": "Search memories semantically. Returns the most relevant memories for a query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "default": 5, "description": "Number of results"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_save",
        "description": "Save a new memory. Use for facts, decisions, preferences, procedures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Memory content"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"},
                "importance": {"type": "number", "default": 0.5, "description": "Importance 0.0-1.0"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "memory_forget",
        "description": "Delete a memory by ID or by tag (removes all memories with that tag).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Memory ID to delete"},
                "tag": {"type": "string", "description": "Delete all memories with this tag"},
            },
        },
    },
    {
        "name": "memory_stats",
        "description": "Return statistics about the memory store.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "kg_add_fact",
        "description": "Add a temporal fact (triple) to the knowledge graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Subject entity"},
                "predicate": {"type": "string", "description": "Relation type"},
                "object": {"type": "string", "description": "Object entity or value"},
                "valid_from": {"type": "string", "description": "Start of validity (epoch, ISO 8601, or relative)"},
                "valid_to": {"type": "string", "description": "End of validity (epoch, ISO 8601, or relative)"},
                "confidence": {"type": "number", "default": 1.0, "description": "Confidence 0.0-1.0"},
                "source": {"type": "string", "description": "Source label"},
            },
            "required": ["subject", "predicate", "object"],
        },
    },
    {
        "name": "kg_query_entity",
        "description": "Query all active facts linked to an entity at a given time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Entity name to query"},
                "time": {"type": "string", "description": "Point in time (epoch, ISO 8601, or relative). Defaults to now."},
                "direction": {"type": "string", "enum": ["both", "subject", "object"], "default": "both"},
            },
            "required": ["entity"],
        },
    },
    {
        "name": "kg_timeline",
        "description": "Return chronological sequence of all facts about an entity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Entity name"},
            },
            "required": ["entity"],
        },
    },
]


def _text(content: str) -> dict:
    return {"content": [{"type": "text", "text": content}]}


def _error(msg: str) -> dict:
    return {"content": [{"type": "text", "text": f"Error: {msg}"}], "isError": True}


def _dispatch(memos: Any, tool: str, args: dict) -> dict:
    """Dispatch a tool call to the MemOS instance."""
    try:
        if tool == "memory_search":
            query = args.get("query", "")
            top_k = int(args.get("top_k", 5))
            tags = args.get("tags") or []
            results = memos.recall(query, top=top_k, filter_tags=tags)
            if not results:
                return _text("No memories found.")
            lines = []
            for r in results:
                tag_str = f"[{', '.join(r.item.tags)}]" if r.item.tags else ""
                lines.append(f"[{r.score:.3f}] {r.item.content} {tag_str}")
            return _text("\n".join(lines))

        elif tool == "memory_save":
            content = args.get("content", "").strip()
            if not content:
                return _error("content is required")
            tags = args.get("tags") or []
            importance = float(args.get("importance", 0.5))
            item = memos.learn(content, tags=tags, importance=importance)
            return _text(f"Saved [{item.id[:8]}] {content[:60]}")

        elif tool == "memory_forget":
            mem_id = args.get("id")
            tag = args.get("tag")
            if mem_id:
                memos.forget(mem_id)
                return _text(f"Forgotten: {mem_id}")
            elif tag:
                count = memos.delete_tag(tag)
                return _text(f"Deleted {count} memories with tag '{tag}'")
            else:
                return _error("Provide 'id' or 'tag'")

        elif tool == "memory_stats":
            s = memos.stats()
            return _text(
                f"Total memories: {s.total_memories}\n"
                f"Total tags: {s.total_tags}\n"
                f"Avg relevance: {s.avg_relevance:.3f}\n"
                f"Decay candidates: {s.decay_candidates}"
            )

        elif tool == "kg_add_fact":
            from .knowledge_graph import KnowledgeGraph
            subject = args.get("subject", "").strip()
            predicate = args.get("predicate", "").strip()
            obj = args.get("object", "").strip()
            if not subject or not predicate or not obj:
                return _error("subject, predicate and object are required")
            kg_instance = getattr(memos, "_kg", None)
            if kg_instance is None:
                kg_instance = KnowledgeGraph()
                memos._kg = kg_instance  # cache it for reuse
            fact_id = kg_instance.add_fact(
                subject=subject,
                predicate=predicate,
                object=obj,
                valid_from=args.get("valid_from"),
                valid_to=args.get("valid_to"),
                confidence=float(args.get("confidence", 1.0)),
                source=args.get("source"),
            )
            return _text(f"Fact added [{fact_id}]: {subject} -{predicate}-> {obj}")

        elif tool == "kg_query_entity":
            from .knowledge_graph import KnowledgeGraph
            entity = args.get("entity", "").strip()
            if not entity:
                return _error("entity is required")
            kg_instance = getattr(memos, "_kg", None)
            if kg_instance is None:
                kg_instance = KnowledgeGraph()
                memos._kg = kg_instance  # cache it for reuse
            facts = kg_instance.query(
                entity,
                time=args.get("time"),
                direction=args.get("direction", "both"),
            )
            if not facts:
                return _text(f"No facts found for: {entity}")
            lines = [f"[{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']}" for f in facts]
            return _text(f"{len(facts)} fact(s):\n" + "\n".join(lines))

        elif tool == "kg_timeline":
            from .knowledge_graph import KnowledgeGraph
            entity = args.get("entity", "").strip()
            if not entity:
                return _error("entity is required")
            kg_instance = getattr(memos, "_kg", None)
            if kg_instance is None:
                kg_instance = KnowledgeGraph()
                memos._kg = kg_instance  # cache it for reuse
            facts = kg_instance.timeline(entity)
            if not facts:
                return _text(f"No timeline entries for: {entity}")
            lines = [f"[{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']}" for f in facts]
            return _text(f"Timeline ({len(facts)} events):\n" + "\n".join(lines))

        else:
            return _error(f"Unknown tool: {tool}")

    except Exception as exc:
        return _error(str(exc))


def create_mcp_app(memos: Any) -> Any:
    """Create a FastAPI MCP HTTP server (JSON-RPC 2.0)."""
    if not _FASTAPI_AVAILABLE:
        raise ImportError("Install memos[server]: pip install memos[server]")

    app = FastAPI(title="MemOS MCP Server", version="1.0.0")

    def _ok(req_id: Any, result: Any) -> JSONResponse:
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _err(req_id: Any, code: int, msg: str, status: int = 200) -> JSONResponse:
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}, status_code=status)

    async def _handle_body(body: dict) -> JSONResponse:
        req_id = body.get("id")
        method = body.get("method", "")
        params = body.get("params", {})
        if method == "initialize":
            return _ok(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "memos-mcp", "version": "1.0.0"},
            })
        elif method == "tools/list":
            return _ok(req_id, {"tools": TOOLS})
        elif method == "tools/call":
            result = _dispatch(memos, params.get("name", ""), params.get("arguments", {}))
            return _ok(req_id, result)
        elif method == "ping":
            return _ok(req_id, {})
        else:
            return _err(req_id, -32601, f"Method not found: {method}", 404)

    @app.post("/")
    async def handle_root(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return _err(None, -32700, "Parse error", 400)
        return await _handle_body(body)

    @app.post("/mcp")
    async def handle_mcp(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return _err(None, -32700, "Parse error", 400)
        return await _handle_body(body)

    @app.get("/health")
    def health() -> dict:
        s = memos.stats()
        return {"status": "ok", "memories": s.total_memories}

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
            _send({"jsonrpc": "2.0", "id": req_id, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "memos-mcp", "version": "1.0.0"},
            }})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            result = _dispatch(memos, params.get("name", ""), params.get("arguments", {}))
            _send({"jsonrpc": "2.0", "id": req_id, "result": result})
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {}})
        else:
            _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})
