"""Aggregate focused knowledge-related route modules."""

from __future__ import annotations

from fastapi import APIRouter

from .brain import create_brain_router
from .context import create_context_router
from .kg import create_kg_router
from .palace import create_palace_router
from .wiki import create_wiki_router


def create_knowledge_router(memos, _kg, _palace, _context_stack) -> APIRouter:
    """Create the aggregated knowledge-related API router."""
    router = APIRouter()
    router.include_router(create_kg_router(_kg))
    router.include_router(create_brain_router(memos, _kg))
    router.include_router(create_palace_router(memos, _palace))
    router.include_router(create_context_router(memos, _context_stack))
    router.include_router(create_wiki_router(memos))
    return router
