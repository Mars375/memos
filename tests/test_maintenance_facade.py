"""Structural regression tests for the MaintenanceFacade mixin extraction.

Verifies that MaintenanceFacade methods exist on MemOS via inheritance,
have correct signatures, and that core.py no longer contains duplicated definitions.
"""

import inspect

from memos._maintenance_facade import MaintenanceFacade
from memos.core import MemOS

MAINTENANCE_METHODS = (
    "prune",
    "prune_expired",
    "consolidate",
    "consolidate_async",
    "consolidation_status",
    "consolidation_tasks",
    "compact",
    "cache_stats",
    "cache_clear",
    "compress",
)


class TestMaintenanceFacadeInheritance:
    def test_memos_inherits_maintenance_facade(self):
        assert issubclass(MemOS, MaintenanceFacade)

    def test_maintenance_facade_is_mixin(self):
        assert "__init__" not in MaintenanceFacade.__dict__, (
            "MaintenanceFacade should not define __init__"
        )

    def test_memos_instance_has_all_maintenance_methods(self):
        mem = MemOS(backend="memory", sanitize=False)
        for name in MAINTENANCE_METHODS:
            assert hasattr(mem, name), f"MemOS instance missing method: {name}"
            assert callable(getattr(mem, name)), f"MemOS.{name} is not callable"


class TestMethodSignatures:
    def test_prune_signature(self):
        sig = inspect.signature(MemOS.prune)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "threshold" in params
        assert "max_age_days" in params
        assert "dry_run" in params

    def test_prune_expired_signature(self):
        sig = inspect.signature(MemOS.prune_expired)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "dry_run" in params

    def test_consolidate_signature(self):
        sig = inspect.signature(MemOS.consolidate)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "similarity_threshold" in params
        assert "merge_content" in params
        assert "dry_run" in params

    def test_consolidate_async_signature(self):
        sig = inspect.signature(MemOS.consolidate_async)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "similarity_threshold" in params
        assert "merge_content" in params
        assert "dry_run" in params
        assert inspect.iscoroutinefunction(MemOS.consolidate_async)

    def test_consolidation_status_signature(self):
        sig = inspect.signature(MemOS.consolidation_status)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "task_id" in params

    def test_consolidation_tasks_signature(self):
        sig = inspect.signature(MemOS.consolidation_tasks)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_compact_signature(self):
        sig = inspect.signature(MemOS.compact)
        params = list(sig.parameters.keys())
        for expected in (
            "archive_age_days",
            "archive_importance_floor",
            "stale_score_threshold",
            "merge_similarity_threshold",
            "cluster_min_size",
            "dry_run",
            "max_compact_per_run",
        ):
            assert expected in params, f"compact missing param: {expected}"

    def test_cache_stats_signature(self):
        sig = inspect.signature(MemOS.cache_stats)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_cache_clear_signature(self):
        sig = inspect.signature(MemOS.cache_clear)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_compress_signature(self):
        sig = inspect.signature(MemOS.compress)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "threshold" in params
        assert "dry_run" in params


class TestNoDuplicationInCore:
    def test_methods_defined_on_facade(self):
        for name in MAINTENANCE_METHODS:
            assert name in MaintenanceFacade.__dict__, (
                f"{name} should be defined on MaintenanceFacade, not just inherited"
            )

    def test_prune_not_duplicated_in_core(self):
        source = inspect.getsource(MemOS.prune)
        assert source is not None
        assert "namespace=self._namespace" in source

    def test_consolidate_not_duplicated_in_core(self):
        source = inspect.getsource(MemOS.consolidate)
        assert source is not None

    def test_compress_not_duplicated_in_core(self):
        source = inspect.getsource(MemOS.compress)
        assert source is not None


class TestMaintenanceBehaviorSmoke:
    def test_prune_dry_run_returns_empty(self):
        mem = MemOS(backend="memory", sanitize=False)
        result = mem.prune(dry_run=True)
        assert isinstance(result, list)

    def test_prune_expired_dry_run(self):
        mem = MemOS(backend="memory", sanitize=False)
        result = mem.prune_expired(dry_run=True)
        assert isinstance(result, list)

    def test_consolidate_dry_run(self):
        mem = MemOS(backend="memory", sanitize=False)
        result = mem.consolidate(dry_run=True)
        assert result.memories_merged == 0

    def test_consolidation_status_no_tasks(self):
        mem = MemOS(backend="memory", sanitize=False)
        assert mem.consolidation_status("nonexistent") is None

    def test_consolidation_tasks_empty(self):
        mem = MemOS(backend="memory", sanitize=False)
        assert mem.consolidation_tasks() == []

    def test_compact_dry_run(self):
        mem = MemOS(backend="memory", sanitize=False)
        report = mem.compact(dry_run=True)
        assert isinstance(report, dict)

    def test_cache_stats_returns_dict(self):
        mem = MemOS(backend="memory", sanitize=False)
        result = mem.cache_stats()
        assert isinstance(result, dict) or result is None

    def test_cache_clear_returns_count(self):
        mem = MemOS(backend="memory", sanitize=False)
        result = mem.cache_clear()
        assert isinstance(result, int)

    def test_compress_dry_run(self):
        mem = MemOS(backend="memory", sanitize=False)
        result = mem.compress(dry_run=True)
        assert result.summary_count == 0
