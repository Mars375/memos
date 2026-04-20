"""Memory CRUD, recall, lifecycle, sync, and export route wiring."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import (
    BatchLearnRequest,
    CompressRequest,
    ConsolidateRequest,
    DecayRunRequest,
    DedupCheckRequest,
    DedupScanRequest,
    FeedbackRequest,
    LearnExtractRequest,
    LearnRequest,
    PruneRequest,
    RecallRequest,
    ReinforceRequest,
    RollbackRequest,
    SyncApplyRequest,
    SyncCheckRequest,
    TagDeleteRequest,
    TagRenameRequest,
    VersioningGCRequest,
)
from ._memory_learn import register_memory_learn_routes
from ._memory_maintenance import register_memory_maintenance_routes
from ._memory_recall import register_memory_recall_routes
from ._memory_sync import register_memory_sync_routes
from ._memory_versioning import register_memory_versioning_routes

__all__ = [
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
]


def create_memory_router(memos, kg_bridge) -> APIRouter:
    """Create the composed memory API router."""
    router = APIRouter()
    register_memory_learn_routes(router, memos, kg_bridge)
    register_memory_recall_routes(router, memos, kg_bridge)
    register_memory_maintenance_routes(router, memos)
    register_memory_versioning_routes(router, memos)
    register_memory_sync_routes(router, memos, kg_bridge)
    return router
