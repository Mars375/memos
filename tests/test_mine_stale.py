"""Tests for MinerCache.staleness_report() — P5 staleness detection."""

import hashlib
import time

import pytest

from memos.ingest.cache import MinerCache


@pytest.fixture
def cache():
    c = MinerCache(":memory:")
    yield c
    c.close()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class TestStalenessReport:
    def test_empty_cache_returns_empty(self, cache):
        report = cache.staleness_report()
        assert report == []

    def test_fresh_file(self, tmp_path, cache):
        f = tmp_path / "note.md"
        content = b"Hello world"
        f.write_bytes(content)
        cache.record(str(f), _sha256(content))

        report = cache.staleness_report()
        assert len(report) == 1
        assert report[0]["status"] == "fresh"
        assert report[0]["path"] == str(f)

    def test_changed_file(self, tmp_path, cache):
        f = tmp_path / "note.md"
        f.write_bytes(b"original content")
        cache.record(str(f), _sha256(b"original content"))

        # Modify the file
        f.write_bytes(b"modified content")

        report = cache.staleness_report()
        assert report[0]["status"] == "changed"

    def test_missing_file(self, tmp_path, cache):
        p = str(tmp_path / "deleted.md")
        cache.record(p, "abc123deadbeef")

        report = cache.staleness_report()
        assert report[0]["status"] == "missing"

    def test_sort_order_changed_before_missing_before_fresh(self, tmp_path, cache):
        # Create files
        fresh_f = tmp_path / "fresh.md"
        fresh_f.write_bytes(b"fresh")
        cache.record(str(fresh_f), _sha256(b"fresh"))

        changed_f = tmp_path / "changed.md"
        changed_f.write_bytes(b"original")
        cache.record(str(changed_f), _sha256(b"original"))
        changed_f.write_bytes(b"modified")

        cache.record(str(tmp_path / "missing.md"), "deadbeef")

        report = cache.staleness_report()
        statuses = [r["status"] for r in report]
        # changed comes first
        assert statuses[0] == "changed"
        # fresh last
        assert statuses[-1] == "fresh"

    def test_memory_count_in_report(self, tmp_path, cache):
        f = tmp_path / "doc.md"
        f.write_bytes(b"content")
        cache.record(str(f), _sha256(b"content"), memory_ids=["id1", "id2", "id3"])

        report = cache.staleness_report()
        assert report[0]["memory_count"] == 3

    def test_mined_at_in_report(self, tmp_path, cache):
        f = tmp_path / "doc.md"
        f.write_bytes(b"content")
        before = time.time()
        cache.record(str(f), _sha256(b"content"))
        after = time.time()

        report = cache.staleness_report()
        assert before <= report[0]["mined_at"] <= after


class TestCLI:
    def test_mine_stale_empty_cache(self, tmp_path, capsys):
        import argparse

        from memos.cli import cmd_mine_stale

        ns = argparse.Namespace(
            only_stale=False,
            cache_db=str(tmp_path / "mine-cache.db"),
        )
        cmd_mine_stale(ns)
        out = capsys.readouterr().out
        assert "No cached files" in out

    def test_mine_stale_fresh(self, tmp_path, capsys):
        import argparse

        from memos.cli import cmd_mine_stale

        cache = MinerCache(str(tmp_path / "mine-cache.db"))
        f = tmp_path / "doc.md"
        f.write_bytes(b"fresh content")
        cache.record(str(f), _sha256(b"fresh content"))
        cache.close()

        ns = argparse.Namespace(
            only_stale=False,
            cache_db=str(tmp_path / "mine-cache.db"),
        )
        cmd_mine_stale(ns)
        out = capsys.readouterr().out
        assert "fresh" in out.lower()

    def test_mine_stale_with_changed_file(self, tmp_path, capsys):
        import argparse

        from memos.cli import cmd_mine_stale

        cache = MinerCache(str(tmp_path / "mine-cache.db"))
        f = tmp_path / "doc.md"
        f.write_bytes(b"original")
        cache.record(str(f), _sha256(b"original"), memory_ids=["m1"])
        f.write_bytes(b"modified")
        cache.close()

        ns = argparse.Namespace(
            only_stale=True,
            cache_db=str(tmp_path / "mine-cache.db"),
        )
        cmd_mine_stale(ns)
        out = capsys.readouterr().out
        assert "changed" in out
        assert "memos mine --update" in out

    def test_mine_stale_only_stale_hides_fresh(self, tmp_path, capsys):
        import argparse

        from memos.cli import cmd_mine_stale

        cache = MinerCache(str(tmp_path / "mine-cache.db"))
        f = tmp_path / "doc.md"
        f.write_bytes(b"fresh")
        cache.record(str(f), _sha256(b"fresh"))
        cache.close()

        ns = argparse.Namespace(
            only_stale=True,
            cache_db=str(tmp_path / "mine-cache.db"),
        )
        cmd_mine_stale(ns)
        out = capsys.readouterr().out
        assert "All sources are fresh" in out
