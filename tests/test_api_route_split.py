"""Characterization tests for splitting knowledge API routes into focused modules."""

from __future__ import annotations

import importlib

from memos.api import create_fastapi_app
from memos.context import ContextStack
from memos.core import MemOS
from memos.kg_bridge import KGBridge
from memos.knowledge_graph import KnowledgeGraph
from memos.palace import PalaceIndex


def _paths(router) -> set[str]:
    return {route.path for route in router.routes}


EXPECTED_MEMORY_API_PATHS = {
    "/api/v1/learn",
    "/api/v1/learn/extract",
    "/api/v1/learn/batch",
    "/api/v1/recall",
    "/api/v1/memories",
    "/api/v1/recall/enriched",
    "/api/v1/recall/stream",
    "/api/v1/search",
    "/api/v1/memory/{item_id}",
    "/api/v1/recall/at",
    "/api/v1/recall/at/stream",
    "/api/v1/prune",
    "/api/v1/classify",
    "/api/v1/tags",
    "/api/v1/tags/rename",
    "/api/v1/tags/delete",
    "/api/v1/consolidate",
    "/api/v1/consolidate/{task_id}",
    "/api/v1/feedback",
    "/api/v1/feedback/stats",
    "/api/v1/decay/run",
    "/api/v1/memories/{memory_id}/reinforce",
    "/api/v1/compress",
    "/api/v1/dedup/check",
    "/api/v1/dedup/scan",
    "/api/v1/memory/{item_id}/history",
    "/api/v1/memory/{item_id}/version/{version_number}",
    "/api/v1/memory/{item_id}/diff",
    "/api/v1/memory/{item_id}/rollback",
    "/api/v1/snapshot",
    "/api/v1/versioning/stats",
    "/api/v1/versioning/gc",
    "/api/v1/sync/check",
    "/api/v1/sync/apply",
    "/api/v1/export/markdown",
    "/api/v1/export/parquet",
}


EXPECTED_MEMORY_EXPORTS = {
    "BatchLearnRequest",
    "CompressRequest",
    "ConsolidateRequest",
    "DecayRunRequest",
    "DedupCheckRequest",
    "DedupScanRequest",
    "FeedbackRequest",
    "LearnExtractRequest",
    "LearnRequest",
    "PruneRequest",
    "RecallRequest",
    "ReinforceRequest",
    "RollbackRequest",
    "SyncApplyRequest",
    "SyncCheckRequest",
    "TagDeleteRequest",
    "TagRenameRequest",
    "VersioningGCRequest",
    "create_memory_router",
}


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


def test_memory_router_exposes_expected_paths():
    from memos.api.routes.memory import create_memory_router

    memos = MemOS(backend="memory")
    kg_bridge = KGBridge(memos, KnowledgeGraph(db_path=":memory:"))
    try:
        assert EXPECTED_MEMORY_API_PATHS.issubset(_paths(create_memory_router(memos, kg_bridge)))
    finally:
        kg_bridge.close()


def test_fastapi_app_exposes_expected_memory_paths():
    memos = MemOS(backend="memory")
    app = create_fastapi_app(memos=memos, kg_db_path=":memory:")

    assert EXPECTED_MEMORY_API_PATHS.issubset(_paths(app))


def test_memory_module_preserves_public_exports():
    memory_module = importlib.import_module("memos.api.routes.memory")

    assert EXPECTED_MEMORY_EXPORTS.issubset(set(memory_module.__all__))
    for export_name in EXPECTED_MEMORY_EXPORTS:
        assert hasattr(memory_module, export_name)


def test_memory_compatibility_modules_remain_importable():
    for module_name in (
        "memos.api.routes._memory_recall",
        "memos.api.routes._memory_maintenance",
        "memos.api.routes._memory_sync",
    ):
        assert importlib.import_module(module_name)
