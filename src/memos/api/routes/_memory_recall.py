"""Recall, query, and retrieval memory routes."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..errors import not_found
from ..schemas import RecallRequest
from ..sse import sse_stream
from ._memory_common import _parse_date, as_list, parse_iso_timestamp


def register_memory_recall_routes(router: APIRouter, memos, kg_bridge) -> None:
    """Register recall, search, get, and list endpoints."""

    @router.post("/api/v1/recall")
    async def api_recall(req: RecallRequest) -> dict:
        tags_payload = req.tags
        filter_tags = req.filter_tags
        tag_filter = None
        if isinstance(tags_payload, dict):
            tag_filter = {
                "include": as_list(tags_payload.get("include")),
                "require": as_list(tags_payload.get("require")),
                "exclude": as_list(tags_payload.get("exclude")),
                "mode": tags_payload.get("mode", "ANY"),
            }
            filter_tags = None
        elif isinstance(tags_payload, list):
            filter_tags = tags_payload

        importance_payload = req.importance.model_dump()
        explain = req.explain
        results = list(
            memos.recall(
                query=req.query,
                top=req.top_k,
                filter_tags=filter_tags,
                min_score=req.min_score,
                filter_after=_parse_date(req.created_after or req.filter_after),
                filter_before=_parse_date(req.created_before or req.filter_before),
                retrieval_mode=req.retrieval_mode,
                tag_filter=tag_filter,
                min_importance=importance_payload.get("min"),
                max_importance=importance_payload.get("max"),
            )
        )

        if req.rerank and results:
            llm_client = getattr(memos, "_llm_client", None)
            from ...retrieval.hybrid import HybridRetriever

            retriever = HybridRetriever()
            results = retriever.llm_rerank(
                query=req.query,
                candidates=results,
                top_k=req.top_k,
                llm_client=llm_client,
            )

        serialized = []
        for result in results:
            entry = {
                "id": result.item.id,
                "content": result.item.content,
                "score": round(result.score, 4),
                "tags": result.item.tags,
                "match_reason": result.match_reason,
                "importance": result.item.importance,
                "created_at": result.item.created_at,
                "age_days": round((time.time() - result.item.created_at) / 86400, 1),
            }
            if explain and result.score_breakdown:
                entry["score_breakdown"] = result.score_breakdown.to_dict()
            serialized.append(entry)
        return {"status": "ok", "results": serialized}

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

    @router.get("/api/v1/recall/enriched")
    async def api_recall_enriched(
        q: str,
        top: int = 10,
        filter_tags: str | None = None,
        min_score: float = 0.0,
        filter_after: str | None = None,
        filter_before: str | None = None,
    ) -> dict:
        tags = [t.strip() for t in filter_tags.split(",") if t.strip()] if filter_tags else None
        payload = kg_bridge.recall_enriched(
            q,
            top=top,
            filter_tags=tags,
            min_score=min_score,
            filter_after=parse_iso_timestamp(filter_after),
            filter_before=parse_iso_timestamp(filter_before),
        )
        return {"status": "ok", **payload}

    @router.get("/api/v1/recall/stream", response_model=None)
    async def api_recall_stream(
        q: str,
        top: int = 5,
        filter_tags: str | None = None,
        min_score: float = 0.0,
    ) -> StreamingResponse:
        tags = [t.strip() for t in filter_tags.split(",") if t.strip()] if filter_tags else None
        recall_gen = memos.recall_stream(query=q, top=top, filter_tags=tags, min_score=min_score)
        return StreamingResponse(
            sse_stream(recall_gen, q),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

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

    @router.get("/api/v1/recall/at")
    async def api_recall_at(q: str, at: float, top: int = 5, min_score: float = 0.0) -> dict:
        results = memos.recall_at(q, at, top=top, min_score=min_score)
        return {
            "query": q,
            "timestamp": at,
            "total": len(results),
            "results": [
                {
                    "id": result.item.id,
                    "content": result.item.content,
                    "score": round(result.score, 4),
                    "tags": result.item.tags,
                    "match_reason": result.match_reason,
                }
                for result in results
            ],
        }

    @router.get("/api/v1/recall/at/stream", response_model=None)
    async def api_recall_at_stream(q: str, at: float, top: int = 5, min_score: float = 0.0) -> StreamingResponse:
        import asyncio as _asyncio

        results = memos.recall_at(q, at, top=top, min_score=min_score)

        async def _gen():
            for result in results:
                yield result
                await _asyncio.sleep(0)

        return StreamingResponse(
            sse_stream(_gen(), q),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
