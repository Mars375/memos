"""Context stack and memory graph API routes."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter

from ..schemas import ContextIdentityRequest


def create_context_router(memos, _context_stack) -> APIRouter:
    """Create context and graph routes."""
    router = APIRouter()

    @router.get("/api/v1/context/wake-up")
    async def context_wake_up(max_chars: int = 2000, l1_top: int = 15, include_stats: bool = True):
        output = _context_stack.wake_up(max_chars=max_chars, l1_top=l1_top, include_stats=include_stats)
        return {"status": "ok", "context": output, "chars": len(output)}

    @router.get("/api/v1/context/identity")
    async def context_get_identity():
        content = _context_stack.get_identity()
        return {"status": "ok", "identity": content, "exists": bool(content)}

    @router.post("/api/v1/context/identity")
    async def context_set_identity(body: ContextIdentityRequest):
        _context_stack.set_identity(body.content)
        return {"status": "ok", "chars": len(body.content)}

    @router.get("/api/v1/context/for")
    async def context_for_query(query: str, max_chars: int = 1500, top: int = 10):
        output = _context_stack.context_for(query=query, max_chars=max_chars, top=top)
        return {"status": "ok", "context": output, "query": query, "chars": len(output)}

    @router.get("/api/v1/graph")
    async def api_graph(min_shared_tags: int = 1, limit: int = 500, created_before: Optional[float] = None):
        items = memos._store.list_all(namespace=memos._namespace)
        now = time.time()
        nodes = []
        for item in items[:limit]:
            if item.is_expired:
                continue
            if created_before is not None and item.created_at > created_before:
                continue
            age_days = (now - item.created_at) / 86400
            nodes.append(
                {
                    "id": item.id,
                    "label": item.content[:60] + ("…" if len(item.content) > 60 else ""),
                    "content": item.content,
                    "tags": item.tags,
                    "importance": item.importance,
                    "relevance": item.relevance_score,
                    "age_days": round(age_days, 1),
                    "access_count": item.access_count,
                    "primary_tag": item.tags[0] if item.tags else "__untagged__",
                    "namespace": getattr(item, "namespace", memos._namespace or "default"),
                    "created_at": item.created_at,
                }
            )
        edge_map: dict[tuple[str, str], dict] = {}
        tag_to_ids: dict[str, list[str]] = {}
        for node in nodes:
            for tag in node["tags"]:
                tag_to_ids.setdefault(tag, []).append(node["id"])
        for tag, ids in tag_to_ids.items():
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    key = tuple(sorted([ids[i], ids[j]]))
                    edge = edge_map.get(key)
                    if edge is None:
                        edge_map[key] = {"source": key[0], "target": key[1], "shared_tags": [tag], "weight": 1}
                    else:
                        edge["weight"] += 1
                        edge["shared_tags"].append(tag)
        edges = list(edge_map.values())
        if min_shared_tags > 1:
            edges = [edge for edge in edges if edge["weight"] >= min_shared_tags]
        stats = memos.stats(items=items)
        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_memories": stats.total_memories,
                "total_tags": stats.total_tags,
                "created_before": created_before,
            },
        }

    return router
