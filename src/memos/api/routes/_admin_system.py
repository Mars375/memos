"""Health, rate-limit, namespace ACL, sharing, and dashboard admin routes."""

from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..errors import error_response, not_found
from ..schemas import (
    ACLGrantRequest,
    ACLRevokeRequest,
    ShareImportRequest,
    ShareOfferRequest,
)

# Module-level start time for uptime calculation
_start_time: float = time.time()


def register_admin_system_routes(
    router: APIRouter,
    memos,
    key_manager,
    rate_limiter,
    MEMOS_VERSION: str,
    DASHBOARD_HTML: str,
) -> None:
    """Register health, rate-limit, ACL, sharing, and dashboard routes."""

    # ── Dashboard ─────────────────────────────────────────────

    @router.get("/", response_class=HTMLResponse)
    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    # ── Health & Rate Limit ───────────────────────────────────

    @router.get("/health")
    async def health():
        """Public liveness probe — intentionally minimal.

        Auth state (whether keys are configured, how many) is NOT exposed.
        See ``/api/v1/health`` for the full readiness probe.
        """
        return {
            "status": "ok",
            "version": MEMOS_VERSION,
        }

    @router.get("/api/v1/health")
    async def api_v1_health():
        """Health check with version, uptime, and auth state."""
        uptime = time.time() - _start_time
        try:
            import importlib.metadata

            version = importlib.metadata.version("memos")
        except (importlib.metadata.PackageNotFoundError, ValueError):
            version = MEMOS_VERSION
        return {
            "status": "ok",
            "version": version,
            "uptime": round(uptime, 2),
            "auth_enabled": key_manager.auth_enabled,
            "active_keys": key_manager.key_count,
        }

    @router.get("/api/v1/rate-limit/status")
    async def api_rate_limit_status(request):
        return rate_limiter.get_status(request)

    # ── Namespace ACL ─────────────────────────────────────────

    @router.post("/api/v1/namespaces/{namespace}/grant")
    async def api_acl_grant(namespace: str, body: ACLGrantRequest):
        try:
            policy = memos.grant_namespace_access(
                body.agent_id,
                namespace,
                body.role,
                granted_by=body.granted_by,
                expires_at=body.expires_at,
            )
            return {"status": "ok", "policy": policy}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)

    @router.post("/api/v1/namespaces/{namespace}/revoke")
    async def api_acl_revoke(namespace: str, body: ACLRevokeRequest):
        revoked = memos.revoke_namespace_access(body.agent_id, namespace)
        if not revoked:
            return not_found(f"No access found for {body.agent_id}")
        return {"status": "ok", "revoked": body.agent_id}

    @router.get("/api/v1/namespaces/{namespace}/policies")
    async def api_acl_list(namespace: str):
        policies = memos.list_namespace_policies(namespace=namespace)
        return {"namespace": namespace, "policies": policies, "total": len(policies)}

    @router.get("/api/v1/namespaces")
    async def api_acl_all_policies():
        policies = memos.list_namespace_policies()
        return {"policies": policies, "total": len(policies)}

    @router.get("/api/v1/namespaces/acl/stats")
    async def api_acl_stats():
        return memos.namespace_acl_stats()

    # ── Multi-Agent Sharing ───────────────────────────────────

    @router.post("/api/v1/share/offer")
    async def api_share_offer(body: ShareOfferRequest):
        from ...sharing.models import SharePermission, ShareScope

        scope = ShareScope(body.scope)
        permission = SharePermission(body.permission)
        try:
            req = memos.share_with(
                body.target_agent,
                scope=scope,
                scope_key=body.scope_key,
                permission=permission,
                expires_at=body.expires_at,
            )
            return {"status": "ok", "share": req.to_dict()}
        except ValueError as exc:
            return error_response(str(exc), status_code=400)

    @router.post("/api/v1/share/{share_id}/accept")
    async def api_share_accept(share_id: str):
        try:
            return {"status": "ok", "share": memos.accept_share(share_id).to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/v1/share/{share_id}/reject")
    async def api_share_reject(share_id: str):
        try:
            return {"status": "ok", "share": memos.reject_share(share_id).to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/v1/share/{share_id}/revoke")
    async def api_share_revoke(share_id: str):
        try:
            return {"status": "ok", "share": memos.revoke_share(share_id).to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.get("/api/v1/share/{share_id}/export")
    async def api_share_export(share_id: str):
        try:
            return {"status": "ok", "envelope": memos.export_shared(share_id).to_dict()}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/v1/share/import")
    async def api_share_import(body: ShareImportRequest):
        from ...sharing.models import MemoryEnvelope

        try:
            envelope = MemoryEnvelope.from_dict(body.envelope)
            learned = memos.import_shared(envelope)
            return {"status": "ok", "imported": len(learned), "ids": [i.id for i in learned]}
        except (ValueError, KeyError) as exc:
            return error_response(str(exc), status_code=400)

    @router.get("/api/v1/shares")
    async def api_shares_list(agent: str | None = None, status: str | None = None):
        from ...sharing.models import ShareStatus as SS

        st = SS(status) if status else None
        shares = memos.list_shares(agent=agent, status=st)
        return {"shares": [s.to_dict() for s in shares], "total": len(shares)}

    @router.get("/api/v1/sharing/stats")
    async def api_sharing_stats():
        return memos.sharing_stats()
