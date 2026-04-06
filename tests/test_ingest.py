"""Tests for file ingestion engine."""

import json
import pytest
from pathlib import Path

from memos.ingest.engine import ingest_file, ingest_files, _chunk_markdown, _chunk_json


@pytest.fixture
def tmp_md(tmp_path):
    p = tmp_path / "test.md"
    p.write_text("""# Project Alpha

This is the main project description.

## Setup

Install dependencies with pip.

## Architecture

The system has three layers:
- API layer
- Business logic
- Storage backend
""")
    return p


@pytest.fixture
def tmp_json_array(tmp_path):
    p = tmp_path / "memories.json"
    data = [
        {"content": "User prefers dark mode", "tags": ["ui", "preference"], "importance": 0.8},
        {"content": "Server runs on port 8080", "tags": ["config"]},
        "Simple string memory",
    ]
    p.write_text(json.dumps(data))
    return p


@pytest.fixture
def tmp_json_kv(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"host": "localhost", "port": 8080, "debug": True}))
    return p


class TestMarkdownIngest:
    def test_basic_md_ingest(self, tmp_md):
        result = ingest_file(tmp_md)
        assert result.total_chunks >= 2
        assert not result.errors
        assert all(c["metadata"]["type"] == "markdown" for c in result.chunks)

    def test_md_header_tags(self, tmp_md):
        result = ingest_file(tmp_md)
        # Should have tags from headers
        tag_lists = [c["tags"] for c in result.chunks if c["tags"]]
        assert any("project-alpha" in tags for tags in tag_lists)

    def test_md_empty_file(self, tmp_path):
        p = tmp_path / "empty.md"
        p.write_text("")
        result = ingest_file(p)
        assert result.total_chunks == 0
        assert result.skipped == 1

    def test_md_no_headers(self, tmp_path):
        p = tmp_path / "plain.txt"
        p.write_text("Just a simple paragraph of text.\nNo headers here.")
        result = ingest_file(p)
        assert result.total_chunks == 1
        assert "simple paragraph" in result.chunks[0]["content"]

    def test_md_custom_tags(self, tmp_md):
        result = ingest_file(tmp_md, tags=["custom"])
        for chunk in result.chunks:
            assert "custom" in chunk["tags"]

    def test_md_importance(self, tmp_md):
        result = ingest_file(tmp_md, importance=0.9)
        for chunk in result.chunks:
            assert chunk["importance"] == 0.9


class TestJsonIngest:
    def test_json_array_of_objects(self, tmp_json_array):
        result = ingest_file(tmp_json_array)
        assert result.total_chunks == 3
        assert result.chunks[0]["content"] == "User prefers dark mode"
        assert "ui" in result.chunks[0]["tags"]

    def test_json_string_array(self, tmp_path):
        p = tmp_path / "strings.json"
        p.write_text(json.dumps(["First memory", "Second memory"]))
        result = ingest_file(p)
        assert result.total_chunks == 2

    def test_json_single_object(self, tmp_path):
        p = tmp_path / "single.json"
        p.write_text(json.dumps({"content": "Important note", "tags": ["note"]}))
        result = ingest_file(p)
        assert result.total_chunks == 1
        assert result.chunks[0]["content"] == "Important note"

    def test_json_kv_mapping(self, tmp_json_kv):
        result = ingest_file(tmp_json_kv)
        assert result.total_chunks == 3
        contents = [c["content"] for c in result.chunks]
        assert any("host" in c for c in contents)

    def test_json_invalid(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json")
        result = ingest_file(p)
        assert result.errors
        assert result.total_chunks == 0

    def test_json_string_tags_parsed(self, tmp_json_array):
        result = ingest_file(tmp_json_array)
        assert "ui" in result.chunks[0]["tags"]
        assert "preference" in result.chunks[0]["tags"]


class TestEdgeCases:
    def test_nonexistent_file(self):
        result = ingest_file("/tmp/does_not_exist_12345.md")
        assert result.errors
        assert result.total_chunks == 0

    def test_unsupported_format(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("a,b,c")
        result = ingest_file(p)
        assert "Unsupported format" in result.errors[0]

    def test_directory(self, tmp_path):
        result = ingest_file(tmp_path)
        assert "Not a file" in result.errors[0]

    def test_dry_run_returns_chunks(self, tmp_md):
        result = ingest_file(tmp_md, dry_run=True)
        assert result.total_chunks > 0
        assert result.chunks  # chunks are returned even in dry run

    def test_large_chunk_split(self, tmp_path):
        p = tmp_path / "big.md"
        # One section with many paragraphs
        content = "## Big Section\n\n" + "\n\n".join(f"Paragraph {i} with some content." for i in range(50))
        p.write_text(content)
        result = ingest_file(p, max_chunk=200)
        assert result.total_chunks > 1


class TestIngestFiles:
    def test_multiple_files(self, tmp_md, tmp_json_array):
        result = ingest_files([tmp_md, tmp_json_array])
        assert result.total_chunks >= 3  # at least 2 from md + 3 from json

    def test_empty_list(self):
        result = ingest_files([])
        assert result.total_chunks == 0
