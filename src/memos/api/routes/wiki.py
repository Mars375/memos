"""Living wiki API routes."""

from __future__ import annotations

from fastapi import APIRouter

from ...wiki_living import LivingWikiEngine
from ..errors import error_response, handle_exception, not_found
from ..schemas import WikiCreatePageRequest


def create_wiki_router(memos) -> APIRouter:
    """Create living-wiki routes."""
    router = APIRouter()
    wiki = LivingWikiEngine(memos)

    @router.get("/api/v1/wiki/pages")
    async def wiki_list_pages():
        try:
            pages = wiki.list_pages()
            return {
                "status": "ok",
                "pages": [
                    {
                        "name": p.entity,
                        "slug": p.slug,
                        "memory_count": p.memory_count,
                        "updated_at": p.updated_at,
                    }
                    for p in pages
                ],
                "total": len(pages),
            }
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="wiki_list_pages")

    @router.post("/api/v1/wiki/pages")
    async def wiki_create_page(body: WikiCreatePageRequest):
        try:
            result = wiki.create_page(entity=body.entity, entity_type=body.entity_type, content=body.content)
            return {**result}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="wiki_create_page")

    @router.get("/api/v1/wiki/page/{slug}")
    async def wiki_read_page(slug: str):
        try:
            content = wiki.read_page(slug)
            if content is None:
                content = wiki.read_page(slug.replace("-", " "))
            if content is None:
                return not_found(f"Wiki page '{slug}' not found")
            return {"status": "ok", "slug": slug, "content": content}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="wiki_read_page")

    @router.get("/api/v1/wiki/search")
    async def wiki_search_pages(q: str):
        try:
            results = wiki.search(q)
            return {"status": "ok", "results": results, "query": q}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="wiki_search_pages")

    @router.get("/api/v1/wiki/index")
    async def wiki_get_index():
        try:
            content = wiki.generate_index()
            return {"status": "ok", "content": content}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="wiki_get_index")

    @router.post("/api/v1/wiki/regenerate-index")
    async def wiki_regenerate_index():
        try:
            content = wiki.regenerate_index()
            return {"status": "ok", "content": content}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="wiki_regenerate_index")

    @router.get("/api/v1/wiki/lint")
    async def wiki_lint():
        try:
            report = wiki.lint_report()
            return {"status": "ok", **report}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="wiki_lint")

    @router.get("/api/v1/wiki/log")
    async def wiki_get_log():
        try:
            content = wiki.get_log_markdown()
            return {"status": "ok", "content": content}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:
            return handle_exception(exc, context="wiki_get_log")

    return router
