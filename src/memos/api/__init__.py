"""REST API for MemOS."""

from __future__ import annotations

from typing import Any, Optional

from .. import __version__ as MEMOS_VERSION
from ..core import MemOS

try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]


def create_fastapi_app(
    memos: Optional[MemOS] = None,
    api_keys: Optional[list[str]] = None,
    rate_limit: Optional[int] = None,
    rate_window: Optional[float] = None,
    kg_db_path: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Create a FastAPI application for MemOS.

    Args:
        memos: MemOS instance (created from kwargs if None).
        api_keys: List of valid API keys. If None/empty, auth is disabled.
        rate_limit: Max requests per window per key. Falls back to
            MEMOS_RATE_LIMIT env var, then default 300.
        rate_window: Window in seconds. Falls back to MEMOS_RATE_WINDOW
            env var, then default 60.0.
        kg_db_path: SQLite path for KnowledgeGraph and PalaceIndex.
    """
    if FastAPI is None:
        raise ImportError("FastAPI is required for the server. Install with: pip install memos-os[server]")

    if memos is None:
        memos = MemOS(**kwargs)

    # Resolve rate limit from arg → env → default
    import os

    if rate_limit is None:
        rate_limit = int(os.environ.get("MEMOS_RATE_LIMIT", "300"))
    if rate_window is None:
        rate_window = float(os.environ.get("MEMOS_RATE_WINDOW", "60.0"))

    # ── Dependencies ──────────────────────────────────────────
    from ..context import ContextStack
    from ..kg_bridge import KGBridge
    from ..knowledge_graph import KnowledgeGraph
    from ..palace import PalaceIndex
    from ..web import DASHBOARD_HTML
    from .auth import APIKeyManager, create_auth_middleware
    from .ratelimit import DEFAULT_RULES, RateLimiter, create_rate_limit_middleware

    _kg = KnowledgeGraph(db_path=kg_db_path)
    _kg_bridge = KGBridge(memos, _kg)
    memos.kg = _kg
    memos.kg_bridge = _kg_bridge

    if kg_db_path:
        if kg_db_path == ":memory:":
            _palace_db_path = ":memory:"
        else:
            from pathlib import Path as _Path

            _palace_db_path = str(_Path(kg_db_path).parent / "palace.db")
    else:
        _palace_db_path = None
    _palace = PalaceIndex(db_path=_palace_db_path) if _palace_db_path else PalaceIndex()
    _context_stack = ContextStack(memos)

    key_manager = APIKeyManager(keys=api_keys)
    key_manager.rate_limiter.max_requests = rate_limit
    rate_limiter = RateLimiter(default_max=rate_limit, default_window=rate_window, rules=DEFAULT_RULES)

    # ── FastAPI app ───────────────────────────────────────────
    app = FastAPI(
        title="MemOS",
        description="Memory Operating System for LLM Agents",
        version=MEMOS_VERSION,
    )

    # Middleware (auth before rate-limit)
    if key_manager.auth_enabled:
        app.middleware("http")(create_auth_middleware(key_manager))
    app.middleware("http")(create_rate_limit_middleware(rate_limiter))

    # ── Routers ───────────────────────────────────────────────
    from .routes.admin import create_admin_router
    from .routes.knowledge import create_knowledge_router
    from .routes.memory import create_memory_router

    app.include_router(create_memory_router(memos, _kg_bridge))
    app.include_router(create_knowledge_router(memos, _kg, _palace, _context_stack))
    app.include_router(create_admin_router(memos, _kg, key_manager, rate_limiter, MEMOS_VERSION, DASHBOARD_HTML))

    # ── MCP Streamable HTTP ───────────────────────────────────
    from ..mcp_server import add_mcp_routes as _add_mcp

    _add_mcp(app, memos)

    # ── Static files (CSS, JS modules) ───────────────────────
    from pathlib import Path as _WebPath

    from starlette.staticfiles import StaticFiles

    _web_dir = _WebPath(__file__).resolve().parent.parent / "web"
    if _web_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(_web_dir)), name="dashboard_static")

    return app
