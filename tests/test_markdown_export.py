"""Tests for portable Markdown export (P27)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from memos.api import create_fastapi_app
from memos.core import MemOS
from memos.export_markdown import MarkdownExporter
from memos.knowledge_graph import KnowledgeGraph


def build_sample_memos(tmp_path: Path) -> MemOS:
    data_dir = tmp_path / ".memos"
    data_dir.mkdir(parents=True, exist_ok=True)
    memos = MemOS(
        backend="memory",
        persist_path=str(data_dir / "store.json"),
        kg_db_path=str(data_dir / "kg.db"),
        sanitize=False,
        auto_kg=False,
    )
    memos._kg = KnowledgeGraph(db_path=str(data_dir / "kg.db"))

    memos.learn("Alice decided to launch Project Phoenix with Acme.", tags=["decision", "team"], importance=0.95)
    memos.learn("Project Phoenix milestone reached in Paris.", tags=["milestone", "project"], importance=0.7)
    memos.learn("Acme prefers weekly written updates from Alice.", tags=["preference"], importance=0.6)

    memos._kg.add_fact("Alice", "works_on", "Project Phoenix", confidence=0.9, confidence_label="EXTRACTED")
    memos._kg.add_fact("Alice", "works_at", "Acme", confidence=0.85, confidence_label="EXTRACTED")
    memos._kg.add_fact("Project Phoenix", "located_in", "Paris", confidence=0.8, confidence_label="EXTRACTED")
    return memos


def test_markdown_export_builds_portable_bundle(tmp_path):
    memos = build_sample_memos(tmp_path)
    export_dir = tmp_path / "knowledge"

    result = MarkdownExporter(memos).export(str(export_dir))

    assert result.memories_total == 3
    assert (export_dir / "INDEX.md").exists()
    assert (export_dir / "LOG.md").exists()
    assert (export_dir / "entities" / "Alice.md").exists()
    assert (export_dir / "memories" / "decisions.md").exists()
    assert list((export_dir / "communities").glob("*.md"))

    entity_page = (export_dir / "entities" / "Alice.md").read_text(encoding="utf-8")
    assert "tags:" in entity_page
    assert "## Knowledge Graph Facts" in entity_page
    assert "[Project Phoenix](../entities/Project-Phoenix.md)" in entity_page

    memory_page = (export_dir / "memories" / "decisions.md").read_text(encoding="utf-8")
    assert "## " in memory_page
    assert "[Alice](../entities/Alice.md)" in memory_page


def test_markdown_export_update_skips_unchanged_pages(tmp_path):
    memos = build_sample_memos(tmp_path)
    exporter = MarkdownExporter(memos)
    export_dir = tmp_path / "knowledge"

    first = exporter.export(str(export_dir))
    second = exporter.export(str(export_dir), update=True)

    assert first.pages_written >= 4
    assert second.pages_skipped >= 4
    assert second.pages_written == 1  # append-only log


def test_cli_export_markdown_writes_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    memos = build_sample_memos(tmp_path)

    from memos.cli import main

    out_dir = tmp_path / "bundle"
    main(["export", "--backend", "memory", "--format", "markdown", "-o", str(out_dir)])

    output = capsys.readouterr().out
    assert "Exported Markdown knowledge bundle" in output
    assert (out_dir / "INDEX.md").exists()
    assert (out_dir / "entities" / "Alice.md").exists()
    memos._kg.close()


def test_api_export_markdown_returns_zip_bundle(tmp_path):
    memos = build_sample_memos(tmp_path)
    app = create_fastapi_app(memos=memos, kg_db_path=str(tmp_path / ".memos" / "kg.db"))

    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/api/v1/export/markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    archive_path = tmp_path / "export.zip"
    archive_path.write_bytes(response.content)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "INDEX.md" in names
        assert "LOG.md" in names
        assert "entities/Alice.md" in names
        assert any(name.startswith("communities/") for name in names)
