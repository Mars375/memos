"""Tests for export/import functionality."""

import json

import pytest

from memos.core import MemOS


@pytest.fixture
def mem():
    m = MemOS(backend="memory", sanitize=False)
    m.learn("alpha memory", tags=["a"], importance=0.8)
    m.learn("beta memory", tags=["b"], importance=0.4)
    m.learn("gamma memory", tags=["a", "b"], importance=0.6)
    return m


class TestExport:
    def test_export_structure(self, mem):
        data = mem.export_json()
        assert data["version"] == "0.2.0"
        assert data["total"] == 3
        assert len(data["memories"]) == 3
        assert "exported_at" in data

    def test_export_fields(self, mem):
        data = mem.export_json()
        item = data["memories"][0]
        for key in (
            "id",
            "content",
            "tags",
            "importance",
            "created_at",
            "accessed_at",
            "access_count",
            "relevance_score",
        ):
            assert key in item

    def test_export_no_metadata(self, mem):
        data = mem.export_json(include_metadata=False)
        assert "metadata" not in data["memories"][0]

    def test_export_with_metadata(self, mem):
        data = mem.export_json(include_metadata=True)
        assert "metadata" in data["memories"][0]

    def test_export_empty(self):
        m = MemOS(backend="memory", sanitize=False)
        data = m.export_json()
        assert data["total"] == 0
        assert data["memories"] == []

    def test_export_roundtrip_json(self, mem):
        """Export then re-import into a fresh instance preserves count."""
        data = mem.export_json()
        text = json.dumps(data)
        m2 = MemOS(backend="memory", sanitize=False)
        result = m2.import_json(json.loads(text))
        assert result["imported"] == 3
        assert result["skipped"] == 0
        assert m2.stats().total_memories == 3

    def test_export_roundtrip_preserves_ttl_and_relevance_score(self):
        from memos.models import MemoryItem

        m = MemOS(backend="memory", sanitize=False)
        m._store.upsert(
            MemoryItem(
                id="scored",
                content="scored memory",
                relevance_score=0.77,
                ttl=3600.0,
            ),
            namespace=m._namespace,
        )

        data = m.export_json()
        exported = data["memories"][0]
        assert exported["relevance_score"] == 0.77
        assert exported["ttl"] == 3600.0

        m2 = MemOS(backend="memory", sanitize=False)
        result = m2.import_json(data)
        assert result["imported"] == 1
        restored = m2._store.get("scored", namespace=m2._namespace)
        assert restored is not None
        assert restored.relevance_score == 0.77
        assert restored.ttl == 3600.0


