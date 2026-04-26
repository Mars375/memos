"""Recall query memory routes."""

from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..schemas import RecallRequest
from ..sse import sse_stream
from ._memory_common import _parse_date, as_list, parse_iso_timestamp


def register_memory_recall_query_routes(router: APIRouter, memos, kg_bridge) -> None:
    """Register recall query and streaming endpoints."""

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
