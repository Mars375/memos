"""Tests for backend migration."""

from __future__ import annotations

import json
from types import SimpleNamespace

from memos.core import MemOS
from memos.cli import build_parser, cmd_migrate


class TestMigrationEngine:
    def test_migrate_preserves_metadata(self, tmp_path):
        src = MemOS(backend="memory", sanitize=False)
        src.namespace = "agents"
        item = src.learn("User prefers concise responses", tags=["preference", "docs"], importance=0.9)
        stored = src._store.get(item.id, namespace="agents")
        assert stored is not None
        stored.metadata["origin"] = "unit-test"
        src._store.upsert(stored, namespace="agents")

        dest_path = tmp_path / "dest.json"
        report = src.migrate_to("memory", persist_path=str(dest_path))

        assert report.source_backend == "memory"
        assert report.dest_backend == "memory"
        assert report.migrated == 1
        assert report.skipped == 0
        assert report.errors == []
        assert report.namespaces_migrated == 1

        dest = MemOS(backend="memory", persist_path=str(dest_path), sanitize=False)
        dest.namespace = "agents"
        migrated = dest._store.get(item.id, namespace="agents")
        assert migrated is not None
        assert migrated.content == "User prefers concise responses"
        assert migrated.tags == ["preference", "docs"]
        assert migrated.importance == 0.9
        assert migrated.metadata["origin"] == "unit-test"

    def test_migrate_dry_run_does_not_write(self, tmp_path):
        src = MemOS(backend="memory", sanitize=False)
        src.learn("Dry run memory")
        dest_path = tmp_path / "dry.json"

        report = src.migrate_to("memory", persist_path=str(dest_path), dry_run=True)

        assert report.dry_run is True
        assert report.migrated == 1
        assert not dest_path.exists()


class TestMigrationCLI:
    def test_parser_accepts_migrate(self):
        p = build_parser()
        ns = p.parse_args([
            "migrate",
            "--dest",
            "json",
            "--dest-option",
            "path=/tmp/memos.json",
            "--namespaces",
            "agents,ops",
            "--merge",
            "overwrite",
        ])
        assert ns.command == "migrate"
        assert ns.dest == "json"
        assert ns.dest_option == ["path=/tmp/memos.json"]
        assert ns.namespaces == "agents,ops"
        assert ns.merge == "overwrite"

    def test_cmd_migrate_prints_summary(self, capsys):
        class FakeReport:
            source_backend = "memory"
            dest_backend = "json"
            total_items = 2
            migrated = 2
            skipped = 0
            errors: list[str] = []
            namespaces_migrated = 1
            duration_seconds = 0.01
            dry_run = False

            def summary(self) -> str:
                return "Migration: memory → json\n  Items: 2/2 migrated, 0 skipped"

        class FakeMemOS:
            def migrate_to(self, dest_backend: str, **kwargs):
                assert dest_backend == "json"
                assert kwargs["namespaces"] == ["agents"]
                assert kwargs["merge"] == "overwrite"
                assert kwargs["dry_run"] is False
                assert kwargs["batch_size"] == 50
                assert kwargs["path"] == "/tmp/memos.json"
                return FakeReport()

        ns = SimpleNamespace(
            backend="memory",
            chroma_host=None,
            chroma_port=None,
            qdrant_host=None,
            qdrant_port=None,
            qdrant_api_key=None,
            qdrant_path=None,
            pinecone_api_key=None,
            pinecone_environment=None,
            pinecone_index_name=None,
            pinecone_cloud=None,
            pinecone_region=None,
            pinecone_serverless=None,
            vector_size=None,
            embed_host=None,
            embed_model=None,
            no_sanitize=False,
            dest="json",
            namespaces="agents",
            merge="overwrite",
            dry_run=False,
            json=False,
            batch_size=50,
            dest_option=["path=/tmp/memos.json"],
        )

        from unittest.mock import patch

        with patch("memos.cli._get_memos", return_value=FakeMemOS()):
            cmd_migrate(ns)

        out = capsys.readouterr().out
        assert "Migration: memory → json" in out
