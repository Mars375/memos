"""Characterization tests for splitting knowledge API routes into focused modules."""

from __future__ import annotations

from memos.context import ContextStack
from memos.core import MemOS
from memos.knowledge_graph import KnowledgeGraph
from memos.palace import PalaceIndex


def _paths(router) -> set[str]:
    return {route.path for route in router.routes}


def test_split_route_modules_expose_expected_paths(tmp_path):
    from memos.api.routes.brain import create_brain_router
    from memos.api.routes.context import create_context_router
    from memos.api.routes.kg import create_kg_router
    from memos.api.routes.palace import create_palace_router
    from memos.api.routes.wiki import create_wiki_router

    memos = MemOS(backend="memory")
    kg = KnowledgeGraph(db_path=":memory:")
    palace = PalaceIndex(db_path=":memory:")
    context = ContextStack(memos, identity_path=str(tmp_path / "identity.txt"))

    try:
        assert {
            "/api/v1/kg/facts",
            "/api/v1/kg/query",
            "/api/v1/kg/timeline",
            "/api/v1/kg/stats",
            "/api/v1/kg/communities",
        }.issubset(_paths(create_kg_router(kg)))

        assert {
            "/api/v1/brain/search",
            "/api/v1/brain/entity/{name}",
            "/api/v1/brain/connections",
            "/api/v1/brain/suggestions",
        }.issubset(_paths(create_brain_router(memos, kg)))

        assert {
            "/api/v1/palace/wings",
            "/api/v1/palace/rooms",
            "/api/v1/palace/assign",
            "/api/v1/palace/agents",
        }.issubset(_paths(create_palace_router(memos, palace)))

        assert {
            "/api/v1/context/wake-up",
            "/api/v1/context/identity",
            "/api/v1/context/for",
            "/api/v1/graph",
        }.issubset(_paths(create_context_router(memos, context)))

        assert {
            "/api/v1/wiki/pages",
            "/api/v1/wiki/page/{slug}",
            "/api/v1/wiki/index",
            "/api/v1/wiki/log",
        }.issubset(_paths(create_wiki_router(memos)))
    finally:
        kg.close()
        palace.close()
