"""Tests for Parquet export/import functionality."""

import pytest

from memos.core import MemOS

# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def mem():
    m = MemOS(backend="memory", sanitize=False)
    m.learn("alpha memory", tags=["a"], importance=0.8)
    m.learn("beta memory", tags=["b"], importance=0.4)
    m.learn("gamma memory", tags=["a", "b"], importance=0.6)
    return m


# ── Parquet Export Tests ──────────────────────────────────


class TestExportParquet:
    def test_export_creates_file(self, mem, tmp_path):
        path = tmp_path / "export.parquet"
        result = mem.export_parquet(str(path))
        assert path.exists()
        assert result["total"] == 3
        assert result["size_bytes"] > 0
        assert result["compression"] == "zstd"

    def test_export_with_metadata(self, mem, tmp_path):
        path = tmp_path / "export.parquet"
        result = mem.export_parquet(str(path), include_metadata=True)
        assert result["total"] == 3

        # Verify we can read the file and it has metadata column
        import pyarrow.parquet as pq

        table = pq.read_table(str(path))
        assert "metadata_json" in table.column_names

    def test_export_without_metadata(self, mem, tmp_path):
        path = tmp_path / "export.parquet"
        result = mem.export_parquet(str(path), include_metadata=False)
        assert result["total"] == 3

        import pyarrow.parquet as pq

        table = pq.read_table(str(path))
        assert "metadata_json" not in table.column_names

    def test_export_empty(self, tmp_path):
        m = MemOS(backend="memory", sanitize=False)
        path = tmp_path / "empty.parquet"
        result = m.export_parquet(str(path))
        assert result["total"] == 0
        assert path.exists()

    def test_export_snappy_compression(self, mem, tmp_path):
        path = tmp_path / "snappy.parquet"
        result = mem.export_parquet(str(path), compression="snappy")
        assert result["compression"] == "snappy"
        assert path.exists()

    def test_export_creates_parent_dirs(self, mem, tmp_path):
        path = tmp_path / "sub" / "dir" / "export.parquet"
        mem.export_parquet(str(path))
        assert path.exists()

    def test_export_preserves_all_fields(self, mem, tmp_path):
        path = tmp_path / "full.parquet"
        mem.export_parquet(str(path))

        import pyarrow.parquet as pq

        table = pq.read_table(str(path))
        assert table.num_rows == 3
        cols = table.column_names
        for col in (
            "id",
            "content",
            "tags",
            "importance",
            "created_at",
            "accessed_at",
            "access_count",
            "relevance_score",
        ):
            assert col in cols


# ── Parquet Import Tests ──────────────────────────────────