class TestImport:
    def test_import_basic(self):
        m = MemOS(backend="memory", sanitize=False)
        data = {"memories": [{"content": "hello", "tags": ["x"], "importance": 0.9}]}
        result = m.import_json(data)
        assert result["imported"] == 1
        assert m.stats().total_memories == 1

    def test_import_skip_existing(self, mem):
        data = mem.export_json()
        result = mem.import_json(data, merge="skip")
        assert result["skipped"] == 3
        assert result["imported"] == 0

    def test_import_overwrite(self, mem):
        data = mem.export_json()
        # Modify importance in exported data
        data["memories"][0]["importance"] = 0.99
        result = mem.import_json(data, merge="overwrite")
        assert result["overwritten"] == 3
        assert result["imported"] == 3

    def test_import_tags_prefix(self):
        m = MemOS(backend="memory", sanitize=False)
        data = {"memories": [{"content": "test", "tags": ["original"]}]}
        result = m.import_json(data, tags_prefix=["imported"])
        assert result["imported"] == 1
        items = m._store.list_all()
        assert "imported" in items[0].tags
        assert "original" in items[0].tags

    def test_import_dry_run(self):
        m = MemOS(backend="memory", sanitize=False)
        data = {"memories": [{"content": "test"}]}
        result = m.import_json(data, dry_run=True)
        assert result["imported"] == 1
        assert m.stats().total_memories == 0

    def test_import_dry_run_overwrite_preserves_existing(self, mem):
        data = mem.export_json()
        first_id = data["memories"][0]["id"]
        original = mem._store.get(first_id, namespace=mem._namespace)
        assert original is not None
        data["memories"][0]["content"] = "changed by dry run"

        result = mem.import_json(data, merge="overwrite", dry_run=True)

        assert result["overwritten"] == 3
        assert result["imported"] == 3
        preserved = mem._store.get(first_id, namespace=mem._namespace)
        assert preserved is not None
        assert preserved.content == original.content

    def test_import_overwrite_invalid_entry_preserves_existing(self, mem):
        data = mem.export_json()
        first_id = data["memories"][0]["id"]
        original = mem._store.get(first_id, namespace=mem._namespace)
        assert original is not None
        data["memories"][0].pop("content")

        result = mem.import_json(data, merge="overwrite")

        assert result["errors"]
        preserved = mem._store.get(first_id, namespace=mem._namespace)
        assert preserved is not None
        assert preserved.content == original.content

    def test_import_overwrite_index_failure_preserves_existing(self, mem, monkeypatch):
        data = mem.export_json()
        first_id = data["memories"][0]["id"]
        original = mem._store.get(first_id, namespace=mem._namespace)
        assert original is not None
        data["memories"][0]["content"] = "changed before index failure"

        def fail_index(item):
            raise RuntimeError("index failed")

        monkeypatch.setattr(mem._retrieval, "index", fail_index)

        result = mem.import_json({"memories": [data["memories"][0]]}, merge="overwrite")

        assert result["errors"] == ["index failed"]
        preserved = mem._store.get(first_id, namespace=mem._namespace)
        assert preserved is not None
        assert preserved.content == original.content

    def test_import_new_item_index_failure_removes_partial_item(self, monkeypatch):
        mem = MemOS(backend="memory", sanitize=False)

        def fail_index(item):
            raise RuntimeError("index failed")

        monkeypatch.setattr(mem._retrieval, "index", fail_index)

        result = mem.import_json({"memories": [{"id": "new-id", "content": "partial"}]})

        assert result["errors"] == ["index failed"]
        assert mem._store.get("new-id", namespace=mem._namespace) is None

    def test_import_overwrite_versioning_failure_preserves_existing(self, mem, monkeypatch):
        data = mem.export_json()
        first_id = data["memories"][0]["id"]
        original = mem._store.get(first_id, namespace=mem._namespace)
        assert original is not None
        data["memories"][0]["content"] = "changed before versioning failure"

        def fail_record_version(item, *, source):
            raise RuntimeError("versioning failed")

        monkeypatch.setattr(mem._versioning, "record_version", fail_record_version)

        result = mem.import_json({"memories": [data["memories"][0]]}, merge="overwrite")

        assert result["errors"] == ["versioning failed"]
        preserved = mem._store.get(first_id, namespace=mem._namespace)
        assert preserved is not None
        assert preserved.content == original.content

    def test_import_empty(self):
        m = MemOS(backend="memory", sanitize=False)
        result = m.import_json({"memories": []})
        assert result["imported"] == 0

    def test_import_invalid_entry(self):
        m = MemOS(backend="memory", sanitize=False)
        data = {"memories": [{"content": ""}, {"no_content": True}]}
        result = m.import_json(data)
        assert len(result["errors"]) >= 1

    def test_import_preserves_timestamps(self):
        m1 = MemOS(backend="memory", sanitize=False)
        m1.learn("old memory", importance=0.9)
        data = m1.export_json()

        m2 = MemOS(backend="memory", sanitize=False)
        m2.import_json(data)
        items = m2._store.list_all()
        assert abs(items[0].created_at - data["memories"][0]["created_at"]) < 1


class TestCLIExportImport:
    def _populate(self):
        m = MemOS(backend="memory", sanitize=False)
        m.learn("alpha", tags=["a"])
        m.learn("beta", tags=["b"])
        m.learn("gamma", tags=["c"])
        return m

    def test_cli_export_stdout(self, capsys):
        # CLI creates its own instance — test on empty store is valid
        from memos.cli import main

        main(["export", "--backend", "memory"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "total" in data

    def test_cli_export_file(self, tmp_path):
        from memos.cli import main

        f = tmp_path / "export.json"
        main(["export", "--backend", "memory", "-o", str(f)])
        data = json.loads(f.read_text())
        assert "memories" in data

    def test_cli_import(self, tmp_path):
        from memos.cli import main

        f = tmp_path / "export.json"
        main(["export", "--backend", "memory", "-o", str(f)])
        main(["import", str(f), "--backend", "memory", "--merge", "duplicate"])
