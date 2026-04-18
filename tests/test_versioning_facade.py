"""Structural regression tests for the extracted versioning facade."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_versioning_facade_delegates_engine_methods():
    from src.memos._versioning_facade import VersioningFacade

    class _DummyMemOS(VersioningFacade):
        def __init__(self):
            self._versioning = MagicMock()
            self._store = MagicMock()
            self._retrieval = MagicMock()
            self._events = MagicMock()
            self._namespace = ""

        def recall(self, *args, **kwargs):
            return []

    mem = _DummyMemOS()

    mem.history("item-1")
    mem.get_version("item-1", 2)
    mem.diff("item-1", 1, 2)
    mem.diff_latest("item-1")
    mem.snapshot_at(123.0)
    mem.versioning_stats()
    mem.versioning_gc(max_age_days=30.0, keep_latest=2)

    mem._versioning.history.assert_called_once_with("item-1")
    mem._versioning.get_version.assert_called_once_with("item-1", 2)
    mem._versioning.diff.assert_called_once_with("item-1", 1, 2)
    mem._versioning.diff_latest.assert_called_once_with("item-1")
    mem._versioning.snapshot_at.assert_called_once_with(123.0)
    mem._versioning.stats.assert_called_once_with()
    mem._versioning.gc.assert_called_once_with(max_age_days=30.0, keep_latest=2)
