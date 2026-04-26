"""Compatibility aggregator for maintenance memory routes."""

from __future__ import annotations

from fastapi import APIRouter

from ._memory_consolidation import register_memory_consolidation_routes
from ._memory_dedup import register_memory_dedup_routes
from ._memory_feedback import register_memory_feedback_routes
from ._memory_lifecycle import register_memory_lifecycle_routes
from ._memory_tags import register_memory_tag_routes


def register_memory_maintenance_routes(router: APIRouter, memos) -> None:
    """Register maintenance-oriented memory routes."""
    register_memory_lifecycle_routes(router, memos)
    register_memory_tag_routes(router, memos)
    register_memory_consolidation_routes(router, memos)
    register_memory_feedback_routes(router, memos)
    register_memory_dedup_routes(router, memos)
