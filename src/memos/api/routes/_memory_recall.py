"""Compatibility aggregator for recall, item, and time-travel memory routes."""

from __future__ import annotations

from fastapi import APIRouter

from ._memory_items import register_memory_item_routes
from ._memory_recall_query import register_memory_recall_query_routes
from ._memory_time_travel import register_memory_time_travel_routes


def register_memory_recall_routes(router: APIRouter, memos, kg_bridge) -> None:
    """Register recall, search, get, list, and time-travel endpoints."""
    register_memory_recall_query_routes(router, memos, kg_bridge)
    register_memory_item_routes(router, memos)
    register_memory_time_travel_routes(router, memos)
