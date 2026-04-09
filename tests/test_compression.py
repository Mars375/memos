from __future__ import annotations

import argparse
import time

import pytest

from memos.compression import MemoryCompressor
from memos.core import MemOS
from memos.models import MemoryItem


def _item(content: str, *, tags: list[str] | None = None, importance: float = 0.05, age_days: float = 30) -> MemoryItem:
    created_at = time.time() - age_days * 86400
    return MemoryItem(
        id=f"id-{abs(hash((content, tuple(tags or []))))}",
        content=content,
        tags=tags or [],
        importance=importance,
        created_at=created_at,
        accessed_at=created_at,
    )


def test_memory_compressor_groups_by_shared_tag():
    compressor = MemoryCompressor()
    result = compressor.compress(
        [
            _item("first stale note", tags=["project-a", "ops"]),
            _item("second stale note", tags=["project-a"]),
            _item("keep me", tags=["project-b"], importance=0.5),
        ],
        threshold=0.1,
    )

    assert result.compressed_count == 2
    assert result.summary_count == 1
    assert len(result.deleted_ids) == 2
    summary = result.summaries[0]
    assert "compressed" in summary.tags
    assert "project-a" in summary.tags
    assert summary.importance == pytest.approx(0.15)
    assert "first stale note" in summary.content
    assert "second stale note" in summary.content


def test_memory_compressor_skips_singletons_and_existing_summaries():
    compressor = MemoryCompressor()
    compressed_item = _item("already compressed", tags=["compressed"], importance=0.05)
    compressed_item.metadata["compression"] = {"source_count": 2}
    result = compressor.compress(
        [
            _item("solo stale", tags=["solo"], importance=0.05),
            compressed_item,
        ],
        threshold=0.1,
    )

    assert result.compressed_count == 0
    assert result.summary_count == 0
    assert result.skipped_count == 1


def test_memos_compress_dry_run_keeps_originals():
    mem = MemOS(backend="memory")
    first = mem.learn("compress alpha", tags=["compress-test"], importance=0.05, auto_kg=False)
    second = mem.learn("compress beta", tags=["compress-test"], importance=0.06, auto_kg=False)

    result = mem.compress(threshold=0.1, dry_run=True)
    items = mem._store.list_all(namespace=mem._namespace)

    assert result["compressed_count"] == 2
    assert len(items) == 2
    assert {item.id for item in items} == {first.id, second.id}


def test_memos_compress_apply_replaces_group_with_summary():
    mem = MemOS(backend="memory")
    first = mem.learn("compress gamma", tags=["compress-apply"], importance=0.05, auto_kg=False)
    second = mem.learn("compress delta", tags=["compress-apply"], importance=0.06, auto_kg=False)

    result = mem.compress(threshold=0.1, dry_run=False)
    items = mem._store.list_all(namespace=mem._namespace)

    assert result["compressed_count"] == 2
    assert result["summary_count"] == 1
    assert len(items) == 1
    assert items[0].id not in {first.id, second.id}
    assert "compressed" in items[0].tags
    assert items[0].metadata["compression"]["source_count"] == 2


def test_cli_compress_parser():
    from memos.cli import build_parser

    ns = build_parser().parse_args(["compress", "--threshold", "0.2", "--dry-run", "--json"])
    assert ns.command == "compress"
    assert ns.threshold == 0.2
    assert ns.dry_run is True
    assert ns.json is True


def test_cli_compress_dry_run_output(capsys):
    from memos.cli import cmd_compress
    import memos.cli as cli_mod

    mem = MemOS(backend="memory")
    mem.learn("cli compress one", tags=["cli-compress"], importance=0.05, auto_kg=False)
    mem.learn("cli compress two", tags=["cli-compress"], importance=0.06, auto_kg=False)

    ns = argparse.Namespace(threshold=0.1, dry_run=True, json=False, backend="memory")
    original = cli_mod._get_memos
    cli_mod._get_memos = lambda _: mem
    try:
        cmd_compress(ns)
    finally:
        cli_mod._get_memos = original

    out = capsys.readouterr().out
    assert "Compression report (DRY RUN)" in out
    assert "Compressed memories: 2" in out


@pytest.fixture()
def app():
    from memos.api import create_fastapi_app

    mem = MemOS(backend="memory")
    mem.learn("api compress one", tags=["api-compress"], importance=0.05, auto_kg=False)
    mem.learn("api compress two", tags=["api-compress"], importance=0.06, auto_kg=False)
    return create_fastapi_app(memos=mem)


@pytest.mark.anyio
async def test_rest_compress_endpoint(app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/compress", json={"threshold": 0.1, "dry_run": True})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["compressed_count"] == 2
    assert data["summary_count"] == 1