class TestImportParquet:
    def test_roundtrip_preserves_count(self, mem, tmp_path):
        path = tmp_path / "rt.parquet"
        mem.export_parquet(str(path))

        m2 = MemOS(backend="memory", sanitize=False)
        result = m2.import_parquet(str(path))
        assert result["imported"] == 3
        assert result["skipped"] == 0
        assert m2.stats().total_memories == 3

    def test_roundtrip_preserves_content(self, mem, tmp_path):
        path = tmp_path / "rt.parquet"
        mem.export_parquet(str(path))

        m2 = MemOS(backend="memory", sanitize=False)
        m2.import_parquet(str(path))

        items = m2._store.list_all()
        contents = {i.content for i in items}
        assert "alpha memory" in contents
        assert "beta memory" in contents
        assert "gamma memory" in contents

    def test_roundtrip_preserves_tags(self, mem, tmp_path):
        path = tmp_path / "rt.parquet"
        mem.export_parquet(str(path))

        m2 = MemOS(backend="memory", sanitize=False)
        m2.import_parquet(str(path))

        items = m2._store.list_all()
        alpha = [i for i in items if i.content == "alpha memory"][0]
        assert "a" in alpha.tags

    def test_roundtrip_preserves_importance(self, mem, tmp_path):
        path = tmp_path / "rt.parquet"
        mem.export_parquet(str(path))

        m2 = MemOS(backend="memory", sanitize=False)
        m2.import_parquet(str(path))

        items = m2._store.list_all()
        alpha = [i for i in items if i.content == "alpha memory"][0]
        assert abs(alpha.importance - 0.8) < 0.01

    def test_import_skip_existing(self, mem, tmp_path):
        path = tmp_path / "rt.parquet"
        mem.export_parquet(str(path))

        result = mem.import_parquet(str(path), merge="skip")
        assert result["skipped"] == 3
        assert result["imported"] == 0

    def test_import_overwrite(self, mem, tmp_path):
        path = tmp_path / "rt.parquet"
        mem.export_parquet(str(path))

        result = mem.import_parquet(str(path), merge="overwrite")
        assert result["overwritten"] == 3
        assert result["imported"] == 3

    def test_import_tags_prefix(self, tmp_path):
        m = MemOS(backend="memory", sanitize=False)
        m.learn("test memory", tags=["original"])

        path = tmp_path / "prefix.parquet"
        m.export_parquet(str(path))

        m2 = MemOS(backend="memory", sanitize=False)
        result = m2.import_parquet(str(path), tags_prefix=["imported"])
        assert result["imported"] == 1
        items = m2._store.list_all()
        assert "imported" in items[0].tags
        assert "original" in items[0].tags

    def test_import_dry_run(self, tmp_path):
        m = MemOS(backend="memory", sanitize=False)
        m.learn("test memory")

        path = tmp_path / "dry.parquet"
        m.export_parquet(str(path))

        m2 = MemOS(backend="memory", sanitize=False)
        result = m2.import_parquet(str(path), dry_run=True)
        assert result["imported"] == 1
        assert m2.stats().total_memories == 0

    def test_import_dry_run_overwrite_preserves_existing(self, mem, tmp_path):
        path = tmp_path / "rt.parquet"
        mem.export_parquet(str(path))
        first_id = mem.export_json()["memories"][0]["id"]
        original = mem._store.get(first_id, namespace=mem._namespace)
        assert original is not None

        result = mem.import_parquet(str(path), merge="overwrite", dry_run=True)

        assert result["overwritten"] == 3
        assert result["imported"] == 3
        preserved = mem._store.get(first_id, namespace=mem._namespace)
        assert preserved is not None
        assert preserved.content == original.content

    def test_import_overwrite_index_failure_preserves_existing(self, mem, tmp_path, monkeypatch):
        path = tmp_path / "rt.parquet"
        mem.export_parquet(str(path))
        first_id = mem.export_json()["memories"][0]["id"]
        original = mem._store.get(first_id, namespace=mem._namespace)
        assert original is not None

        def fail_index(item):
            raise RuntimeError("index failed")

        monkeypatch.setattr(mem._retrieval, "index", fail_index)

        result = mem.import_parquet(str(path), merge="overwrite")

        assert result["errors"]
        assert "index failed" in result["errors"][0]
        preserved = mem._store.get(first_id, namespace=mem._namespace)
        assert preserved is not None
        assert preserved.content == original.content

    def test_import_overwrite_versioning_failure_preserves_existing(self, mem, tmp_path, monkeypatch):
        path = tmp_path / "rt.parquet"
        mem.export_parquet(str(path))
        first_id = mem.export_json()["memories"][0]["id"]
        original = mem._store.get(first_id, namespace=mem._namespace)
        assert original is not None

        def fail_record_version(item, *, source):
            raise RuntimeError("versioning failed")

        monkeypatch.setattr(mem._versioning, "record_version", fail_record_version)

        result = mem.import_parquet(str(path), merge="overwrite")

        assert result["errors"]
        assert "versioning failed" in result["errors"][0]
        preserved = mem._store.get(first_id, namespace=mem._namespace)
        assert preserved is not None
        assert preserved.content == original.content

    def test_import_file_not_found(self, tmp_path):
        m = MemOS(backend="memory", sanitize=False)
        with pytest.raises(FileNotFoundError):
            m.import_parquet(str(tmp_path / "nonexistent.parquet"))

    def test_import_empty_parquet(self, tmp_path):
        m = MemOS(backend="memory", sanitize=False)
        path = tmp_path / "empty.parquet"
        m.export_parquet(str(path))

        m2 = MemOS(backend="memory", sanitize=False)
        result = m2.import_parquet(str(path))
        assert result["imported"] == 0


# ── Parquet with Metadata Tests ───────────────────────────


