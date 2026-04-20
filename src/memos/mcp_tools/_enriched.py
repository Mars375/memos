"""Enriched retrieval tools: memory_recall_enriched, brain_search, brain_suggest."""

from __future__ import annotations

from typing import Any

from ._registry import _error, _get_kg, _get_kg_bridge, _text, register_tool

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_MEMORY_RECALL_ENRICHED = {
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
}

_BRAIN_SEARCH = {
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
}

_BRAIN_SUGGEST = {
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
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_memory_recall_enriched(args: dict, memos: Any) -> dict:
    query = args.get("query", "").strip()
    if not query:
        return _error("query is required")
    kg_instance = _get_kg(memos)
    bridge = _get_kg_bridge(memos, kg_instance)
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


def _handle_brain_search(args: dict, memos: Any) -> dict:
    from ..brain import BrainSearch

    query = args.get("query", "").strip()
    if not query:
        return _error("query is required")
    kg_instance = _get_kg(memos)
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


def _handle_brain_suggest(args: dict, memos: Any) -> dict:
    from ..brain import BrainSearch

    kg_instance = _get_kg(memos)
    searcher = BrainSearch(memos, kg_instance)
    top_k = int(args.get("top_k", 5))
    suggestions = searcher.suggest_questions(top_k=top_k)
    if not suggestions:
        return _text("No suggestions available (empty knowledge graph).")
    lines = [f"Suggested questions ({len(suggestions)}):"]
    for sq in suggestions:
        lines.append(f"  [{sq.category}] {sq.question} (score={sq.score:.2f})")
    return _text("\n".join(lines))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_tool("memory_recall_enriched", _MEMORY_RECALL_ENRICHED, _handle_memory_recall_enriched)
register_tool("brain_search", _BRAIN_SEARCH, _handle_brain_search)
register_tool("brain_suggest", _BRAIN_SUGGEST, _handle_brain_suggest)
