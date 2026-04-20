"""Brain search API routes."""

from __future__ import annotations

from fastapi import APIRouter

from ...utils import validate_safe_path
from ..errors import error_response, handle_exception
from ..schemas import BrainSearchRequest


def _validate_wiki_dir(wiki_dir: str | None) -> str | None:
    """Validate wiki_dir or return None; raises ValueError on traversal."""
    if wiki_dir is None:
        return None
    return validate_safe_path(wiki_dir)


def create_brain_router(memos, _kg) -> APIRouter:
    """Create brain-search routes."""
    router = APIRouter()

    @router.post("/api/v1/brain/search")
    async def brain_search(body: BrainSearchRequest):
        from ...brain import BrainSearch

        try:
            safe_dir = _validate_wiki_dir(body.wiki_dir)
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=safe_dir)
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
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="brain_search")

    @router.get("/api/v1/brain/entity/{name}")
    async def brain_entity_detail(
        name: str, top_memories: int = 5, neighbor_limit: int = 12, wiki_dir: str | None = None
    ):
        from ...brain import BrainSearch

        try:
            safe_dir = _validate_wiki_dir(wiki_dir)
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=safe_dir)
            detail = searcher.entity_detail(name, top_memories=top_memories, neighbor_limit=neighbor_limit)
            payload = detail.to_dict()
            payload["status"] = "ok"
            return payload
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="brain_entity_detail")

    @router.get("/api/v1/brain/entity/{name}/subgraph")
    async def brain_entity_subgraph(name: str, depth: int = 2, wiki_dir: str | None = None):
        from ...brain import BrainSearch

        try:
            safe_dir = _validate_wiki_dir(wiki_dir)
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=safe_dir)
            subgraph = searcher.entity_subgraph(name, depth=depth)
            return {
                "status": "ok",
                "entity": subgraph.center,
                "depth": subgraph.depth,
                "nodes": subgraph.nodes,
                "edges": subgraph.edges,
                "layers": subgraph.layers,
            }
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="brain_entity_subgraph")

    @router.get("/api/v1/brain/connections")
    async def brain_surprising_connections(top: int = 5, wiki_dir: str | None = None):
        from ...brain import BrainSearch

        try:
            safe_dir = _validate_wiki_dir(wiki_dir)
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=safe_dir)
            connections = searcher.surprising_connections(top_n=top)
            return {"status": "ok", "connections": connections, "total": len(connections)}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="brain_surprising_connections")

    @router.get("/api/v1/brain/suggest")
    async def brain_suggest(top_k: int = 5, wiki_dir: str | None = None):
        from ...brain import BrainSearch

        try:
            safe_dir = _validate_wiki_dir(wiki_dir)
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=safe_dir)
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
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="brain_suggest")

    @router.get("/api/v1/brain/suggestions")
    async def brain_suggestions(n: int = 5, wiki_dir: str | None = None):
        from ...brain import BrainSearch

        try:
            safe_dir = _validate_wiki_dir(wiki_dir)
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=safe_dir)
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
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="brain_suggestions")

    return router
