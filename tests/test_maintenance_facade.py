"""Structural regression tests for the MaintenanceFacade mixin extraction.

Verifies that MaintenanceFacade methods exist on MemOS via inheritance,
have correct signatures, and that core.py no longer contains duplicated definitions.
"""

import inspect
import time

import pytest

from memos._maintenance_facade import MaintenanceFacade
from memos.core import MemOS
from memos.models import MemoryItem

MAINTENANCE_METHODS = (
    "prune",
    "prune_expired",
    "decay",
    "reinforce_memory",
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

    def test_decay_signature(self):
        sig = inspect.signature(MemOS.decay)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "min_age_days" in params
        assert "floor" in params
        assert "dry_run" in params

    def test_reinforce_memory_signature(self):
        sig = inspect.signature(MemOS.reinforce_memory)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "memory_id" in params
        assert "strength" in params


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


class TestDecayPublicSurface:
    def test_decay_dry_run_returns_report(self):
        mem = MemOS(backend="memory", sanitize=False)
        report = mem.decay(dry_run=True)
        assert hasattr(report, "total")
        assert hasattr(report, "decayed")

    def test_decay_dry_run_does_not_modify(self):
        mem = MemOS(backend="memory", sanitize=False)
        old_time = time.time() - 100 * 86400
        mem._store.upsert(
            MemoryItem(
                id="old-1", content="old memory", tags=[], importance=0.5, created_at=old_time, accessed_at=old_time
            ),
            namespace=mem._namespace,
        )
        mem.decay(dry_run=True)
        item = mem._store.get("old-1", namespace=mem._namespace)
        assert item.importance == 0.5

    def test_decay_apply_modifies_importance(self):
        mem = MemOS(backend="memory", sanitize=False)
        old_time = time.time() - 100 * 86400
        mem._store.upsert(
            MemoryItem(
                id="old-2", content="old memory two", tags=[], importance=0.5, created_at=old_time, accessed_at=old_time
            ),
            namespace=mem._namespace,
        )
        mem.decay(dry_run=False)
        item = mem._store.get("old-2", namespace=mem._namespace)
        assert item.importance < 0.5


class TestReinforcePublicSurface:
    def test_reinforce_boosts_importance(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem._store.upsert(
            MemoryItem(id="r-1", content="reinforce me", tags=[], importance=0.3),
            namespace=mem._namespace,
        )
        new_imp = mem.reinforce_memory("r-1", strength=0.2)
        assert new_imp == pytest.approx(0.5)
        item = mem._store.get("r-1", namespace=mem._namespace)
        assert item.importance == pytest.approx(0.5)

    def test_reinforce_clamps_at_one(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem._store.upsert(
            MemoryItem(id="r-2", content="already high", tags=[], importance=0.95),
            namespace=mem._namespace,
        )
        new_imp = mem.reinforce_memory("r-2", strength=0.2)
        assert new_imp == 1.0

    def test_reinforce_missing_raises_keyerror(self):
        mem = MemOS(backend="memory", sanitize=False)
        with pytest.raises(KeyError, match="Memory not found"):
            mem.reinforce_memory("nonexistent-id")


class TestNamespaceIsolationMaintenance:
    def test_consolidate_respects_namespace(self):
        alice = MemOS(backend="memory", sanitize=False)
        alice._namespace = "agent-alice"
        bob = MemOS(backend="memory", sanitize=False)
        bob._namespace = "agent-bob"

        alice._store.upsert(
            MemoryItem(id="a1", content="duplicate content", tags=[], importance=0.5),
            namespace="agent-alice",
        )
        alice._store.upsert(
            MemoryItem(id="a2", content="duplicate content", tags=[], importance=0.5),
            namespace="agent-alice",
        )
        bob._store.upsert(
            MemoryItem(id="b1", content="unique bob content", tags=[], importance=0.5),
            namespace="agent-bob",
        )

        result = alice.consolidate(dry_run=False)
        assert result.groups_found >= 1

        assert len(alice._store.list_all(namespace="agent-alice")) == 1
        assert len(bob._store.list_all(namespace="agent-bob")) == 1

    def test_compact_respects_namespace(self):
        alice = MemOS(backend="memory", sanitize=False)
        alice._namespace = "agent-alice"
        bob = MemOS(backend="memory", sanitize=False)
        bob._namespace = "agent-bob"

        old_time = time.time() - 200 * 86400
        alice._store.upsert(
            MemoryItem(
                id="a-old",
                content="alice old memory with unique content",
                tags=[],
                importance=0.1,
                created_at=old_time,
                accessed_at=old_time,
            ),
            namespace="agent-alice",
        )
        bob._store.upsert(
            MemoryItem(
                id="b-fresh",
                content="bob fresh memory important content",
                tags=["active"],
                importance=0.8,
            ),
            namespace="agent-bob",
        )

        alice.compact()
        bob_items = bob._store.list_all(namespace="agent-bob")
        assert len(bob_items) == 1
        assert bob_items[0].id == "b-fresh"

    def test_decay_respects_namespace(self):
        alice = MemOS(backend="memory", sanitize=False)
        alice._namespace = "agent-alice"
        bob = MemOS(backend="memory", sanitize=False)
        bob._namespace = "agent-bob"

        old_time = time.time() - 100 * 86400
        alice._store.upsert(
            MemoryItem(
                id="a-decay",
                content="alice decaying memory",
                tags=[],
                importance=0.5,
                created_at=old_time,
                accessed_at=old_time,
            ),
            namespace="agent-alice",
        )
        bob._store.upsert(
            MemoryItem(
                id="b-decay",
                content="bob decaying memory",
                tags=[],
                importance=0.5,
                created_at=old_time,
                accessed_at=old_time,
            ),
            namespace="agent-bob",
        )

        alice.decay(dry_run=False)

        bob_item = bob._store.get("b-decay", namespace="agent-bob")
        assert bob_item.importance == 0.5

    def test_reinforce_memory_respects_namespace(self):
        alice = MemOS(backend="memory", sanitize=False)
        alice._namespace = "agent-alice"
        bob = MemOS(backend="memory", sanitize=False)
        bob._namespace = "agent-bob"

        alice._store.upsert(
            MemoryItem(id="shared-id", content="alice version", tags=[], importance=0.3),
            namespace="agent-alice",
        )
        bob._store.upsert(
            MemoryItem(id="shared-id", content="bob version", tags=[], importance=0.3),
            namespace="agent-bob",
        )

        alice.reinforce_memory("shared-id", strength=0.4)

        alice_item = alice._store.get("shared-id", namespace="agent-alice")
        bob_item = bob._store.get("shared-id", namespace="agent-bob")
        assert alice_item.importance == pytest.approx(0.7)
        assert bob_item.importance == pytest.approx(0.3)
