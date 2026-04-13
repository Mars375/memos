from __future__ import annotations

import zipfile
from pathlib import Path

from memos.core import MemOS
from memos.export_markdown import MarkdownExporter
from memos.knowledge_graph import KnowledgeGraph
from memos.wiki_living import LivingWikiEngine


def _build_env(tmp_path: Path):
    persist_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    wiki_root = tmp_path / "wiki"

    memos = MemOS(backend="json", persist_path=str(persist_path))
    memos.learn("Alice works at OpenAI and documents MemOS.", tags=["people", "docs"])
    memos.learn("MemOS export should stay portable across tools.", tags=["docs", "export"])

    wiki = LivingWikiEngine(memos, wiki_dir=str(wiki_root))
    wiki.init()
    wiki.update(force=True)

    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_fact("Alice", "works_at", "OpenAI", confidence_label="EXTRACTED")
    return memos, kg, wiki_root


def test_markdown_exporter_writes_expected_structure(tmp_path: Path):
    memos, kg, wiki_root = _build_env(tmp_path)
    out_dir = tmp_path / "knowledge"

    exporter = MarkdownExporter(memos, kg=kg, wiki_dir=str(wiki_root))
    result = exporter.export(str(out_dir))

    assert result.total_memories == 2
    assert (out_dir / "INDEX.md").exists()
    assert (out_dir / "LOG.md").exists()
    assert any((out_dir / "entities").glob("alice*.md"))
    assert any((out_dir / "memories").glob("docs*.md"))
    assert "Portable markdown snapshot" in (out_dir / "INDEX.md").read_text(encoding="utf-8")

    kg.close()


def test_markdown_export_cli(tmp_path: Path, capsys):
    from memos.cli import main

    memos, kg, wiki_root = _build_env(tmp_path)
    out_dir = tmp_path / "knowledge-cli"
    kg_path = tmp_path / "kg.db"
    kg.close()

    main(
        [
            "export",
            "--format",
            "markdown",
            "--output",
            str(out_dir),
            "--backend",
            "json",
            "--persist-path",
            str(tmp_path / "store.json"),
            "--wiki-dir",
            str(wiki_root),
            "--db",
            str(kg_path),
        ]
    )

    out = capsys.readouterr().out
    assert "Exported markdown knowledge" in out
    assert (out_dir / "INDEX.md").exists()
    assert (out_dir / "entities").exists()


def test_markdown_export_api_returns_zip(tmp_path: Path):
    from fastapi.testclient import TestClient

    from memos.api import create_fastapi_app

    memos, kg, wiki_root = _build_env(tmp_path)
    app = create_fastapi_app(memos=memos, kg_db_path=str(tmp_path / "kg.db"))
    client = TestClient(app)

    response = client.get(
        "/api/v1/export/markdown", params={"output_dir": str(tmp_path / "knowledge-api"), "wiki_dir": str(wiki_root)}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    zip_path = tmp_path / "export.zip"
    zip_path.write_bytes(response.content)
    with zipfile.ZipFile(zip_path) as bundle:
        names = set(bundle.namelist())
    assert "INDEX.md" in names
    assert "LOG.md" in names
    assert any(name.startswith("entities/") for name in names)

    kg.close()