class TestParquetMetadata:
    def test_metadata_roundtrip(self, tmp_path):
        m = MemOS(backend="memory", sanitize=False)
        m.learn("with meta", metadata={"source": "test", "priority": 1})

        path = tmp_path / "meta.parquet"
        m.export_parquet(str(path), include_metadata=True)

        m2 = MemOS(backend="memory", sanitize=False)
        m2.import_parquet(str(path))

        items = m2._store.list_all()
        assert len(items) == 1
        assert items[0].metadata.get("source") == "test"

    def test_metadata_excluded(self, tmp_path):
        m = MemOS(backend="memory", sanitize=False)
        m.learn("with meta", metadata={"secret": "value"})

        path = tmp_path / "no-meta.parquet"
        m.export_parquet(str(path), include_metadata=False)

        m2 = MemOS(backend="memory", sanitize=False)
        m2.import_parquet(str(path))

        items = m2._store.list_all()
        assert items[0].metadata == {}

    def test_ttl_and_relevance_roundtrip(self, tmp_path):
        from memos.models import MemoryItem

        m = MemOS(backend="memory", sanitize=False)
        m._store.upsert(
            MemoryItem(
                id="scored",
                content="scored parquet memory",
                relevance_score=0.91,
                ttl=1800.0,
            ),
            namespace=m._namespace,
        )

        path = tmp_path / "scored.parquet"
        m.export_parquet(str(path))

        m2 = MemOS(backend="memory", sanitize=False)
        result = m2.import_parquet(str(path))

        assert result["imported"] == 1
        restored = m2._store.get("scored", namespace=m2._namespace)
        assert restored is not None
        assert restored.relevance_score == 0.91
        assert restored.ttl == 1800.0


# ── CLI Parquet Tests ─────────────────────────────────────


class TestCLIParquet:
    def test_cli_export_parquet(self, tmp_path):
        from memos.cli import main

        m = MemOS(backend="memory", sanitize=False)
        m.learn("cli test", tags=["cli"])

        # Export via CLI
        path = tmp_path / "cli.parquet"
        main(["export", "--backend", "memory", "--format", "parquet", "-o", str(path)])
        assert path.exists()

    def test_cli_import_parquet(self, tmp_path):
        from memos.cli import main

        # Create a parquet file first
        m = MemOS(backend="memory", sanitize=False)
        m.learn("import test")
        path = tmp_path / "imp.parquet"
        m.export_parquet(str(path))

        # Import via CLI (detects .parquet extension)
        main(["import", str(path), "--backend", "memory", "--merge", "duplicate"])


# ── Parquet IO Module Unit Tests ──────────────────────────


class TestParquetIOUnit:
    def test_export_import_with_special_chars(self, tmp_path):
        m = MemOS(backend="memory", sanitize=False)
        m.learn("Content with émojis 🧪 and spëcial chars: <>&\"'")
        m.learn("Tags with|pipe", tags=["tag|1", "tag2"])

        path = tmp_path / "special.parquet"
        m.export_parquet(str(path))

        m2 = MemOS(backend="memory", sanitize=False)
        m2.import_parquet(str(path))

        items = m2._store.list_all()
        assert len(items) == 2
        emoji_item = [i for i in items if "🧪" in i.content][0]
        assert "émojis" in emoji_item.content

    def test_large_export(self, tmp_path):
        m = MemOS(backend="memory", sanitize=False)
        for i in range(30):
            m.learn(f"Memory number {i}", tags=[f"batch-{i % 10}"], importance=i / 100)

        path = tmp_path / "large.parquet"
        result = m.export_parquet(str(path))
        assert result["total"] == 30
        assert result["size_bytes"] > 0

        m2 = MemOS(backend="memory", sanitize=False)
        imported = m2.import_parquet(str(path))
        assert imported["imported"] == 30


class TestParquetMissingPyarrow:
    """Verify graceful error when pyarrow is not installed."""

    def test_export_raises_import_error_with_message(self, tmp_path, monkeypatch):
        """_check_pyarrow should raise ImportError with install hint."""

        # Simulate pyarrow missing by making the import fail
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pyarrow":
                raise ModuleNotFoundError("No module named 'pyarrow'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        m = MemOS(backend="memory", sanitize=False)
        m.learn("test")

        with pytest.raises(ImportError, match="pyarrow is required"):
            m.export_parquet(str(tmp_path / "fail.parquet"))

    def test_import_raises_import_error_with_message(self, tmp_path, monkeypatch):
        """import_parquet should also raise ImportError with install hint."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pyarrow":
                raise ModuleNotFoundError("No module named 'pyarrow'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        m = MemOS(backend="memory", sanitize=False)
        with pytest.raises(ImportError, match="pyarrow is required"):
            m.import_parquet(str(tmp_path / "nonexistent.parquet"))
