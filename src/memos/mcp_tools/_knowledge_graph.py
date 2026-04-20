"""Knowledge Graph tools: add_fact, query_entity, timeline, communities, god_nodes, surprising."""

from __future__ import annotations

from typing import Any

from ._registry import _error, _get_kg, _text, register_tool

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_KG_ADD_FACT = {
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
}

_KG_QUERY_ENTITY = {
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
}

_KG_TIMELINE = {
    "name": "kg_timeline",
    "description": "Return chronological sequence of all facts about an entity.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "entity": {"type": "string", "description": "Entity name"},
        },
        "required": ["entity"],
    },
}

_KG_COMMUNITIES = {
    "name": "kg_communities",
    "description": "Detect entity communities in the knowledge graph using label-propagation clustering (no external dependencies).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "algorithm": {
                "type": "string",
                "default": "label_propagation",
                "description": "Community detection algorithm (currently only 'label_propagation')",
            },
        },
    },
}

_KG_GOD_NODES = {
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
}

_KG_SURPRISING = {
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
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_kg_add_fact(args: dict, memos: Any) -> dict:
    subject = args.get("subject", "").strip()
    predicate = args.get("predicate", "").strip()
    obj = args.get("object", "").strip()
    if not subject or not predicate or not obj:
        return _error("subject, predicate and object are required")
    kg_instance = _get_kg(memos)
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


def _handle_kg_query_entity(args: dict, memos: Any) -> dict:
    entity = args.get("entity", "").strip()
    if not entity:
        return _error("entity is required")
    kg_instance = _get_kg(memos)
    facts = kg_instance.query(
        entity,
        time=args.get("time"),
        direction=args.get("direction", "both"),
    )
    if not facts:
        return _text(f"No facts found for: {entity}")
    lines = [f"[{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']}" for f in facts]
    return _text(f"{len(facts)} fact(s):\n" + "\n".join(lines))


def _handle_kg_timeline(args: dict, memos: Any) -> dict:
    entity = args.get("entity", "").strip()
    if not entity:
        return _error("entity is required")
    kg_instance = _get_kg(memos)
    facts = kg_instance.timeline(entity)
    if not facts:
        return _text(f"No timeline entries for: {entity}")
    lines = [f"[{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']}" for f in facts]
    return _text(f"Timeline ({len(facts)} events):\n" + "\n".join(lines))


def _handle_kg_communities(args: dict, memos: Any) -> dict:
    kg_instance = _get_kg(memos)
    communities = kg_instance.detect_communities(algorithm=args.get("algorithm", "label_propagation"))
    if not communities:
        return _text("No communities found (empty graph).")
    lines = [f"Found {len(communities)} communities:"]
    for c in communities:
        nodes_str = ", ".join(c["nodes"][:10])
        if c["size"] > 10:
            nodes_str += f" (+{c['size'] - 10} more)"
        lines.append(
            f"  Community {c['id']}: {c['size']} nodes, "
            f"label='{c['label']}', top_entity='{c['top_entity']}' — [{nodes_str}]"
        )
    return _text("\n".join(lines))


def _handle_kg_god_nodes(args: dict, memos: Any) -> dict:
    kg_instance = _get_kg(memos)
    top_k = int(args.get("top_k", 10))
    nodes = kg_instance.god_nodes(top_k=top_k)
    if not nodes:
        return _text("No entities found (empty graph).")
    lines = [f"Top {len(nodes)} god nodes:"]
    for n in nodes:
        top_preds = ", ".join(n.get("top_predicates", []))
        lines.append(
            f"  {n['entity']} (degree={n['degree']}, "
            f"as_subject={n.get('facts_as_subject', 0)}, "
            f"as_object={n.get('facts_as_object', 0)}"
            f"{', top_predicates=[' + top_preds + ']' if top_preds else ''})"
        )
    return _text("\n".join(lines))


def _handle_kg_surprising(args: dict, memos: Any) -> dict:
    kg_instance = _get_kg(memos)
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


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_tool("kg_add_fact", _KG_ADD_FACT, _handle_kg_add_fact)
register_tool("kg_query_entity", _KG_QUERY_ENTITY, _handle_kg_query_entity)
register_tool("kg_timeline", _KG_TIMELINE, _handle_kg_timeline)
register_tool("kg_communities", _KG_COMMUNITIES, _handle_kg_communities)
register_tool("kg_god_nodes", _KG_GOD_NODES, _handle_kg_god_nodes)
register_tool("kg_surprising", _KG_SURPRISING, _handle_kg_surprising)
