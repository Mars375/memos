"""Sync memory routes and export route aggregation."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..errors import error_response
from ..schemas import SyncApplyRequest, SyncCheckRequest
from ._memory_export import register_memory_export_routes


def register_memory_sync_routes(router: APIRouter, memos, kg_bridge) -> None:
    """Register sync and export endpoints."""

    @router.post("/api/v1/sync/check", response_model=None)
    async def api_sync_check(req: SyncCheckRequest) -> dict | JSONResponse:
        from ...conflict import ConflictDetector
        from ...sharing.models import MemoryEnvelope

        try:
            envelope = MemoryEnvelope.from_dict(req.envelope)
        except (KeyError, ValueError):
            return error_response("Invalid envelope format", status_code=400)
        if not envelope.validate():
            return error_response("Envelope checksum validation failed", status_code=400)
        detector = ConflictDetector()
        return {"status": "ok", **detector.detect(memos, envelope).to_dict()}

    @router.post("/api/v1/sync/apply", response_model=None)
    async def api_sync_apply(req: SyncApplyRequest) -> dict | JSONResponse:
        from ...conflict import ConflictDetector, ResolutionStrategy
        from ...sharing.models import MemoryEnvelope

        try:
            envelope = MemoryEnvelope.from_dict(req.envelope)
        except (KeyError, ValueError):
            return error_response("Invalid envelope format", status_code=400)
        if not envelope.validate():
            return error_response("Envelope checksum validation failed", status_code=400)
        try:
            strategy = ResolutionStrategy(req.strategy)
        except ValueError:
            return error_response("Invalid strategy. Use: local_wins, remote_wins, merge, manual", status_code=400)
        detector = ConflictDetector()
        report = detector.detect(memos, envelope)
        if req.dry_run:
            detector.resolve(report.conflicts, strategy)
            return {"status": "ok", "dry_run": True, **report.to_dict()}
        return {"status": "ok", **detector.apply(memos, report, strategy).to_dict()}

    register_memory_export_routes(router, memos, kg_bridge)
