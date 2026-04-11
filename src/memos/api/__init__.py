"""REST API for MemOS."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

from .. import __version__ as MEMOS_VERSION
from ..core import MemOS, MemoryStats

try:
    from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import StreamingResponse, HTMLResponse
except ImportError:  # pragma: no cover - optional server dependency
    FastAPI = None  # type: ignore[assignment]
    Query = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    WebSocket = None  # type: ignore[assignment]
    WebSocketDisconnect = None  # type: ignore[assignment]
    StreamingResponse = None  # type: ignore[assignment]
    HTMLResponse = None  # type: ignore[assignment]


def create_api(memos: MemOS) -> dict[str, Any]:
    """Create API route handlers. Can be used with any ASGI framework.
    
    For FastAPI, wrap these in router. For raw ASGI, use the asgi_app below.
    """
    async def learn(body: dict) -> dict:
        try:
            item = memos.learn(
                content=body["content"],
                tags=body.get("tags"),
                importance=body.get("importance", 0.5),
                metadata=body.get("metadata"),
            )
            return {"status": "ok", "id": item.id, "tags": item.tags}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    async def recall(body: dict) -> dict:
        from datetime import datetime as _dt

        def _parse_date(value: Any) -> float | None:
            if not value:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            return _dt.fromisoformat(str(value)).timestamp()

        def _as_list(value: Any) -> list[str]:
            if not value:
                return []
            if isinstance(value, str):
                return [value]
            return [str(item) for item in value if item]

        tags_payload = body.get("tags")
        filter_tags = body.get("filter_tags")
        tag_filter = None
        if isinstance(tags_payload, dict):
            tag_filter = {
                "include": _as_list(tags_payload.get("include")),
                "require": _as_list(tags_payload.get("require")),
                "exclude": _as_list(tags_payload.get("exclude")),
                "mode": tags_payload.get("mode", "ANY"),
            }
            filter_tags = None
        elif isinstance(tags_payload, list):
            filter_tags = tags_payload

        importance_payload = body.get("importance") or {}
        retrieval_mode = body.get("retrieval_mode", "semantic")
        if retrieval_mode not in ("semantic", "keyword", "hybrid"):
            return {"status": "error", "message": "Invalid retrieval_mode. Must be semantic, keyword, or hybrid."}

        results = memos.recall(
            query=body["query"],
            top=body.get("top_k", body.get("top", 5)),
            filter_tags=filter_tags,
            min_score=body.get("min_score", 0.0),
            filter_after=_parse_date(body.get("created_after") or body.get("filter_after")),
            filter_before=_parse_date(body.get("created_before") or body.get("filter_before")),
            retrieval_mode=retrieval_mode,
            tag_filter=tag_filter,
            min_importance=importance_payload.get("min"),
            max_importance=importance_payload.get("max"),
        )
        return {
            "status": "ok",
            "results": [
                {
                    "id": r.item.id,
                    "content": r.item.content,
                    "score": round(r.score, 4),
                    "tags": r.item.tags,
                    "match_reason": r.match_reason,
                    "importance": r.item.importance,
                    "created_at": r.item.created_at,
                    "age_days": round((__import__("time").time() - r.item.created_at) / 86400, 1),
                }
                for r in results
            ],
        }

    async def prune(body: dict) -> dict:
        pruned = memos.prune(
            threshold=body.get("threshold", 0.1),
            max_age_days=body.get("max_age_days", 90.0),
            dry_run=body.get("dry_run", False),
        )
        return {
            "status": "ok",
            "pruned_count": len(pruned),
            "pruned_ids": [item.id for item in pruned],
        }

    async def stats(_body: dict = None) -> dict:
        s = memos.stats()
        return {
            "total_memories": s.total_memories,
            "total_tags": s.total_tags,
            "avg_relevance": round(s.avg_relevance, 3),
            "avg_importance": round(s.avg_importance, 3),
            "oldest_memory_days": round(s.oldest_memory_days, 1),
            "newest_memory_days": round(s.newest_memory_days, 1),
            "decay_candidates": s.decay_candidates,
            "top_tags": s.top_tags,
        }

    async def analytics_top(body: dict | None = None) -> dict:
        payload = body or {}
        return {"status": "ok", "results": memos.analytics.top_recalled(n=payload.get("n", 20))}

    async def analytics_patterns(body: dict | None = None) -> dict:
        payload = body or {}
        return {"status": "ok", "results": memos.analytics.query_patterns(n=payload.get("n", 20))}

    async def analytics_latency(_body: dict | None = None) -> dict:
        return {"status": "ok", "results": memos.analytics.latency_stats()}

    async def analytics_success(body: dict | None = None) -> dict:
        payload = body or {}
        days = int(payload.get("days", 7))
        return {"status": "ok", **memos.analytics.recall_success_rate_stats(days=days)}

    async def analytics_daily(body: dict | None = None) -> dict:
        payload = body or {}
        days = int(payload.get("days", 30))
        return {"status": "ok", "results": memos.analytics.daily_activity(days=days)}

    async def analytics_zero(body: dict | None = None) -> dict:
        payload = body or {}
        return {"status": "ok", "results": memos.analytics.zero_result_queries(n=payload.get("n", 20))}

    async def analytics_summary(body: dict | None = None) -> dict:
        payload = body or {}
        days = int(payload.get("days", 7))
        return {"status": "ok", **memos.analytics.summary(days=days)}

    async def search(body: dict) -> dict:
        items = memos.search(q=body["q"], limit=body.get("limit", 20))
        return {
            "status": "ok",
            "results": [
                {
                    "id": item.id,
                    "content": item.content[:200],
                    "tags": item.tags,
                    "importance": item.importance,
                }
                for item in items
            ],
        }

    async def delete_memory(item_id: str) -> dict:
        success = memos.forget(item_id)
        return {"status": "deleted" if success else "not_found"}

    async def get_memory(item_id: str) -> dict:
        item = memos.get(item_id)
        if item is None:
            return {"status": "not_found", "message": f"Memory {item_id} not found"}
        result = {
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
            result["ttl"] = item.ttl
            result["expires_at"] = item.expires_at
            result["is_expired"] = item.is_expired
        if item.metadata:
            # Exclude internal metadata keys
            public_meta = {k: v for k, v in item.metadata.items() if not k.startswith("_")}
            if public_meta:
                result["metadata"] = public_meta
        return {"status": "ok", "item": result}

    async def batch_learn(body: dict) -> dict:
        items = body.get("items", [])
        if not items:
            return {"status": "error", "message": "No items provided"}
        if len(items) > 1000:
            return {"status": "error", "message": "Batch size exceeds 1000 items"}
        try:
            result = memos.batch_learn(
                items=items,
                continue_on_error=body.get("continue_on_error", True),
            )
            return {"status": "ok", **result}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    return {
        "learn": learn,
        "batch_learn": batch_learn,
        "recall": recall,
        "prune": prune,
        "stats": stats,
        "analytics_top": analytics_top,
        "analytics_patterns": analytics_patterns,
        "analytics_latency": analytics_latency,
        "analytics_success": analytics_success,
        "analytics_daily": analytics_daily,
        "analytics_zero": analytics_zero,
        "analytics_summary": analytics_summary,
        "search": search,
        "delete_memory": delete_memory,
        "get_memory": get_memory,
    }


def create_fastapi_app(memos: Optional[MemOS] = None, api_keys: Optional[list[str]] = None, rate_limit: int = 100, kg_db_path: Optional[str] = None, **kwargs) -> Any:
    """Create a FastAPI application for MemOS.
    
    Args:
        api_keys: List of valid API keys. If None/empty, auth is disabled.
        rate_limit: Max requests per minute per key (default 100).
    """
    if FastAPI is None:
        raise ImportError(
            "FastAPI is required for the server. "
            "Install with: pip install memos[server]"
        )

    if memos is None:
        memos = MemOS(**kwargs)

    from ..knowledge_graph import KnowledgeGraph
    from ..kg_bridge import KGBridge
    _kg = KnowledgeGraph(db_path=kg_db_path)
    _kg_bridge = KGBridge(memos, _kg)

    app = FastAPI(
        title="MemOS",
        description="Memory Operating System for LLM Agents",
        version=MEMOS_VERSION,
    )
    app.state.memos = memos

    routes = create_api(memos)

    @app.post("/api/v1/learn")
    async def api_learn(body: dict):
        return await routes["learn"](body)

    @app.post("/api/v1/learn/extract")
    async def api_learn_extract(body: dict):
        """Learn a memory and extract simple KG facts."""
        content = body.get("content", "").strip()
        if not content:
            return {"status": "error", "message": "content is required"}
        try:
            payload = _kg_bridge.learn_and_extract(
                content,
                tags=body.get("tags"),
                importance=float(body.get("importance", 0.5)),
                metadata=body.get("metadata"),
            )
            return {"status": "ok", **payload}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @app.post("/api/v1/learn/batch")
    async def api_batch_learn(body: dict):
        """Batch learn — store multiple memories in one call.

        Body:
            items: list of dicts, each with content (required), tags, importance, metadata.
            continue_on_error: bool (default True) — skip invalid items vs raise.

        Returns:
            status, learned count, skipped count, errors, item details.
        """
        return await routes["batch_learn"](body)

    @app.post("/api/v1/ingest/url")
    async def api_ingest_url(body: dict):
        """Fetch a URL and ingest it into memory."""
        url = body.get("url", "").strip()
        if not url:
            return {"status": "error", "message": "url is required"}
        result = memos.ingest_url(
            url,
            tags=body.get("tags"),
            importance=float(body.get("importance", 0.5)),
            max_chunk=int(body.get("max_chunk", 2000)),
            dry_run=bool(body.get("dry_run", False)),
        )
        head_meta = result.chunks[0].get("metadata", {}) if result.chunks else {}
        payload = {
            "status": "ok" if not result.errors else "partial",
            "url": url,
            "total_chunks": result.total_chunks,
            "skipped": result.skipped,
            "errors": result.errors,
            "source_type": head_meta.get("source_type"),
            "title": head_meta.get("title"),
        }
        if body.get("dry_run"):
            payload["chunks"] = result.chunks
        return payload

    @app.post("/api/v1/mine/conversation")
    async def api_mine_conversation(body: dict):
        """Parse a transcript text and ingest per-speaker into MemOS.

        Body:
            text (str): raw transcript content (mutually exclusive with path)
            path (str): server-side file path (optional)
            per_speaker (bool): store under per-speaker namespaces (default true)
            namespace_prefix (str): namespace prefix (default "conv")
            tags (list[str]): extra tags
            importance (float): base importance (default 0.6)
            dry_run (bool): preview without storing (default false)
        """
        from ..__init__ import __version__  # noqa: F401 — keep import clean
        from ..ingest.conversation import ConversationMiner, parse_transcript
        import tempfile, os

        text_body = body.get("text", "")
        path_body = body.get("path", "")

        if not text_body and not path_body:
            return {"status": "error", "message": "Either 'text' or 'path' is required"}

        per_speaker = bool(body.get("per_speaker", True))
        namespace_prefix = str(body.get("namespace_prefix", "conv"))
        extra_tags = body.get("tags") or []
        importance = float(body.get("importance", 0.6))
        dry_run = bool(body.get("dry_run", False))

        miner = ConversationMiner(memos, dry_run=dry_run)

        if text_body:
            # Write to temp file so ConversationMiner.mine_conversation() can read it
            try:
                fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="memos_conv_")
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(text_body)
                result = miner.mine_conversation(
                    tmp_path,
                    namespace_prefix=namespace_prefix,
                    per_speaker=per_speaker,
                    tags=extra_tags or None,
                    importance=importance,
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        else:
            result = miner.mine_conversation(
                path_body,
                namespace_prefix=namespace_prefix,
                per_speaker=per_speaker,
                tags=extra_tags or None,
                importance=importance,
            )

        payload = {
            "status": "ok" if not result.errors else "partial",
            "imported": result.imported,
            "skipped_duplicates": result.skipped_duplicates,
            "skipped_empty": result.skipped_empty,
            "speakers": result.speakers,
            "errors": result.errors,
        }
        return payload

    @app.post("/api/v1/recall")
    async def api_recall(body: dict):
        return await routes["recall"](body)

    @app.get("/api/v1/memories")
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
    ):
        from datetime import datetime as _dt

        after_ts = _dt.fromisoformat(after).timestamp() if after else None
        before_ts = _dt.fromisoformat(before).timestamp() if before else None
        items = memos.list_memories(
            tags=tag,
            require_tags=require_tag,
            exclude_tags=exclude_tag,
            min_importance=min_importance,
            max_importance=max_importance,
            created_after=after_ts,
            created_before=before_ts,
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

    # SSE Streaming Recall endpoint
    @app.get("/api/v1/recall/enriched")
    async def api_recall_enriched(
        q: str,
        top: int = 10,
        filter_tags: str | None = None,
        min_score: float = 0.0,
        filter_after: str | None = None,
        filter_before: str | None = None,
    ):
        """Recall memories and augment them with KG facts."""
        from datetime import datetime as _dt

        tags = [t.strip() for t in filter_tags.split(",") if t.strip()] if filter_tags else None
        after_ts = _dt.fromisoformat(filter_after).timestamp() if filter_after else None
        before_ts = _dt.fromisoformat(filter_before).timestamp() if filter_before else None
        payload = _kg_bridge.recall_enriched(
            q,
            top=top,
            filter_tags=tags,
            min_score=min_score,
            filter_after=after_ts,
            filter_before=before_ts,
        )
        return {"status": "ok", **payload}

    @app.get("/api/v1/recall/stream")
    async def api_recall_stream(
        q: str,
        top: int = 5,
        filter_tags: str | None = None,
        min_score: float = 0.0,
    ):
        """Stream recall results as Server-Sent Events (SSE).

        Each matching memory is sent as a separate SSE event, allowing
        clients to start processing results before the full search completes.

        Query params:
            q: The search query
            top: Maximum results to return (default 5)
            filter_tags: Comma-separated tag filter
            min_score: Minimum relevance score (default 0.0)
        """
        from .sse import sse_stream

        tags = [t.strip() for t in filter_tags.split(",") if t.strip()] if filter_tags else None
        recall_gen = memos.recall_stream(
            query=q, top=top, filter_tags=tags, min_score=min_score,
        )
        return StreamingResponse(
            sse_stream(recall_gen, q),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/v1/prune")
    async def api_prune(body: dict):
        return await routes["prune"](body)

    @app.get("/api/v1/stats")
    async def api_stats():
        return await routes["stats"]()

    @app.get("/api/v1/analytics/summary")
    async def api_analytics_summary(days: int = 7):
        return await routes["analytics_summary"]({"days": days})

    @app.get("/api/v1/analytics/top")
    async def api_analytics_top(n: int = 20):
        return await routes["analytics_top"]({"n": n})

    @app.get("/api/v1/analytics/patterns")
    async def api_analytics_patterns(n: int = 20):
        return await routes["analytics_patterns"]({"n": n})

    @app.get("/api/v1/analytics/latency")
    async def api_analytics_latency():
        return await routes["analytics_latency"]()

    @app.get("/api/v1/analytics/success-rate")
    async def api_analytics_success_rate(days: int = 7):
        return await routes["analytics_success"]({"days": days})

    @app.get("/api/v1/analytics/daily")
    async def api_analytics_daily(days: int = 30):
        return await routes["analytics_daily"]({"days": days})

    @app.get("/api/v1/analytics/zero-result")
    async def api_analytics_zero_result(n: int = 20):
        return await routes["analytics_zero"]({"n": n})

    @app.get("/api/v1/search")
    async def api_search(q: str, limit: int = 20):
        return await routes["search"]({"q": q, "limit": limit})

    @app.delete("/api/v1/memory/{item_id}")
    async def api_delete(item_id: str):
        return await routes["delete_memory"](item_id)

    @app.get("/api/v1/memory/{item_id}")
    async def api_get_memory(item_id: str):
        return await routes["get_memory"](item_id)

    # Auth & rate limiting
    from .auth import APIKeyManager, create_auth_middleware
    from .ratelimit import RateLimiter, create_rate_limit_middleware, DEFAULT_RULES
    key_manager = APIKeyManager.from_env(keys=api_keys)
    app.state.auth_key_manager = key_manager
    key_manager.rate_limiter.max_requests = rate_limit
    if key_manager.auth_enabled:
        app.middleware("http")(create_auth_middleware(key_manager))
    else:
        logger.warning(
            "MemOS API authentication is disabled. Set API_KEY and/or MEMOS_NAMESPACE_KEYS to enable bearer auth."
        )

    # Standalone per-endpoint rate limiter (works with or without auth)
    rate_limiter = RateLimiter(default_max=rate_limit, rules=DEFAULT_RULES)
    app.middleware("http")(create_rate_limit_middleware(rate_limiter))

    @app.post("/api/v1/mine/conversation")
    async def api_mine_conversation(body: dict):
        """Mine a conversation file with speaker attribution.

        Body: {"path": "...", "per_speaker": true, "namespace_prefix": "conv",
               "tags": [...], "importance": 0.55}
        """
        from ..miner.conversation import ConversationMiner
        path = body.get("path", "").strip()
        if not path:
            return {"status": "error", "message": "path is required"}
        from pathlib import Path as _Path
        if not _Path(path).expanduser().exists():
            return {"status": "error", "message": f"File not found: {path}"}
        miner = ConversationMiner(
            memos,
            namespace_prefix=body.get("namespace_prefix", "conv"),
            per_speaker=body.get("per_speaker", True),
            extra_tags=body.get("tags"),
        )
        try:
            result = miner.mine_conversation(
                path,
                tags=body.get("tags"),
                importance=float(body.get("importance", 0.55)),
                per_speaker=body.get("per_speaker"),
            )
            return {
                "status": "ok",
                "imported": result.imported,
                "speakers": result.speakers_detected,
                "turns_total": result.turns_total,
                "skipped_duplicates": result.skipped_duplicates,
                "skipped_empty": result.skipped_empty,
                "memory_ids": result.memory_ids,
                "errors": result.errors,
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # Dashboard
    from ..web import DASHBOARD_HTML

    @app.get("/api/v1/auth/whoami")
    async def api_auth_whoami(request: Request):
        identity = getattr(request.state, "auth_identity", None)
        namespace = getattr(request.state, "namespace", "")
        if identity is None:
            return {
                "status": "ok",
                "auth_enabled": False,
                "mode": "open",
                "namespace": namespace,
                "permissions": ["read", "write", "admin"],
            }
        return {
            "status": "ok",
            "auth_enabled": key_manager.auth_enabled,
            "mode": "master" if identity.is_master else "namespace",
            "name": identity.name,
            "namespace": namespace,
            "permissions": identity.permissions,
        }


    @app.get("/api/v1/classify")
    async def api_classify(text: str):
        """Classify text into memory type tags (zero-LLM)."""
        from ..tagger import AutoTagger
        tagger = AutoTagger()
        tags = tagger.tag(text)
        detailed = tagger.tag_detailed(text)
        return {"status": "ok", "tags": tags, "matches": detailed}

    @app.get("/api/v1/tags")
    async def api_tags(sort: str = "count", limit: int = 0):
        """List all tags with memory counts."""
        tags = memos.list_tags(sort=sort, limit=limit)
        return [{"tag": t, "count": c} for t, c in tags]

    @app.post("/api/v1/tags/rename")
    async def api_tags_rename(body: dict):
        """Rename a tag across all memories."""
        old_tag = body.get("old")
        new_tag = body.get("new")
        if not old_tag or not new_tag:
            return {"error": "Both 'old' and 'new' tag names are required"}
        count = memos.rename_tag(old_tag, new_tag)
        return {"status": "ok", "renamed": count, "old_tag": old_tag, "new_tag": new_tag}

    @app.post("/api/v1/tags/delete")
    async def api_tags_delete(body: dict):
        """Delete a tag from all memories."""
        tag = body.get("tag")
        if not tag:
            return {"error": "Tag name is required"}
        count = memos.delete_tag(tag)
        return {"status": "ok", "deleted": count, "tag": tag}

    # ---- Knowledge Graph endpoints ----

    @app.post("/api/v1/kg/facts")
    async def kg_add_fact(body: dict):
        """Add a triple to the temporal knowledge graph."""
        subject = body.get("subject", "").strip()
        predicate = body.get("predicate", "").strip()
        obj = body.get("object", "").strip()
        if not subject or not predicate or not obj:
            return {"status": "error", "message": "subject, predicate and object are required"}
        try:
            confidence_label = body.get("confidence_label", "EXTRACTED")
            if confidence_label not in KnowledgeGraph.VALID_LABELS:
                return {"status": "error", "message": f"Invalid confidence_label. Must be one of {KnowledgeGraph.VALID_LABELS}"}
            fact_id = _kg.add_fact(
                subject=subject,
                predicate=predicate,
                object=obj,
                valid_from=body.get("valid_from"),
                valid_to=body.get("valid_to"),
                confidence=float(body.get("confidence", 1.0)),
                confidence_label=confidence_label,
                source=body.get("source"),
            )
            return {"status": "ok", "id": fact_id, "confidence_label": confidence_label}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @app.get("/api/v1/kg/query")
    async def kg_query(entity: str, time: Optional[str] = None, direction: str = "both"):
        """Query all active facts linked to an entity at a given time."""
        try:
            facts = _kg.query(entity, time=time, direction=direction)
            return {"status": "ok", "entity": entity, "facts": facts}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @app.get("/api/v1/kg/timeline")
    async def kg_timeline(entity: str):
        """Return chronological timeline of facts about an entity."""
        try:
            facts = _kg.timeline(entity)
            return {"status": "ok", "entity": entity, "timeline": facts}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @app.delete("/api/v1/kg/facts/{fact_id}")
    async def kg_invalidate(fact_id: str):
        """Invalidate (soft-delete) a fact by ID."""
        ok = _kg.invalidate(fact_id)
        return {"status": "ok" if ok else "not_found"}

    @app.get("/api/v1/kg/stats")
    async def kg_stats():
        """Return knowledge graph statistics."""
        return _kg.stats()

    @app.get("/api/v1/kg/labels")
    async def kg_labels(label: Optional[str] = None, active_only: bool = True):
        """Return label stats or facts filtered by confidence label."""
        if label:
            if label not in KnowledgeGraph.VALID_LABELS:
                return {"status": "error", "message": f"Invalid label. Must be one of {KnowledgeGraph.VALID_LABELS}"}
            facts = _kg.query_by_label(label, active_only=active_only)
            return {"status": "ok", "label": label, "facts": facts, "count": len(facts)}
        return {"status": "ok", "label_stats": _kg.label_stats()}

    @app.post("/api/v1/kg/infer")
    async def kg_infer(body: dict):
        """Infer transitive facts for a predicate."""
        predicate = body.get("predicate", "").strip()
        if not predicate:
            return {"status": "error", "message": "predicate is required"}
        try:
            new_ids = _kg.infer_transitive(
                predicate=predicate,
                inferred_predicate=body.get("inferred_predicate"),
                max_depth=int(body.get("max_depth", 3)),
            )
            return {"status": "ok", "inferred_count": len(new_ids), "fact_ids": new_ids}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @app.get("/api/v1/kg/paths")
    async def kg_paths(
        entity_a: str,
        entity_b: str,
        max_hops: int = 3,
        max_paths: int = 10,
    ):
        """Find paths between two entities in the knowledge graph."""
        paths = _kg.find_paths(entity_a, entity_b, max_hops=max_hops, max_paths=max_paths)
        return {
            "entity_a": entity_a,
            "entity_b": entity_b,
            "max_hops": max_hops,
            "paths": [
                {
                    "hops": len(p),
                    "edges": [
                        {
                            "id": t["id"],
                            "subject": t["subject"],
                            "predicate": t["predicate"],
                            "object": t["object"],
                            "confidence": t["confidence"],
                        }
                        for t in p
                    ],
                }
                for p in paths
            ],
            "total": len(paths),
        }

    @app.get("/api/v1/kg/neighbors")
    async def kg_neighbors(
        entity: str,
        depth: int = 1,
        direction: str = "both",
    ):
        """Show entity neighborhood up to N hops."""
        result = _kg.neighbors(entity, depth=depth, direction=direction)
        return {
            "center": result["center"],
            "depth": result["depth"],
            "total_nodes": len(result["nodes"]),
            "total_edges": len(result["edges"]),
            "nodes": result["nodes"],
            "layers": result["layers"],
            "edges": [
                {
                    "id": t["id"],
                    "subject": t["subject"],
                    "predicate": t["predicate"],
                    "object": t["object"],
                    "confidence": t["confidence"],
                }
                for t in result["edges"]
            ],
        }

    @app.post("/api/v1/brain/search")
    async def brain_search(body: dict):
        """Unified search across memories, living wiki pages, and the knowledge graph."""
        from ..brain import BrainSearch

        query = body.get("query", "").strip()
        if not query:
            return {"status": "error", "message": "query is required"}
        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=body.get("wiki_dir"))
            result = searcher.search(
                query,
                top_k=int(body.get("top_k", 10)),
                filter_tags=body.get("tags"),
                min_score=float(body.get("min_score", 0.0)),
                retrieval_mode=body.get("retrieval_mode", "hybrid"),
                max_context_chars=int(body.get("max_context_chars", 2000)),
            )
            payload = result.to_dict()
            payload["status"] = "ok"
            return payload
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ---- End Knowledge Graph ----

    # ---- Palace (P6) ----
    from ..palace import PalaceIndex, PalaceRecall as _PalaceRecall
    if kg_db_path:
        if kg_db_path == ":memory:":
            _palace_db_path = ":memory:"
        else:
            from pathlib import Path as _Path
            _palace_db_path = str(_Path(kg_db_path).parent / "palace.db")
    else:
        _palace_db_path = None
    _palace = PalaceIndex(db_path=_palace_db_path) if _palace_db_path else PalaceIndex()

    @app.get("/api/v1/palace/wings")
    async def palace_list_wings():
        """List all Wings with memory and room counts."""
        return {"status": "ok", "wings": _palace.list_wings()}

    @app.post("/api/v1/palace/wings")
    async def palace_create_wing(body: dict):
        """Create a Wing. Body: {name, description?}"""
        name = body.get("name", "").strip()
        if not name:
            return {"status": "error", "message": "name is required"}
        try:
            wing_id = _palace.create_wing(name, description=body.get("description", ""))
            return {"status": "ok", "id": wing_id, "name": name}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @app.get("/api/v1/palace/rooms")
    async def palace_list_rooms(wing: Optional[str] = None):
        """List Rooms, optionally filtered by wing name."""
        try:
            rooms = _palace.list_rooms(wing_name=wing)
            return {"status": "ok", "rooms": rooms}
        except KeyError as exc:
            return {"status": "error", "message": str(exc)}

    @app.post("/api/v1/palace/rooms")
    async def palace_create_room(body: dict):
        """Create a Room. Body: {wing, name, description?}"""
        wing_name = body.get("wing", "").strip()
        room_name = body.get("name", "").strip()
        if not wing_name or not room_name:
            return {"status": "error", "message": "wing and name are required"}
        try:
            room_id = _palace.create_room(wing_name, room_name, description=body.get("description", ""))
            return {"status": "ok", "id": room_id, "wing": wing_name, "name": room_name}
        except KeyError as exc:
            return {"status": "error", "message": str(exc)}

    @app.post("/api/v1/palace/assign")
    async def palace_assign(body: dict):
        """Assign a memory to a Wing/Room. Body: {memory_id, wing, room?}"""
        memory_id = body.get("memory_id", "").strip()
        wing_name = body.get("wing", "").strip()
        if not memory_id or not wing_name:
            return {"status": "error", "message": "memory_id and wing are required"}
        try:
            _palace.assign(memory_id, wing_name, room_name=body.get("room"))
            return {"status": "ok", "memory_id": memory_id, "wing": wing_name, "room": body.get("room")}
        except KeyError as exc:
            return {"status": "error", "message": str(exc)}

    @app.delete("/api/v1/palace/assign/{memory_id}")
    async def palace_unassign(memory_id: str):
        """Remove a palace assignment."""
        _palace.unassign(memory_id)
        return {"status": "ok", "memory_id": memory_id}

    @app.get("/api/v1/palace/recall")
    async def palace_recall_endpoint(
        query: str,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        top: int = 10,
    ):
        """Scoped recall. Query params: query, wing?, room?, top?"""
        pr = _PalaceRecall(_palace)
        results = pr.palace_recall(memos, query, wing_name=wing, room_name=room, top=top)
        return {
            "status": "ok",
            "results": [
                {
                    "id": r.item.id,
                    "content": r.item.content,
                    "score": round(r.score, 4),
                    "tags": r.item.tags,
                    "match_reason": r.match_reason,
                }
                for r in results
            ],
        }

    @app.get("/api/v1/palace/stats")
    async def palace_stats_endpoint():
        """Palace aggregate statistics."""
        return {"status": "ok", **_palace.stats()}

    # ---- End Palace ----

    # ---- Context Stack (P7) ----
    from ..context import ContextStack as _ContextStack
    _context_stack = _ContextStack(memos)

    @app.get("/api/v1/context/wake-up")
    async def context_wake_up(
        max_chars: int = 2000,
        l1_top: int = 15,
        include_stats: bool = True,
    ):
        """Return L0+L1 context string for session priming.

        Query params:
            max_chars: Maximum characters (default 2000)
            l1_top: Top-N memories by importance (default 15)
            include_stats: Include STATS section (default true)
        """
        output = _context_stack.wake_up(
            max_chars=max_chars,
            l1_top=l1_top,
            include_stats=include_stats,
        )
        return {"status": "ok", "context": output, "chars": len(output)}

    @app.get("/api/v1/context/identity")
    async def context_get_identity():
        """Read the current agent identity (L0)."""
        content = _context_stack.get_identity()
        return {"status": "ok", "identity": content, "exists": bool(content)}

    @app.post("/api/v1/context/identity")
    async def context_set_identity(body: dict):
        """Write the agent identity. Body: {content: string}"""
        content = body.get("content")
        if content is None:
            return {"status": "error", "message": "content is required"}
        _context_stack.set_identity(content)
        return {"status": "ok", "chars": len(content)}

    @app.get("/api/v1/context/for")
    async def context_for_query(
        query: str,
        max_chars: int = 1500,
        top: int = 10,
    ):
        """Return optimised context for a specific query (L0 + L3).

        Query params:
            query: Search query (required)
            max_chars: Maximum characters (default 1500)
            top: Number of semantic results (default 10)
        """
        output = _context_stack.context_for(
            query=query,
            max_chars=max_chars,
            top=top,
        )
        return {"status": "ok", "context": output, "query": query, "chars": len(output)}

    # ---- End Context Stack ----


    @app.get("/api/v1/graph")
    async def api_graph(min_shared_tags: int = 1, limit: int = 500):
        """Return memory graph: nodes + edges based on shared tags."""
        import time as _time
        items = memos._store.list_all(namespace=memos._namespace)
        now = _time.time()

        # Build nodes
        nodes = []
        for item in items[:limit]:
            if item.is_expired:
                continue
            age_days = (now - item.created_at) / 86400
            nodes.append({
                "id": item.id,
                "label": item.content[:60] + ("…" if len(item.content) > 60 else ""),
                "content": item.content,
                "tags": item.tags,
                "importance": item.importance,
                "relevance": item.relevance_score,
                "age_days": round(age_days, 1),
                "access_count": item.access_count,
                "primary_tag": item.tags[0] if item.tags else "__untagged__",
            })

        # Build edges based on shared tags
        edges = []
        tag_to_ids: dict[str, list[str]] = {}
        for n in nodes:
            for tag in n["tags"]:
                tag_to_ids.setdefault(tag, []).append(n["id"])

        seen = set()
        for tag, ids in tag_to_ids.items():
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    key = tuple(sorted([ids[i], ids[j]]))
                    if key not in seen:
                        seen.add(key)
                        edges.append({
                            "source": ids[i],
                            "target": ids[j],
                            "shared_tags": [tag],
                            "weight": 1,
                        })
                    else:
                        # Increment weight for multiple shared tags
                        for e in edges:
                            if e["source"] == key[0] and e["target"] == key[1]:
                                e["weight"] += 1
                                e["shared_tags"].append(tag)
                                break

        if min_shared_tags > 1:
            edges = [e for e in edges if e["weight"] >= min_shared_tags]

        stats = memos.stats()
        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_memories": stats.total_memories,
                "total_tags": stats.total_tags,
            },
        }

    @app.get("/", response_class=HTMLResponse)
    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    # WebSocket endpoint for real-time events
    import asyncio

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        queue = memos.events.add_ws_client()

        async def sender():
            """Background task: send events from queue to WebSocket."""
            try:
                while True:
                    event = await queue.get()
                    await websocket.send_text(event.to_json())
            except Exception:
                pass

        sender_task = asyncio.create_task(sender())
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                try:
                    payload = json.loads(data)
                except Exception:
                    await websocket.send_json({"type": "error", "message": "send JSON subscribe/unsubscribe commands or ping"})
                    continue

                action = payload.get("action")
                event_types = payload.get("event_types")
                tags = payload.get("tags")
                namespace = payload.get("namespace")

                if action in {"subscribe", "update"}:
                    memos.events.update_ws_client(
                        queue,
                        event_types=event_types,
                        namespaces=[namespace] if namespace else None,
                        tags=tags,
                        active=True,
                        label=payload.get("label", ""),
                    )
                    await websocket.send_json({"type": "subscribed", "subscription": memos.events.get_ws_client_subscription(queue)})
                elif action == "unsubscribe":
                    memos.events.update_ws_client(queue, active=False)
                    await websocket.send_json({"type": "unsubscribed", "subscription": memos.events.get_ws_client_subscription(queue)})
                elif action == "list":
                    await websocket.send_json({"type": "subscriptions", "current": memos.events.get_ws_client_subscription(queue), "all": memos.events.list_subscriptions()})
                else:
                    await websocket.send_json({"type": "error", "message": f"unknown action: {action}"})
        except WebSocketDisconnect:
            pass
        finally:
            sender_task.cancel()
            memos.events.remove_ws_client(queue)

    @app.get("/api/v1/events/stream")
    async def event_stream(
        event_types: str | None = None,
        tags: str | None = None,
        namespace: str | None = None,
    ):
        """Stream memory events as SSE with optional filters."""
        from .sse import SSEEvent
        from fastapi.responses import StreamingResponse
        import asyncio as _asyncio

        event_type_list = [t.strip() for t in event_types.split(",") if t.strip()] if event_types else None
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        ns_list = [namespace] if namespace else None
        queue = memos.events.add_ws_client(event_types=event_type_list, namespaces=ns_list, tags=tag_list)

        async def _gen():
            try:
                while True:
                    event = await queue.get()
                    payload = event.to_dict()
                    yield SSEEvent(event=event.type, data=json.dumps(payload), id=str(int(event.timestamp * 1000))).encode()
                    await _asyncio.sleep(0)
            finally:
                memos.events.remove_ws_client(queue)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/v1/events")
    async def event_history(
        event_type: str | None = None,
        limit: int = 50,
        namespace: str | None = None,
        tags: str | None = None,
    ):
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        events = memos.events.get_history(event_type=event_type, limit=limit, namespace=namespace, tags=tag_list)
        return {"events": [e.to_dict() for e in events]}

    @app.get("/api/v1/subscriptions")
    async def list_subscriptions():
        subscriptions = memos.events.list_subscriptions()
        return {"subscriptions": subscriptions, "total": len(subscriptions)}

    @app.delete("/api/v1/subscriptions/{subscription_id}")
    async def delete_subscription(subscription_id: str):
        ok = memos.events.unsubscribe_subscription(subscription_id)
        return {"status": "deleted" if ok else "not_found", "subscription_id": subscription_id}

    @app.get("/api/v1/events/stats")
    async def event_stats():
        return {
            "total_events": memos.events.total_events_emitted,
            "ws_clients": memos.events.client_count,
        }

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": MEMOS_VERSION,
            "auth_enabled": key_manager.auth_enabled,
            "auth_mode": "bearer" if key_manager.auth_enabled else "open",
            "active_keys": key_manager.key_count,
            "master_keys": key_manager.master_key_count,
            "namespace_keys": key_manager.namespace_key_count,
            "rate_limiting": True,
        }

    @app.get("/api/v1/rate-limit/status")
    async def api_rate_limit_status(request):
        """Get current rate limit status for the requesting client."""
        return rate_limiter.get_status(request)

    # Parquet export
    @app.get("/api/v1/export/parquet")
    async def api_export_parquet(include_metadata: bool = True, compression: str = "zstd"):
        """Export all memories as a downloadable Parquet file."""
        import tempfile
        from fastapi.responses import FileResponse

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            result = memos.export_parquet(
                tmp.name,
                include_metadata=include_metadata,
                compression=compression,
            )
            return FileResponse(
                tmp.name,
                media_type="application/octet-stream",
                filename=f"memos-export-{int(time.time())}.parquet",
                headers={"X-Memos-Total": str(result["total"]), "X-Memos-Size": str(result["size_bytes"])},
            )

    # Async consolidation
    @app.post("/api/v1/consolidate")
    async def api_consolidate(body: dict):
        """Run consolidation (sync or async).

        Body:
            async: bool (default False) — run in background.
            similarity_threshold: float (default 0.75).
            merge_content: bool (default False).
            dry_run: bool (default False).
        """
        threshold = body.get("similarity_threshold", 0.75)
        merge = body.get("merge_content", False)
        dry = body.get("dry_run", False)
        is_async = body.get("async", False)

        if is_async:
            handle = await memos.consolidate_async(
                similarity_threshold=threshold,
                merge_content=merge,
                dry_run=dry,
            )
            return {"status": "started", "task_id": handle.task_id}
        else:
            result = memos.consolidate(
                similarity_threshold=threshold,
                merge_content=merge,
                dry_run=dry,
            )
            return {
                "status": "completed",
                "groups_found": result.groups_found,
                "memories_merged": result.memories_merged,
                "space_freed": result.space_freed,
            }

    @app.get("/api/v1/consolidate/{task_id}")
    async def api_consolidate_status(task_id: str):
        """Get status of an async consolidation task."""
        status = memos.consolidation_status(task_id)
        if not status:
            return {"status": "not_found", "task_id": task_id}
        return status

    @app.get("/api/v1/consolidate")
    async def api_consolidate_list():
        """List all async consolidation tasks."""
        return {"tasks": memos.consolidation_tasks()}


    # ── Versioning API ───────────────────────────────────────

    @app.get("/api/v1/memory/{item_id}/history")
    async def api_version_history(item_id: str):
        """Get version history for a memory item."""
        versions = memos.history(item_id)
        return {
            "item_id": item_id,
            "versions": [v.to_dict() for v in versions],
            "total": len(versions),
        }

    @app.get("/api/v1/memory/{item_id}/version/{version_number}")
    async def api_version_get(item_id: str, version_number: int):
        """Get a specific version of a memory item."""
        v = memos.get_version(item_id, version_number)
        if v is None:
            return {"status": "not_found", "item_id": item_id, "version": version_number}
        return {"status": "ok", "version": v.to_dict()}

    @app.get("/api/v1/memory/{item_id}/diff")
    async def api_version_diff(item_id: str, v1: int, v2: int | None = None, latest: bool = False):
        """Diff between two versions. Use ?latest=true for last two versions."""
        if latest:
            result = memos.diff_latest(item_id)
        else:
            if v2 is None:
                return {"status": "error", "message": "Provide v2 or use ?latest=true"}
            result = memos.diff(item_id, v1, v2)
        if result is None:
            return {"status": "not_found", "item_id": item_id}
        return {"status": "ok", "diff": result.to_dict()}

    @app.post("/api/v1/memory/{item_id}/rollback")
    async def api_version_rollback(item_id: str, body: dict):
        """Roll back a memory to a specific version.

        Body: {"version": <int>}
        """
        version = body.get("version")
        if version is None:
            return {"status": "error", "message": "version is required"}
        result = memos.rollback(item_id, version)
        if result is None:
            return {"status": "not_found", "item_id": item_id, "version": version}
        return {
            "status": "ok",
            "item_id": result.id,
            "content": result.content[:200],
            "tags": result.tags,
            "rolled_back_to": version,
        }

    @app.get("/api/v1/snapshot")
    async def api_snapshot(at: float):
        """Get a snapshot of all memories at a given timestamp (epoch)."""
        versions = memos.snapshot_at(at)
        return {
            "timestamp": at,
            "total": len(versions),
            "memories": [v.to_dict() for v in versions[:200]],
        }

    @app.get("/api/v1/recall/at")
    async def api_recall_at(q: str, at: float, top: int = 5, min_score: float = 0.0):
        """Time-travel recall: query memories as they were at a given timestamp."""
        results = memos.recall_at(q, at, top=top, min_score=min_score)
        return {
            "query": q,
            "timestamp": at,
            "total": len(results),
            "results": [
                {
                    "id": r.item.id,
                    "content": r.item.content,
                    "score": round(r.score, 4),
                    "tags": r.item.tags,
                    "match_reason": r.match_reason,
                }
                for r in results
            ],
        }

    @app.get("/api/v1/versioning/stats")
    async def api_versioning_stats():
        """Get versioning statistics."""
        return memos.versioning_stats()

    @app.post("/api/v1/versioning/gc")
    async def api_versioning_gc(body: dict = None):
        """Garbage collect old versions.

        Body: {"max_age_days": 90, "keep_latest": 3}
        """
        body = body or {}
        removed = memos.versioning_gc(
            max_age_days=body.get("max_age_days", 90.0),
            keep_latest=body.get("keep_latest", 3),
        )
        return {"status": "ok", "removed": removed}

    # ── Streaming time-travel recall ──────────────────────────

    @app.get("/api/v1/recall/at/stream")
    async def api_recall_at_stream(q: str, at: float, top: int = 5, min_score: float = 0.0):
        """Stream time-travel recall results as SSE events."""
        from .sse import sse_stream, SSEEvent, format_recall_event, format_done_event
        import asyncio as _asyncio

        results = memos.recall_at(q, at, top=top, min_score=min_score)

        async def _gen():
            for r in results:
                yield r
                await _asyncio.sleep(0)

        return StreamingResponse(
            sse_stream(_gen(), q),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Namespace ACL API ───────────────────────────────────

    @app.post("/api/v1/namespaces/{namespace}/grant")
    async def api_acl_grant(namespace: str, body: dict):
        """Grant an agent access to a namespace.

        Body: {"agent_id": "...", "role": "owner|writer|reader|denied",
               "expires_at": null}
        """
        agent_id = body.get("agent_id")
        role = body.get("role")
        if not agent_id or not role:
            return {"status": "error", "message": "agent_id and role are required"}
        try:
            policy = memos.grant_namespace_access(
                agent_id, namespace, role,
                granted_by=body.get("granted_by", ""),
                expires_at=body.get("expires_at"),
            )
            return {"status": "ok", "policy": policy}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/namespaces/{namespace}/revoke")
    async def api_acl_revoke(namespace: str, body: dict):
        """Revoke an agent's access to a namespace.

        Body: {"agent_id": "..."}
        """
        agent_id = body.get("agent_id")
        if not agent_id:
            return {"status": "error", "message": "agent_id is required"}
        success = memos.revoke_namespace_access(agent_id, namespace)
        return {"status": "revoked" if success else "not_found"}

    @app.get("/api/v1/namespaces/{namespace}/policies")
    async def api_acl_list(namespace: str):
        """List all ACL policies for a namespace."""
        policies = memos.list_namespace_policies(namespace=namespace)
        return {"namespace": namespace, "policies": policies, "total": len(policies)}

    @app.get("/api/v1/namespaces")
    async def api_acl_all_policies():
        """List all ACL policies across all namespaces."""
        policies = memos.list_namespace_policies()
        return {"policies": policies, "total": len(policies)}

    @app.get("/api/v1/namespaces/acl/stats")
    async def api_acl_stats():
        """Get namespace ACL statistics."""
        return memos.namespace_acl_stats()


    # ── Multi-Agent Sharing API ─────────────────────────────

    @app.post("/api/v1/share/offer")
    async def api_share_offer(body: dict):
        """Offer to share memories with another agent.

        Body: {"target_agent": "...", "scope": "items|tag|namespace",
               "scope_key": "", "permission": "read|read_write|admin",
               "expires_at": null}
        """
        from ..sharing.models import ShareScope, SharePermission
        try:
            scope = ShareScope(body.get("scope", "items"))
            permission = SharePermission(body.get("permission", "read"))
        except ValueError as e:
            return {"status": "error", "message": str(e)}
        try:
            req = memos.share_with(
                body["target_agent"],
                scope=scope,
                scope_key=body.get("scope_key", ""),
                permission=permission,
                expires_at=body.get("expires_at"),
            )
            return {"status": "ok", "share": req.to_dict()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/share/{share_id}/accept")
    async def api_share_accept(share_id: str):
        """Accept a pending share."""
        try:
            req = memos.accept_share(share_id)
            return {"status": "ok", "share": req.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/share/{share_id}/reject")
    async def api_share_reject(share_id: str):
        """Reject a pending share."""
        try:
            req = memos.reject_share(share_id)
            return {"status": "ok", "share": req.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/share/{share_id}/revoke")
    async def api_share_revoke(share_id: str):
        """Revoke a share."""
        try:
            req = memos.revoke_share(share_id)
            return {"status": "ok", "share": req.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.get("/api/v1/share/{share_id}/export")
    async def api_share_export(share_id: str):
        """Export memories for an accepted share as a JSON envelope."""
        try:
            envelope = memos.export_shared(share_id)
            return {"status": "ok", "envelope": envelope.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/v1/share/import")
    async def api_share_import(body: dict):
        """Import memories from a received envelope.

        Body: {"envelope": {"source_agent": "...", "target_agent": "...", "memories": [...]}}
        """
        from ..sharing.models import MemoryEnvelope
        try:
            envelope = MemoryEnvelope.from_dict(body["envelope"])
            learned = memos.import_shared(envelope)
            return {
                "status": "ok",
                "imported": len(learned),
                "ids": [i.id for i in learned],
            }
        except (ValueError, KeyError) as e:
            return {"status": "error", "message": str(e)}

    @app.get("/api/v1/shares")
    async def api_shares_list(agent: str | None = None, status: str | None = None):
        """List shares, optionally filtered."""
        from ..sharing.models import ShareStatus as SS
        st = SS(status) if status else None
        shares = memos.list_shares(agent=agent, status=st)
        return {
            "shares": [s.to_dict() for s in shares],
            "total": len(shares),
        }

    @app.get("/api/v1/sharing/stats")
    async def api_sharing_stats():
        """Get sharing statistics."""
        return memos.sharing_stats()


    # ── Relevance Feedback API ──────────────────────────────

    @app.post("/api/v1/feedback")
    async def api_record_feedback(body: dict):
        """Record relevance feedback for a recalled memory.

        Body: {"item_id": "...", "feedback": "relevant|not-relevant",
               "query": "", "score_at_recall": 0.0, "agent_id": ""}
        """
        item_id = body.get("item_id")
        feedback = body.get("feedback")
        if not item_id or not feedback:
            return {"status": "error", "message": "item_id and feedback are required"}
        try:
            entry = memos.record_feedback(
                item_id=item_id,
                feedback=feedback,
                query=body.get("query", ""),
                score_at_recall=body.get("score_at_recall", 0.0),
                agent_id=body.get("agent_id", ""),
            )
            return {"status": "ok", "feedback": entry.to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @app.get("/api/v1/feedback")
    async def api_list_feedback(item_id: str | None = None, limit: int = 100):
        """List feedback entries, optionally filtered by item_id."""
        entries = memos.get_feedback(item_id=item_id, limit=limit)
        return {
            "feedback": [e.to_dict() for e in entries],
            "total": len(entries),
        }

    @app.get("/api/v1/feedback/stats")
    async def api_feedback_stats():
        """Get aggregate feedback statistics."""
        stats = memos.feedback_stats()
        return stats.to_dict()

    # ── Decay & Reinforce API ──────────────────────────────

    @app.post("/api/v1/decay/run")
    async def api_decay_run(body: dict = None):
        """Run importance decay on all memories.

        Body (optional): {"dry_run": true, "min_age_days": 7, "floor": 0.1}
        """
        body = body or {}
        items = memos._store.list_all(namespace=memos._namespace)
        report = memos._decay.run_decay(
            items,
            min_age_days=body.get("min_age_days"),
            floor=body.get("floor"),
            dry_run=body.get("dry_run", True),
        )
        if not body.get("dry_run", True):
            for item in items:
                memos._store.upsert(item, namespace=memos._namespace)
        return {
            "status": "ok",
            "total": report.total,
            "decayed": report.decayed,
            "avg_importance_before": round(report.avg_importance_before, 4),
            "avg_importance_after": round(report.avg_importance_after, 4),
            "details": report.details[:50],
        }

    @app.post("/api/v1/memories/{memory_id}/reinforce")
    async def api_reinforce(memory_id: str, body: dict = None):
        """Boost a memory's importance.

        Body (optional): {"strength": 0.05}
        """
        body = body or {}
        item = memos._store.get(memory_id, namespace=memos._namespace)
        if item is None:
            return {"status": "error", "message": f"Memory not found: {memory_id}"}
        old_imp = item.importance
        new_imp = memos._decay.reinforce(item, strength=body.get("strength"))
        memos._store.upsert(item, namespace=memos._namespace)
        return {
            "status": "ok",
            "id": item.id,
            "importance_before": round(old_imp, 4),
            "importance_after": round(new_imp, 4),
        }

    @app.post("/api/v1/compress")
    async def api_compress(body: dict = None):
        """Compress very low-importance memories into aggregate summaries.

        Body (optional): {"threshold": 0.1, "dry_run": true}
        """
        body = body or {}
        result = memos.compress(
            threshold=float(body.get("threshold", 0.1)),
            dry_run=bool(body.get("dry_run", True)),
        )
        return {
            "status": "ok",
            "compressed_count": result.compressed_count,
            "summary_count": result.summary_count,
            "freed_bytes": result.freed_bytes,
            "groups_considered": result.groups_considered,
            "details": result.details,
        }


    # ── Sync & Conflict Resolution API (P12) ──────────────────────────

    @app.post("/api/v1/sync/check")
    async def api_sync_check(body: dict):
        """Check for conflicts between local store and a remote envelope.

        Body: {"envelope": {"source_agent": "...", "target_agent": "...", "memories": [...]}}
        """
        from ..conflict import ConflictDetector
        from ..sharing.models import MemoryEnvelope
        try:
            envelope = MemoryEnvelope.from_dict(body["envelope"])
        except (KeyError, ValueError) as exc:
            return {"status": "error", "message": f"Invalid envelope: {exc}"}
        if not envelope.validate():
            return {"status": "error", "message": "Envelope checksum validation failed"}
        detector = ConflictDetector()
        report = detector.detect(memos, envelope)
        return {"status": "ok", **report.to_dict()}

    @app.post("/api/v1/sync/apply")
    async def api_sync_apply(body: dict):
        """Apply remote memories with conflict resolution.

        Body: {"envelope": {...}, "strategy": "local_wins|remote_wins|merge|manual",
               "dry_run": false}
        """
        from ..conflict import ConflictDetector, ResolutionStrategy
        from ..sharing.models import MemoryEnvelope
        try:
            envelope = MemoryEnvelope.from_dict(body["envelope"])
        except (KeyError, ValueError) as exc:
            return {"status": "error", "message": f"Invalid envelope: {exc}"}
        if not envelope.validate():
            return {"status": "error", "message": "Envelope checksum validation failed"}
        strategy_name = body.get("strategy", "merge")
        try:
            strategy = ResolutionStrategy(strategy_name)
        except ValueError:
            return {"status": "error", "message": f"Invalid strategy: {strategy_name}. Use: local_wins, remote_wins, merge, manual"}
        detector = ConflictDetector()
        report = detector.detect(memos, envelope)
        if body.get("dry_run", False):
            detector.resolve(report.conflicts, strategy)
            result = report.to_dict()
            result["dry_run"] = True
            return {"status": "ok", **result}
        report = detector.apply(memos, report, strategy)
        return {"status": "ok", **report.to_dict()}


    # ── MCP Streamable HTTP (universal — OpenClaw, Claude Code, Cursor, …) ──
    from ..mcp_server import add_mcp_routes as _add_mcp
    _add_mcp(app, memos)

    return app
