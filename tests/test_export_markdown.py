from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from memos.core import MemOS
from memos.export_markdown import MarkdownExporter
from memos.knowledge_graph import KnowledgeGraph
from memos.wiki_living import LivingWikiEngine


@pytest.fixture()
def export_env(tmp_path: Path):
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path), sanitize=False)
    memos.learn("Alice decided to ship MemOS export docs this week.", tags=["decision", "memos"], importance=0.9)
    memos.learn("Bob prefers markdown exports for audits.", tags=["preference", "docs"], importance=0.7)

    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)

    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_fact("Alice", "works_on", "MemOS", confidence_label="EXTRACTED")
    kg.add_fact("Bob", "reviews", "MemOS", confidence_label="EXTRACTED")
    memos._kg = kg

    yield memos, kg, wiki_root
    kg.close()


def test_markdown_export_generates_portable_structure(export_env, tmp_path: Path):
    memos, kg, wiki_root = export_env
    exporter = MarkdownExporter(memos, kg=kg, wiki_dir=str(wiki_root), output_dir=str(tmp_path / "knowledge"))

    result = exporter.export()

    assert result.entity_count >= 2
    assert (tmp_path / "knowledge" / "INDEX.md").exists()
    assert (tmp_path / "knowledge" / "LOG.md").exists()
    assert (tmp_path / "knowledge" / "entities" / "Alice.md").exists()
    assert (tmp_path / "knowledge" / "memories" / "decision.md").exists()
    entity_text = (tmp_path / "knowledge" / "entities" / "Alice.md").read_text(encoding="utf-8")
    assert "## Graph Facts" in entity_text
    assert "[MemOS](MemOS.md)" in entity_text or "[MemOS](../entities/MemOS.md)" in entity_text
    index_text = (tmp_path / "knowledge" / "INDEX.md").read_text(encoding="utf-8")
    assert "## Communities" in index_text


def test_markdown_export_update_skips_unchanged_pages(export_env, tmp_path: Path):
    memos, kg, wiki_root = export_env
    exporter = MarkdownExporter(memos, kg=kg, wiki_dir=str(wiki_root), output_dir=str(tmp_path / "knowledge"))

    first = exporter.export()
    second = exporter.export(update=True)

    assert first.pages_written > 0
    assert second.pages_skipped > 0


def test_cli_export_markdown(export_env, tmp_path: Path, capsys, monkeypatch):
    from memos.cli import main

    memos, kg, wiki_root = export_env
    kg_path = Path(kg._db_path)
    monkeypatch.chdir(tmp_path)
    fresh = MemOS(backend="json", persist_path=".memos/store.json", sanitize=False)
    fresh.import_json(memos.export_json(), merge="duplicate")

    main([
        "export",
        "--backend",
        "json",
        "--format",
        "markdown",
        "--output",
        str(tmp_path / "cli-knowledge"),
        "--wiki-dir",
        str(wiki_root),
        "--db",
        str(kg_path),
    ])

    out = capsys.readouterr().out
    assert "Exported markdown knowledge" in out
    assert (tmp_path / "cli-knowledge" / "INDEX.md").exists()


@pytest.mark.asyncio
async def test_api_export_markdown_returns_zip(export_env, tmp_path: Path):
    from httpx import ASGITransport, AsyncClient
    from memos.api import create_fastapi_app

    memos, kg, wiki_root = export_env
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg._db_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/export/markdown", params={"wiki_dir": str(wiki_root)})

    zip_path = tmp_path / "knowledge.zip"
    zip_path.write_bytes(response.content)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "knowledge/INDEX.md" in names
    assert "knowledge/entities/Alice.md" in names
