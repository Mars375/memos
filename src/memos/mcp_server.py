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

try:
    from fastapi import FastAPI
    from fastapi.requests import Request
    from fastapi.responses import JSONResponse, StreamingResponse

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

__all__ = ["create_mcp_app", "run_stdio", "TOOLS", "_dispatch", "add_mcp_routes"]

_MCP_VERSION = "2025-03-26"

_CORS_ALLOWED_ORIGINS = os.environ.get("MEMOS_CORS_ORIGINS", "*")

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": _CORS_ALLOWED_ORIGINS,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Mcp-Session-Id",
    "Access-Control-Expose-Headers": "Mcp-Session-Id",
}

TOOLS = [
    {
        "name": "memory_search",
        "description": "Search memories semantically with structured filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "default": 5, "description": "Number of results"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Include tags (ANY match)"},
                "require_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags that must all be present",
                },
                "exclude_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags that must not be present",
                },
                "min_importance": {"type": "number", "description": "Minimum importance filter"},
                "max_importance": {"type": "number", "description": "Maximum importance filter"},
                "created_after": {"type": "string", "description": "Only memories created after this ISO date"},
                "created_before": {"type": "string", "description": "Only memories created before this ISO date"},
                "retrieval_mode": {"type": "string", "enum": ["semantic", "keyword", "hybrid"], "default": "semantic"},
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
                "time": {
                    "type": "string",
                    "description": "Point in time (epoch, ISO 8601, or relative). Defaults to now.",
                },
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
    {
        "name": "kg_communities",
        "description": "Detect entity communities in the knowledge graph using Louvain clustering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "algorithm": {
                    "type": "string",
                    "default": "louvain",
                    "description": "Community detection algorithm (currently only 'louvain')",
                },
            },
        },
    },
    {
        "name": "kg_god_nodes",
        "description": "Return the highest-degree (most connected) entities in the knowledge graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top_k": {
                    "type": "integer",
                    "default": 10,
                    "description": "Number of top entities to return",
                },
            },
        },
    },
    {
        "name": "kg_surprising",
        "description": "Find edges connecting entities from different communities — surprising cross-domain connections.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top_k": {
                    "type": "integer",
                    "default": 10,
                    "description": "Number of top surprising connections to return",
                },
            },
        },
    },
    {
        "name": "memory_recall_enriched",
        "description": "Recall memories and augment them with KG facts linked to the detected entities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "default": 10, "description": "Number of memory results"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter memories by tags"},
                "min_score": {"type": "number", "default": 0.0, "description": "Minimum score"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "brain_search",
        "description": "Unified search across memories, living wiki pages, and the knowledge graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "default": 10, "description": "Max results per source"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter memories by tags"},
                "min_score": {"type": "number", "default": 0.0, "description": "Minimum memory score"},
                "max_context_chars": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Max characters for fused context",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "brain_suggest",
        "description": "Suggest exploration questions based on knowledge graph structure — hub entities, cross-community connections, and orphan entities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of suggested questions to return",
                },
            },
        },
    },
    {
        "name": "memory_decay",
        "description": "Apply importance decay to memories. Dry-run by default. Use apply=true to persist changes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "apply": {"type": "boolean", "default": False, "description": "Apply decay (default: dry-run)"},
                "min_age_days": {"type": "number", "description": "Minimum age in days to be eligible for decay"},
                "floor": {"type": "number", "description": "Minimum importance after decay (default: 0.1)"},
            },
        },
    },
    {
        "name": "memory_reinforce",
        "description": "Boost a memory's importance. Use to reinforce frequently recalled or critical memories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Memory ID to reinforce"},
                "strength": {"type": "number", "default": 0.05, "description": "Boost amount"},
            },
            "required": ["memory_id"],
        },
    },
    {
        "name": "memory_wake_up",
        "description": (
            "Return L0 (identity) + L1 (top memories by importance) as a single string "
            "ready to inject into an agent system prompt. Use at session start."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_chars": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Maximum character count of the returned string",
                },
                "l1_top": {
                    "type": "integer",
                    "default": 15,
                    "description": "Number of top-importance memories to include",
                },
                "include_stats": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include a STATS section with total/tag counts",
                },
            },
        },
    },
    {
        "name": "memory_context_for",
        "description": (
            "Return optimised context (identity + semantic results) for a specific query. "
            "Combines L0 identity with L3 full-search results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The query to retrieve context for"},
                "max_chars": {
                    "type": "integer",
                    "default": 1500,
                    "description": "Maximum character count of the returned string",
                },
                "top": {
                    "type": "integer",
                    "default": 10,
                    "description": "Number of semantic results to include",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_sync_check",
        "description": (
            "Check for conflicts between local memory store and a remote export envelope. "
            "Returns a report of new, unchanged, and conflicting memories."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "envelope": {
                    "type": "object",
                    "description": "Remote memory envelope (JSON object with source_agent, target_agent, memories)",
                },
            },
            "required": ["envelope"],
        },
    },
    {
        "name": "memory_sync_apply",
        "description": (
            "Apply remote memories to the local store with conflict resolution. "
            "Strategies: local_wins, remote_wins, merge (default). "
            "Merge unions tags, takes most recent content, max importance."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "envelope": {
                    "type": "object",
                    "description": "Remote memory envelope (JSON object with source_agent, target_agent, memories)",
                },
                "strategy": {
                    "type": "string",
                    "default": "merge",
                    "description": "Conflict resolution: local_wins, remote_wins, merge, manual",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, report what would happen without applying changes",
                },
            },
            "required": ["envelope"],
        },
    },
    {
        "name": "wiki_regenerate_index",
        "description": "Regenerate the Karpathy-style Living Wiki index.md and return its content.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _text(content: str) -> dict:
    return {"content": [{"type": "text", "text": content}]}


def _error(msg: str) -> dict:
    return {"content": [{"type": "text", "text": f"Error: {msg}"}], "isError": True}


def _dispatch_inner(memos: Any, tool: str, args: dict) -> dict:
    """Core tool dispatch — no hooks."""
    try:
        if tool == "memory_search":
            from datetime import datetime as _dt

            def _parse_date(value: Any) -> float | None:
                if not value:
                    return None
                if isinstance(value, (int, float)):
                    return float(value)
                return _dt.fromisoformat(str(value)).timestamp()

            query = args.get("query", "")
            top_k = int(args.get("top_k", 5))
            tags = args.get("tags") or []
            require_tags = args.get("require_tags") or []
            exclude_tags = args.get("exclude_tags") or []
            results = memos.recall(
                query,
                top=top_k,
                filter_tags=tags,
                filter_after=_parse_date(args.get("created_after")),
                filter_before=_parse_date(args.get("created_before")),
                retrieval_mode=args.get("retrieval_mode", "semantic"),
                tag_filter={"require": require_tags, "exclude": exclude_tags}
                if (require_tags or exclude_tags)
                else None,
                min_importance=args.get("min_importance"),
                max_importance=args.get("max_importance"),
            )
            if not results:
                return _text("No memories found.")
            lines = []
            for r in results:
                tag_str = f"[{', '.join(r.item.tags)}]" if r.item.tags else ""
                lines.append(f"[{r.score:.3f}] {r.item.content} {tag_str} (importance={r.item.importance:.2f})")
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

        elif tool == "kg_communities":
            from .knowledge_graph import KnowledgeGraph

            kg_instance = getattr(memos, "_kg", None)
            if kg_instance is None:
                kg_instance = KnowledgeGraph()
                memos._kg = kg_instance
            communities = kg_instance.detect_communities(algorithm=args.get("algorithm", "louvain"))
            if not communities:
                return _text("No communities found (empty graph).")
            lines = [f"Found {len(communities)} communities:"]
            for c in communities:
                members_str = ", ".join(c["members"][:10])
                if c["size"] > 10:
                    members_str += f" (+{c['size'] - 10} more)"
                lines.append(
                    f"  Community {c['id']}: {c['size']} members, hub='{c['hub']}' (degree={c['hub_degree']}) — [{members_str}]"
                )
            return _text("\n".join(lines))

        elif tool == "kg_god_nodes":
            from .knowledge_graph import KnowledgeGraph

            kg_instance = getattr(memos, "_kg", None)
            if kg_instance is None:
                kg_instance = KnowledgeGraph()
                memos._kg = kg_instance
            top_k = int(args.get("top_k", 10))
            nodes = kg_instance.god_nodes(top_k=top_k)
            if not nodes:
                return _text("No entities found (empty graph).")
            lines = [f"Top {len(nodes)} god nodes:"]
            for n in nodes:
                lines.append(f"  {n['entity']} (degree={n['degree']})")
            return _text("\n".join(lines))

        elif tool == "kg_surprising":
            from .knowledge_graph import KnowledgeGraph

            kg_instance = getattr(memos, "_kg", None)
            if kg_instance is None:
                kg_instance = KnowledgeGraph()
                memos._kg = kg_instance
            top_k = int(args.get("top_k", 10))
            connections = kg_instance.surprising_connections(top_k=top_k)
            if not connections:
                return _text("No surprising connections found.")
            lines = [f"Top {len(connections)} surprising connections:"]
            for c in connections:
                lines.append(
                    f"  [{c['id']}] {c['subject']} -{c['predicate']}-> {c['object']} "
                    f"(surprise={c['surprise_score']}) — {c['reason']}"
                )
            return _text("\n".join(lines))

        elif tool == "memory_recall_enriched":
            from .kg_bridge import KGBridge
            from .knowledge_graph import KnowledgeGraph

            query = args.get("query", "").strip()
            if not query:
                return _error("query is required")
            kg_instance = getattr(memos, "_kg", None)
            if kg_instance is None:
                kg_instance = KnowledgeGraph()
                memos._kg = kg_instance
            bridge = getattr(memos, "_kg_bridge", None)
            if bridge is None:
                bridge = KGBridge(memos, kg_instance)
                memos._kg_bridge = bridge
            payload = bridge.recall_enriched(
                query,
                top=int(args.get("top_k", 10)),
                filter_tags=args.get("tags"),
                min_score=float(args.get("min_score", 0.0)),
            )
            memories = payload.get("memories", [])
            facts = payload.get("facts", [])
            text = [f"Memories ({len(memories)}):"]
            for r in memories:
                text.append(f"  {r['score']:.3f} {r['content'][:120]}")
            text.append(f"KG facts ({len(facts)}):")
            for f in facts:
                text.append(f"  [{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']}")
            return _text("\n".join(text))

        elif tool == "brain_search":
            from .brain import BrainSearch
            from .knowledge_graph import KnowledgeGraph

            query = args.get("query", "").strip()
            if not query:
                return _error("query is required")
            kg_instance = getattr(memos, "_kg", None)
            if kg_instance is None:
                kg_instance = KnowledgeGraph()
                memos._kg = kg_instance
            searcher = BrainSearch(memos, kg_instance, wiki_dir=args.get("wiki_dir"))
            result = searcher.search(
                query,
                top_k=int(args.get("top_k", 10)),
                filter_tags=args.get("tags"),
                min_score=float(args.get("min_score", 0.0)),
                max_context_chars=int(args.get("max_context_chars", 2000)),
            )
            payload = result.to_dict()
            text = [
                f"Entities: {', '.join(payload['entities'])}" if payload["entities"] else "Entities: none",
                f"Memories ({len(payload['memories'])})",
            ]
            for item in payload["memories"][:5]:
                text.append(f"  [{item['score']:.2f}] {item['content'][:120]}")
            text.append(f"Wiki ({len(payload['wiki_pages'])})")
            for item in payload["wiki_pages"][:5]:
                text.append(f"  [{item['score']:.2f}] {item['entity']}: {item['snippet']}")
            text.append(f"KG facts ({len(payload['kg_facts'])})")
            for item in payload["kg_facts"][:5]:
                text.append(f"  [{item['confidence_label']}] {item['subject']} -{item['predicate']}-> {item['object']}")
            text.append("Context:")
            text.append(payload["context"])
            return _text("\n".join(text))

        elif tool == "brain_suggest":
            from .brain import BrainSearch
            from .knowledge_graph import KnowledgeGraph

            kg_instance = getattr(memos, "_kg", None)
            if kg_instance is None:
                kg_instance = KnowledgeGraph()
                memos._kg = kg_instance
            searcher = BrainSearch(memos, kg_instance)
            top_k = int(args.get("top_k", 5))
            suggestions = searcher.suggest_questions(top_k=top_k)
            if not suggestions:
                return _text("No suggestions available (empty knowledge graph).")
            lines = [f"Suggested questions ({len(suggestions)}):"]
            for sq in suggestions:
                lines.append(f"  [{sq.category}] {sq.question} (score={sq.score:.2f})")
            return _text("\n".join(lines))

        elif tool == "memory_decay":
            items = memos._store.list_all(namespace=memos._namespace)
            report = memos._decay.run_decay(
                items,
                min_age_days=args.get("min_age_days"),
                floor=args.get("floor"),
                dry_run=not args.get("apply", False),
            )
            if args.get("apply", False):
                for item in items:
                    memos._store.upsert(item, namespace=memos._namespace)
            return _text(
                f"Decay ({'APPLIED' if args.get('apply') else 'DRY RUN'}): "
                f"{report.decayed}/{report.total} decayed, "
                f"avg importance: {report.avg_importance_before:.3f} -> {report.avg_importance_after:.3f}"
            )

        elif tool == "memory_reinforce":
            mem_id = args.get("memory_id", "")
            item = memos._store.get(mem_id, namespace=memos._namespace)
            if item is None:
                return _error(f"Memory not found: {mem_id}")
            old_imp = item.importance
            new_imp = memos._decay.reinforce(item, strength=args.get("strength"))
            memos._store.upsert(item, namespace=memos._namespace)
            return _text(f"Reinforced [{item.id[:8]}] importance: {old_imp:.3f} -> {new_imp:.3f}")

        elif tool == "memory_wake_up":
            from .context import ContextStack

            cs = ContextStack(memos)
            max_chars = int(args.get("max_chars", 2000))
            l1_top = int(args.get("l1_top", 15))
            include_stats = bool(args.get("include_stats", True))
            output = cs.wake_up(max_chars=max_chars, l1_top=l1_top, include_stats=include_stats)
            return _text(output)

        elif tool == "memory_context_for":
            from .context import ContextStack

            query = args.get("query", "").strip()
            if not query:
                return _error("query is required")
            cs = ContextStack(memos)
            max_chars = int(args.get("max_chars", 1500))
            top = int(args.get("top", 10))
            output = cs.context_for(query=query, max_chars=max_chars, top=top)
            return _text(output)

        elif tool == "memory_sync_check":
            from .conflict import ConflictDetector
            from .sharing.models import MemoryEnvelope

            envelope_data = args.get("envelope", {})
            if not envelope_data:
                return _error("envelope is required")
            try:
                envelope = MemoryEnvelope.from_dict(envelope_data)
            except Exception as exc:
                return _error(f"Invalid envelope: {exc}")
            detector = ConflictDetector()
            report = detector.detect(memos, envelope)
            rdict = report.to_dict()
            lines = [
                f"Sync check: {rdict['total_remote']} remote, {rdict['new_memories']} new, {rdict['unchanged']} unchanged, {rdict['conflict_count']} conflicts"
            ]
            for c in report.conflicts:
                types = ", ".join(t.value for t in c.conflict_types)
                lines.append(f"  \u26a0 {c.memory_id[:12]}\u2026 [{types}]")
            if rdict["errors"]:
                lines.append(f"  Errors: {len(rdict['errors'])}")
            return _text("\n".join(lines))

        elif tool == "memory_sync_apply":
            from .conflict import ConflictDetector, ResolutionStrategy
            from .sharing.models import MemoryEnvelope

            envelope_data = args.get("envelope", {})
            if not envelope_data:
                return _error("envelope is required")
            try:
                envelope = MemoryEnvelope.from_dict(envelope_data)
            except Exception as exc:
                return _error(f"Invalid envelope: {exc}")
            strategy_name = args.get("strategy", "merge")
            try:
                strategy = ResolutionStrategy(strategy_name)
            except ValueError:
                return _error(f"Invalid strategy: {strategy_name}")
            detector = ConflictDetector()
            report = detector.detect(memos, envelope)
            if args.get("dry_run", False):
                detector.resolve(report.conflicts, strategy)
                return _text(
                    f"Dry run: {len(report.conflicts)} conflicts would be resolved with {strategy.value}, {report.new_memories} new memories added"
                )
            report = detector.apply(memos, report, strategy)
            return _text(
                f"Sync applied ({strategy.value}): {report.applied} applied, {report.skipped} skipped, {len(report.conflicts)} conflicts resolved"
            )

        elif tool == "wiki_regenerate_index":
            from .wiki_living import LivingWikiEngine

            wiki = LivingWikiEngine(memos)
            content = wiki.regenerate_index()
            return _text(content)

        else:
            return _error(f"Unknown tool: {tool}")

    except Exception as exc:
        return _error(str(exc))


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

    def _h(session_id: str | None = None) -> dict:
        h = dict(_CORS_HEADERS)
        if session_id:
            h["Mcp-Session-Id"] = session_id
        return h

    def _ok(req_id: Any, result: Any, sid: str | None = None) -> JSONResponse:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "result": result},
            headers=_h(sid),
        )

    def _err(req_id: Any, code: int, msg: str, status: int = 200, sid: str | None = None) -> JSONResponse:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}},
            status_code=status,
            headers=_h(sid),
        )

    async def _handle(body: dict, sid: str) -> JSONResponse:
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
            )
        elif method in ("notifications/initialized", "initialized"):
            return JSONResponse({}, headers=_h(sid))
        elif method == "tools/list":
            return _ok(req_id, {"tools": TOOLS}, sid)
        elif method == "tools/call":
            result = _dispatch(memos, params.get("name", ""), params.get("arguments") or {}, hooks=hooks)
            return _ok(req_id, result, sid)
        elif method == "ping":
            return _ok(req_id, {}, sid)
        else:
            return _err(req_id, -32601, f"Method not found: {method}", 404, sid)

    @app.options("/mcp")
    async def mcp_options() -> JSONResponse:
        return JSONResponse({}, headers=_CORS_HEADERS)

    @app.post("/mcp")
    async def mcp_post(request: Request):
        sid = request.headers.get("Mcp-Session-Id") or str(uuid.uuid4())
        try:
            body = await request.json()
        except Exception:
            return _err(None, -32700, "Parse error", 400, sid)

        if "text/event-stream" in request.headers.get("Accept", ""):
            resp = await _handle(body, sid)
            data = resp.body.decode() if hasattr(resp, "body") else "{}"

            async def _sse():
                yield f"data: {data}\n\n"

            return StreamingResponse(
                _sse(),
                media_type="text/event-stream",
                headers={
                    **_CORS_HEADERS,
                    "Mcp-Session-Id": sid,
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        return await _handle(body, sid)

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
            headers={**_CORS_HEADERS, "Mcp-Session-Id": sid, "Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/.well-known/mcp.json")
    async def mcp_discovery() -> JSONResponse:
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
            headers=_CORS_HEADERS,
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
