from __future__ import annotations

import argparse

import pytest

from memos.compression import MemoryCompressor
from memos.core import MemOS
from memos.models import MemoryItem


def test_compressor_groups_low_importance_memories():
    compressor = MemoryCompressor()
    items = [
        MemoryItem(id="a", content="first stale note", tags=["ops"], importance=0.05),
        MemoryItem(id="b", content="second stale note", tags=["ops"], importance=0.04),
        MemoryItem(id="c", content="healthy note", tags=["ops"], importance=0.5),
    ]

    result = compressor.compress(items, threshold=0.1)

    assert result.compressed_count == 2
    assert result.summary_count == 1
    assert result.summaries[0].importance == 0.15
    assert "compressed" in result.summaries[0].tags
    assert set(result.deleted_ids) == {"a", "b"}


def test_memos_compress_dry_run_preserves_store():
    mem = MemOS(backend="memory")
    mem.learn("ops stale one", tags=["ops"], importance=0.05)
    mem.learn("ops stale two", tags=["ops"], importance=0.04)

    before = len(mem._store.list_all())
    result = mem.compress(threshold=0.1, dry_run=True)
    after = len(mem._store.list_all())

    assert result.summary_count == 1
    assert before == after


def test_memos_compress_apply_replaces_with_summary():
    mem = MemOS(backend="memory")
    mem.learn("ops stale one", tags=["ops"], importance=0.05)
    mem.learn("ops stale two", tags=["ops"], importance=0.04)

    result = mem.compress(threshold=0.1, dry_run=False)
    items = mem._store.list_all()

    assert result.summary_count == 1
    assert len(items) == 1
    assert items[0].metadata["compressed"] is True
    assert "compressed" in items[0].tags


def test_cli_compress(capsys):
    import memos.cli as cli_mod
    from memos.cli import cmd_compress

    mem = MemOS(backend="memory")
    mem.learn("ops stale one", tags=["ops"], importance=0.05)
    mem.learn("ops stale two", tags=["ops"], importance=0.04)
    ns = argparse.Namespace(threshold=0.1, dry_run=True, verbose=False, backend="memory")

    original = cli_mod._get_memos
    cli_mod._get_memos = lambda ns: mem
    try:
        cmd_compress(ns)
    finally:
        cli_mod._get_memos = original

    output = capsys.readouterr().out
    assert "DRY RUN Compression complete" in output
    assert "Compressed memories" in output


@pytest.mark.anyio
async def test_rest_compress_endpoint():
    from httpx import ASGITransport, AsyncClient
    from memos.api import create_fastapi_app

    mem = MemOS(backend="memory")
    mem.learn("ops stale one", tags=["ops"], importance=0.05)
    mem.learn("ops stale two", tags=["ops"], importance=0.04)
    app = create_fastapi_app(memos=mem)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/compress", json={"threshold": 0.1, "dry_run": True})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["compressed_count"] == 2
    assert data["summary_count"] == 1
