"""Memory tag and classification routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import TagDeleteRequest, TagRenameRequest


def register_memory_tag_routes(router: APIRouter, memos) -> None:
    """Register tag management and classification endpoints."""

    @router.get("/api/v1/classify")
    async def api_classify(text: str) -> dict:
        from ...tagger import AutoTagger

        tagger = AutoTagger()
        return {"status": "ok", "tags": tagger.tag(text), "matches": tagger.tag_detailed(text)}

    @router.get("/api/v1/tags", response_model=None)
    async def api_tags(sort: str = "count", limit: int = 0) -> list[dict]:
        tags = memos.list_tags(sort=sort, limit=limit)
        return [{"tag": tag, "count": count} for tag, count in tags]

    @router.post("/api/v1/tags/rename")
    async def api_tags_rename(req: TagRenameRequest) -> dict:
        return {"status": "ok", "renamed": memos.rename_tag(req.old, req.new), "old_tag": req.old, "new_tag": req.new}

    @router.post("/api/v1/tags/delete")
    async def api_tags_delete(req: TagDeleteRequest) -> dict:
        return {"status": "ok", "deleted": memos.delete_tag(req.tag), "tag": req.tag}
