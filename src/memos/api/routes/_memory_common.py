"""Shared helpers for memory-related API routes."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from ...utils import parse_date as _parse_date

_ENFORCE_SANITIZATION = os.environ.get("MEMOS_ENFORCE_SANITIZATION", "true").lower() in ("true", "1", "yes")


def as_list(value: Any) -> list[str]:
    """Normalize a scalar or sequence tag payload into a list of strings."""
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if item]


def parse_iso_timestamp(value: str | None) -> float | None:
    """Parse an ISO datetime string into a unix timestamp."""
    return datetime.fromisoformat(value).timestamp() if value else None


__all__ = ["_ENFORCE_SANITIZATION", "_parse_date", "as_list", "parse_iso_timestamp"]
