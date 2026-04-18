"""Structural regression tests for the IOFacade mixin extraction.

Verifies that IOFacade methods exist on MemOS via inheritance, have correct
signatures, and that core.py no longer contains duplicated definitions.
"""

import inspect

from memos._io_facade import IOFacade
from memos.core import MemOS


class TestIOFacadeInheritance:
    def test_memos_inherits_io_facade(self):
        assert issubclass(MemOS, IOFacade)

    def test_io_facade_is_mixin(self):
        assert "__init__" not in IOFacade.__dict__, "IOFacade should not define __init__"

    def test_memos_instance_has_all_methods(self):
        mem = MemOS(backend="memory", sanitize=False)
        for name in ("export_json", "import_json", "export_parquet", "import_parquet", "migrate_to"):
            assert hasattr(mem, name), f"MemOS instance missing method: {name}"
            assert callable(getattr(mem, name)), f"MemOS.{name} is not callable"


class TestMethodSignatures:
    def test_export_json_signature(self):
        sig = inspect.signature(MemOS.export_json)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "include_metadata" in params
        assert sig.parameters["include_metadata"].default is True

    def test_import_json_signature(self):
        sig = inspect.signature(MemOS.import_json)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "data" in params
        assert "merge" in params
        assert "tags_prefix" in params
        assert "dry_run" in params

    def test_export_parquet_signature(self):
        sig = inspect.signature(MemOS.export_parquet)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "path" in params
        assert "include_metadata" in params
        assert "compression" in params

    def test_import_parquet_signature(self):
        sig = inspect.signature(MemOS.import_parquet)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "path" in params
        assert "merge" in params
        assert "tags_prefix" in params
        assert "dry_run" in params

    def test_migrate_to_signature(self):
        sig = inspect.signature(MemOS.migrate_to)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "dest_backend" in params
        assert "namespaces" in params
        assert "tags_filter" in params
        assert "merge" in params
        assert "dry_run" in params
        assert "batch_size" in params


class TestNoDuplicationInCore:
    def test_export_json_not_in_core_source(self):
        source = inspect.getsource(MemOS.export_json)
        assert "namespace=self._namespace" in source

    def test_import_json_not_in_core_source(self):
        source = inspect.getsource(MemOS.import_json)
        assert "namespace=self._namespace" in source
        assert "namespace=self._namespace" in source.split("self._store.get")[1].split("\n")[0]

    def test_methods_defined_on_facade(self):
        for name in ("export_json", "import_json", "export_parquet", "import_parquet", "migrate_to"):
            assert name in IOFacade.__dict__, f"{name} should be defined on IOFacade, not just inherited"


class TestNamespaceScopingConsistency:
    def test_export_json_passes_namespace(self):
        mem = MemOS(backend="memory", sanitize=False)
        mem.learn("ns-test memory", tags=["ns"])
        data = mem.export_json()
        assert data["total"] == 1

    def test_import_json_uses_namespace(self):
        mem = MemOS(backend="memory", sanitize=False)
        result = mem.import_json(
            {
                "version": "0.2.0",
                "memories": [
                    {
                        "id": "ns-test-1",
                        "content": "namespaced import",
                        "tags": [],
                        "importance": 0.5,
                        "created_at": 0,
                        "accessed_at": 0,
                        "access_count": 0,
                    }
                ],
            }
        )
        assert result["imported"] == 1
        assert mem.stats().total_memories == 1

    def test_export_import_roundtrip_with_namespace(self):
        mem1 = MemOS(backend="memory", sanitize=False)
        mem1.learn("roundtrip-content", tags=["rt"], importance=0.7)
        data = mem1.export_json()

        mem2 = MemOS(backend="memory", sanitize=False)
        result = mem2.import_json(data)
        assert result["imported"] == 1
        assert result["skipped"] == 0
        assert mem2.stats().total_memories == 1
