"""Ingest and conversation mining admin routes."""

from __future__ import annotations

import logging
import os
import tempfile

from fastapi import APIRouter

from ..schemas import IngestURLRequest, MineConversationRequest

logger = logging.getLogger(__name__)


def register_admin_ingest_routes(router: APIRouter, memos, conversation_mine_lock) -> None:
    """Register ingest URL and conversation mining endpoints."""

    @router.post("/api/v1/ingest/url")
    async def api_ingest_url(body: IngestURLRequest):
        """Fetch a URL and ingest it into memory."""
        result = memos.ingest_url(
            body.url,
            tags=body.tags,
            importance=body.importance,
            max_chunk=body.max_chunk,
            dry_run=body.dry_run,
        )
        head_meta = result.chunks[0].get("metadata", {}) if result.chunks else {}
        payload = {
            "status": "ok" if not result.errors else "partial",
            "url": body.url,
            "total_chunks": result.total_chunks,
            "skipped": result.skipped,
            "errors": result.errors,
            "source_type": head_meta.get("source_type"),
            "title": head_meta.get("title"),
        }
        if body.dry_run:
            payload["chunks"] = result.chunks
        return payload

    @router.post("/api/v1/mine/conversation")
    async def api_mine_conversation(body: MineConversationRequest):
        """Mine a conversation transcript. Accepts text or server-side path."""
        import asyncio

        from ...ingest.conversation import ConversationMiner

        text_body = body.text or body.content or ""
        path_body = body.path or ""

        per_speaker = body.per_speaker
        namespace_prefix = body.namespace_prefix
        extra_tags = body.tags or []
        importance = body.importance
        dry_run = body.dry_run

        def _blocking_mine():
            miner = ConversationMiner(memos, dry_run=dry_run)
            if text_body:
                try:
                    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="memos_conv_")
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        fh.write(text_body)
                    return miner.mine_conversation(
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
                        logger.debug("Temp file cleanup failed for %s", tmp_path, exc_info=True)
            return miner.mine_conversation(
                path_body,
                namespace_prefix=namespace_prefix,
                per_speaker=per_speaker,
                tags=extra_tags or None,
                importance=importance,
            )

        async with conversation_mine_lock:
            result = await asyncio.to_thread(_blocking_mine)
        return {
            "status": "ok" if not result.errors else "partial",
            "imported": result.imported,
            "skipped_duplicates": result.skipped_duplicates,
            "skipped_empty": result.skipped_empty,
            "speakers": result.speakers,
            "errors": result.errors,
        }
