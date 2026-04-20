"""Structural regression tests for the DedupFacade mixin extraction.

Verifies that DedupFacade methods exist on MemOS via inheritance, have correct
signatures, and that delegation to DedupEngine works as expected.
"""

import inspect
from unittest.mock import MagicMock, patch

from memos._dedup_facade import DedupFacade
from memos.core import MemOS
from memos.dedup import DedupCheckResult, DedupScanResult

DEDUP_METHODS = ("dedup_enabled", "dedup_set_enabled", "dedup_check", "dedup_scan")


class TestDedupFacadeInheritance:
    def test_memos_inherits_dedup_facade(self):
        assert issubclass(MemOS, DedupFacade)

    def test_dedup_facade_is_mixin(self):
        assert "__init__" not in DedupFacade.__dict__, "DedupFacade should not define __init__"

    def test_memos_instance_has_all_dedup_methods(self):
        mem = MemOS(backend="memory", sanitize=False)
        for name in ("dedup_set_enabled", "dedup_check", "dedup_scan"):
            assert hasattr(mem, name), f"MemOS instance missing method: {name}"
            assert callable(getattr(mem, name)), f"MemOS.{name} is not callable"


class TestMethodSignatures:
    def test_dedup_enabled_is_property(self):
        assert isinstance(inspect.getattr_static(DedupFacade, "dedup_enabled"), property)

    def test_dedup_set_enabled_signature(self):
        sig = inspect.signature(MemOS.dedup_set_enabled)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "enabled" in params
        assert "threshold" in params

    def test_dedup_check_signature(self):
        sig = inspect.signature(MemOS.dedup_check)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "content" in params
        assert "threshold" in params

    def test_dedup_scan_signature(self):
        sig = inspect.signature(MemOS.dedup_scan)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "fix" in params
        assert "threshold" in params


class TestNoDuplicationInCore:
    def test_methods_defined_on_facade(self):
        for name in ("dedup_set_enabled", "dedup_check", "dedup_scan"):
            assert name in DedupFacade.__dict__, f"{name} should be defined on DedupFacade, not just inherited"

    def test_dedup_enabled_property_on_facade(self):
        assert "dedup_enabled" in DedupFacade.__dict__


class TestDedupEnabledProperty:
    def test_dedup_enabled_default(self):
        mem = MemOS(backend="memory", sanitize=False)
        assert isinstance(mem.dedup_enabled, bool)


class TestDedupSetEnabled:
    def test_enabling_creates_engine(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.dedup_set_enabled(True, threshold=0.9)
        assert mem.dedup_enabled is True
        assert mem._dedup_engine is not None

    def test_disabling_clears_engine(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.dedup_set_enabled(True)
        mem.dedup_set_enabled(False)
        assert mem._dedup_enabled is False
        assert mem._dedup_engine is None


def _make_dedup_dummy():
    class _Dummy(DedupFacade):
        def __init__(self):
            self._store = MagicMock()
            self._namespace = ""
            self._dedup_enabled = False
            self._dedup_threshold = 0.95
            self._dedup_engine = None

    return _Dummy()


class TestDedupCheckDelegation:
    def test_dedup_check_creates_engine_if_none(self):
        mem = _make_dedup_dummy()
        fake_result = DedupCheckResult(is_duplicate=False, match=None, reason="", similarity=0.0)

        with patch("memos._dedup_facade.DedupEngine") as MockEngine:
            mock_instance = MockEngine.return_value
            mock_instance.check.return_value = fake_result
            result = mem.dedup_check("some content")

        assert result.is_duplicate is False
        MockEngine.return_value.check.assert_called_once()

    def test_dedup_check_uses_existing_engine(self):
        mem = _make_dedup_dummy()
        fake_result = DedupCheckResult(is_duplicate=True, reason="exact", similarity=1.0)
        mock_engine = MagicMock()
        mock_engine.check.return_value = fake_result
        mem._dedup_engine = mock_engine

        result = mem.dedup_check("duplicate content")

        mock_engine.check.assert_called_once_with("duplicate content", threshold=None)
        assert result.is_duplicate is True
        assert result.reason == "exact"


class TestDedupScanDelegation:
    def test_dedup_scan_creates_engine_if_none(self):
        mem = _make_dedup_dummy()
        fake_result = DedupScanResult(total_scanned=0, exact_duplicates=0, near_duplicates=0)

        with patch("memos._dedup_facade.DedupEngine") as MockEngine:
            mock_instance = MockEngine.return_value
            mock_instance.scan.return_value = fake_result
            result = mem.dedup_scan()

        assert result.total_scanned == 0
        MockEngine.return_value.scan.assert_called_once()

    def test_dedup_scan_fix_invalidates_cache(self):
        mem = _make_dedup_dummy()
        fake_result = DedupScanResult(total_scanned=5, exact_duplicates=2, fixed=2)
        mock_engine = MagicMock()
        mock_engine.scan.return_value = fake_result
        mem._dedup_engine = mock_engine

        result = mem.dedup_scan(fix=True)

        mock_engine.scan.assert_called_once_with(fix=True, threshold=None)
        mock_engine.invalidate_cache.assert_called_once()
        assert result.fixed == 2

    def test_dedup_scan_no_fix_no_invalidate(self):
        mem = _make_dedup_dummy()
        fake_result = DedupScanResult(total_scanned=3, exact_duplicates=0)
        mock_engine = MagicMock()
        mock_engine.scan.return_value = fake_result
        mem._dedup_engine = mock_engine

        mem.dedup_scan(fix=False)

        mock_engine.invalidate_cache.assert_not_called()
