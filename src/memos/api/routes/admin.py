"""Stats, analytics, ingest, mine, events, sharing, namespaces, health routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from ._admin_analytics import register_admin_analytics_routes
from ._admin_events import register_admin_events_routes
from ._admin_ingest import register_admin_ingest_routes
from ._admin_system import register_admin_system_routes


def create_admin_router(memos, _kg, key_manager, rate_limiter, MEMOS_VERSION: str, DASHBOARD_HTML: str) -> APIRouter:
    """Create the admin/ops API router."""
    router = APIRouter()
    conversation_mine_lock = asyncio.Lock()

    register_admin_analytics_routes(router, memos)
    register_admin_ingest_routes(router, memos, conversation_mine_lock)
    register_admin_events_routes(router, memos, key_manager)
    register_admin_system_routes(router, memos, key_manager, rate_limiter, MEMOS_VERSION, DASHBOARD_HTML)

    return router
