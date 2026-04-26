"""Memory item list, search, get, and delete routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..errors import not_found
from ._memory_common import parse_iso_timestamp


def register_memory_item_routes(router: APIRouter, memos) -> None:
    """Register item list, search, get, and delete endpoints."""

    @router.get("/api/v1/memories")
    async def api_list_memories(
        tag: list[str] | None = Query(default=None),
        require_tag: list[str] | None = Query(default=None),
        exclude_tag: list[str] | None = Query(default=None),
        min_importance: float | None = None,
        max_importance: float | None = None,
        after: str | None = None,
        before: str | None = None,
        sort: str = "created_at",
        limit: int = 50,
    ) -> dict:
        items = memos.list_memories(
            tags=tag,
            require_tags=require_tag,
            exclude_tags=exclude_tag,
            min_importance=min_importance,
            max_importance=max_importance,
            created_after=parse_iso_timestamp(after),
            created_before=parse_iso_timestamp(before),
            sort=sort,
            limit=limit,
        )
        return {
            "status": "ok",
            "results": [
                {
                    "id": item.id,
                    "content": item.content,
                    "tags": item.tags,
                    "importance": item.importance,
                    "created_at": item.created_at,
                    "accessed_at": item.accessed_at,
                }
                for item in items
            ],
            "total": len(items),
        }

    @router.get("/api/v1/search")
    async def api_search(q: str, limit: int = 20) -> dict:
        items = memos.search(q=q, limit=limit)
        return {
            "status": "ok",
            "results": [
                {"id": item.id, "content": item.content[:200], "tags": item.tags, "importance": item.importance}
                for item in items
            ],
        }

    @router.delete("/api/v1/memory/{item_id}", response_model=None)
    async def api_delete(item_id: str) -> dict:
        success = memos.forget(item_id)
        if success:
            return {"status": "deleted"}
        return not_found(f"Memory {item_id} not found")

    @router.get("/api/v1/memory/{item_id}")
    async def api_get_memory(item_id: str) -> dict:
        item = memos.get(item_id)
        if item is None:
            return not_found(f"Memory {item_id} not found")
        result: dict[str, Any] = {
            "id": item.id,
            "content": item.content,
            "tags": item.tags,
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
            "relevance_score": item.relevance_score,
        }
        if item.ttl is not None:
            result.update({"ttl": item.ttl, "expires_at": item.expires_at, "is_expired": item.is_expired})
        if item.metadata:
            public_meta = {k: v for k, v in item.metadata.items() if not k.startswith("_")}
            if public_meta:
                result["metadata"] = public_meta
        return {"status": "ok", "item": result}
