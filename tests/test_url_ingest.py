"""Tests for URL ingestion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from memos.api import create_fastapi_app
from memos.cli import build_parser, main
from memos.core import MemOS
from memos.ingest.url import URLIngestor, _FetchedURL


def _as_uri(path: Path) -> str:
    return path.resolve().as_uri()


def test_ingest_webpage_file_url(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        """
        <html>
          <head>
            <title>MemOS article</title>
            <meta name="description" content="Short summary for testing.">
          </head>
          <body>
            <article>
              <h1>MemOS article</h1>
              <p>URL ingestion turns webpages into memory chunks.</p>
              <p>It should keep the useful text and metadata.</p>
            </article>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    result = URLIngestor().ingest(_as_uri(page), tags=["seed"], max_chunk=120)

    assert result.total_chunks >= 1
    assert not result.errors
    assert result.chunks[0]["metadata"]["source_type"] == "webpage"
    assert result.chunks[0]["metadata"]["title"] == "MemOS article"
    assert "seed" in result.chunks[0]["tags"]
    assert "webpage" in result.chunks[0]["tags"]
    assert "MemOS article" in result.chunks[0]["content"]


def test_ingest_arxiv_metadata(monkeypatch):
    html = b"""
    <html><head>
      <meta name="citation_title" content="MemOS for Agents">
      <meta name="citation_author" content="Alice Smith">
      <meta name="citation_author" content="Bob Jones">
      <meta name="description" content="Abstract: Persistent local-first memory for LLM agents.">
    </head></html>
    """

    ingestor = URLIngestor()
    monkeypatch.setattr(
        ingestor,
        "_fetch",
        lambda url: _FetchedURL(
            url="https://arxiv.org/abs/2504.12345",
            data=html,
            content_type="text/html",
        ),
    )

    result = ingestor.ingest("https://arxiv.org/abs/2504.12345")

    assert result.total_chunks == 1
    chunk = result.chunks[0]
    assert chunk["metadata"]["source_type"] == "arxiv"
    assert chunk["metadata"]["arxiv_id"] == "2504.12345"
    assert "arxiv" in chunk["tags"]
    assert "paper" in chunk["tags"]
    assert "Alice Smith" in chunk["content"]
    assert "Persistent local-first memory" in chunk["content"]


def test_ingest_tweet_metadata(monkeypatch):
    html = b"""
    <html><head>
      <meta property="og:description" content="Proto on X: MemOS can ingest tweets and webpages. / X">
      <title>Proto on X</title>
    </head></html>
    """

    ingestor = URLIngestor()
    monkeypatch.setattr(
        ingestor,
        "_fetch",
        lambda url: _FetchedURL(
            url="https://x.com/proto/status/123",
            data=html,
            content_type="text/html",
        ),
    )

    result = ingestor.ingest("https://x.com/proto/status/123")

    assert result.total_chunks == 1
    chunk = result.chunks[0]
    assert chunk["metadata"]["source_type"] == "tweet"
    assert "tweet" in chunk["tags"]
    assert "author:proto" in chunk["tags"]
    assert "MemOS can ingest tweets and webpages." in chunk["content"]


def test_ingest_pdf_file_url(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj<< /Length 51 >>stream\n"
        b"BT /F1 12 Tf 72 720 Td (MemOS PDF content) Tj ET\n"
        b"endstream\nendobj\n"
        b"trailer<<>>\n%%EOF\n"
    )

    result = URLIngestor().ingest(_as_uri(pdf))

    assert result.total_chunks == 1
    assert result.chunks[0]["metadata"]["source_type"] == "pdf"
    assert "pdf" in result.chunks[0]["tags"]
    assert "MemOS PDF content" in result.chunks[0]["content"]


def test_memos_ingest_url_stores_memories(tmp_path):
    page = tmp_path / "article.html"
    page.write_text("<html><head><title>Stored page</title></head><body><p>Saved into MemOS.</p></body></html>", encoding="utf-8")

    memos = MemOS(backend="memory", sanitize=False)
    result = memos.ingest_url(_as_uri(page), tags=["imported"], dry_run=False)

    assert result.total_chunks == 1
    items = memos.search("Saved into MemOS")
    assert len(items) == 1
    assert items[0].metadata["source_type"] == "webpage"
    assert "imported" in items[0].tags


def test_api_ingest_url_dry_run(tmp_path):
    from fastapi.testclient import TestClient

    page = tmp_path / "api-page.html"
    page.write_text("<html><head><title>API page</title></head><body><p>Dry-run URL ingest.</p></body></html>", encoding="utf-8")

    app = create_fastapi_app(backend="memory", kg_db_path=":memory:")
    client = TestClient(app)
    response = client.post(
        "/api/v1/ingest/url",
        json={"url": _as_uri(page), "tags": ["api"], "dry_run": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["source_type"] == "webpage"
    assert payload["total_chunks"] == 1
    assert payload["chunks"][0]["metadata"]["title"] == "API page"


def test_cli_ingest_url_parsing():
    parser = build_parser()
    ns = parser.parse_args(["ingest-url", "https://example.com/post", "--tags", "web,example", "--max-chunk", "123"])
    assert ns.url == "https://example.com/post"
    assert ns.tags == "web,example"
    assert ns.max_chunk == 123


def test_cli_ingest_url_command(capsys):
    class FakeMemOS:
        def ingest_url(self, url, *, tags=None, importance=0.5, max_chunk=2000, dry_run=False):
            assert url == "https://example.com/post"
            assert tags == ["web", "example"]
            assert dry_run is True
            return type(
                "FakeResult",
                (),
                {
                    "total_chunks": 2,
                    "skipped": 0,
                    "errors": [],
                    "chunks": [{"metadata": {"source_type": "webpage"}}],
                },
            )()

    with patch("memos.cli.commands_io._get_memos", return_value=FakeMemOS()):
        main(["ingest-url", "https://example.com/post", "--tags", "web,example", "--dry-run"])

    out = capsys.readouterr().out
    assert "2 chunks" in out
    assert "webpage" in out
