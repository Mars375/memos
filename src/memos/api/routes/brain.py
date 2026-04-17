"""Brain search API routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..errors import handle_exception
from ..schemas import BrainSearchRequest


def create_brain_router(memos, _kg) -> APIRouter:
    """Create brain-search routes."""
    router = APIRouter()

    @router.post("/api/v1/brain/search")
    async def brain_search(body: BrainSearchRequest):
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=body.wiki_dir)
            result = searcher.search(
                body.query,
                top_k=body.top_k,
                filter_tags=body.tags,
                min_score=body.min_score,
                retrieval_mode=body.retrieval_mode,
                max_context_chars=body.max_context_chars,
                auto_file=body.auto_file,
            )
            payload = result.to_dict()
            payload["status"] = "ok"
            return payload
        except Exception as exc:
            return handle_exception(exc, context="brain_search")

    @router.get("/api/v1/brain/entity/{name}")
    async def brain_entity_detail(
        name: str, top_memories: int = 5, neighbor_limit: int = 12, wiki_dir: str | None = None
    ):
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            detail = searcher.entity_detail(name, top_memories=top_memories, neighbor_limit=neighbor_limit)
            payload = detail.to_dict()
            payload["status"] = "ok"
            return payload
        except Exception as exc:
            return handle_exception(exc, context="brain_entity_detail")

    @router.get("/api/v1/brain/entity/{name}/subgraph")
    async def brain_entity_subgraph(name: str, depth: int = 2, wiki_dir: str | None = None):
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            subgraph = searcher.entity_subgraph(name, depth=depth)
            return {
                "status": "ok",
                "entity": subgraph.center,
                "depth": subgraph.depth,
                "nodes": subgraph.nodes,
                "edges": subgraph.edges,
                "layers": subgraph.layers,
            }
        except Exception as exc:
            return handle_exception(exc, context="brain_entity_subgraph")

    @router.get("/api/v1/brain/connections")
    async def brain_surprising_connections(top: int = 5, wiki_dir: str | None = None):
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            connections = searcher.surprising_connections(top_n=top)
            return {"status": "ok", "connections": connections, "total": len(connections)}
        except Exception as exc:
            return handle_exception(exc, context="brain_surprising_connections")

    @router.get("/api/v1/brain/suggest")
    async def brain_suggest(top_k: int = 5, wiki_dir: str | None = None):
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            suggestions = searcher.suggest_questions(top_k=top_k)
            return {
                "status": "ok",
                "suggestions": [
                    {
                        "question": sq.question,
                        "category": sq.category,
                        "score": sq.score,
                        "entities": sq.entities,
                    }
                    for sq in suggestions
                ],
                "total": len(suggestions),
            }
        except Exception as exc:
            return handle_exception(exc, context="brain_suggest")

    @router.get("/api/v1/brain/suggestions")
    async def brain_suggestions(n: int = 5, wiki_dir: str | None = None):
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            suggestions = searcher.suggest_questions(top_k=n)
            return {
                "status": "ok",
                "questions": [sq.question for sq in suggestions],
                "details": [
                    {
                        "question": sq.question,
                        "category": sq.category,
                        "score": sq.score,
                        "entities": sq.entities,
                    }
                    for sq in suggestions
                ],
                "total": len(suggestions),
            }
        except Exception as exc:
            return handle_exception(exc, context="brain_suggestions")

    return router
