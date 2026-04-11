"""Web dashboard for MemOS — Second Brain Graph View."""

from __future__ import annotations

from pathlib import Path

_DASHBOARD_PATH = Path(__file__).parent / "dashboard.html"

DASHBOARD_HTML = _DASHBOARD_PATH.read_text(encoding="utf-8")
