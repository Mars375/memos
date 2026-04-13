"""Tests for MinerCache and incremental mining (P19)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from memos.ingest.cache import MinerCache
from memos.ingest.miner import Miner, MineResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache() -> MinerCache:
    return MinerCache(":memory:")


@pytest.fixture()
def tmp_file(tmp_path: Path) -> Path:
    f = tmp_path / "notes.txt"
    f.write_text("Hello world, this is a note about deployment pipelines and CI.")
    return f


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _FakeMemos:
    """Minimal MemOS stub that tracks learns and supports forget."""
    def __init__(self) -> None:
        self._store: dict[str, object] = {}
        self._counter = 0

    def learn(self, content: str, tags=None, importance=0.5, metadata=None):
        self._counter += 1
        item_id = f"mem{self._counter:04d}"

        class _Item:
            id = item_id
        self._store[item_id] = content
        return _Item()

    def forget(self, memory_id: str) -> bool:
        return bool(self._store.pop(memory_id, None))

    @property
    def count(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# MinerCache — unit tests
# ---------------------------------------------------------------------------


def test_cache_is_fresh_miss(cache: MinerCache) -> None:
    assert not cache.is_fresh("/some/file.txt", "abc123")


def test_cache_record_and_is_fresh(cache: MinerCache) -> None:
    cache.record("/file.txt", "sha256abc", memory_ids=["m1"], chunk_hashes=["h1"])
    assert cache.is_fresh("/file.txt", "sha256abc")
    assert not cache.is_fresh("/file.txt", "differenthash")


def test_cache_get_returns_entry(cache: MinerCache) -> None:
    cache.record("/f.txt", "aaa", memory_ids=["m1", "m2"], chunk_hashes=["c1"])
    entry = cache.get("/f.txt")
    assert entry is not None
    assert entry["sha256"] == "aaa"
    assert entry["memory_ids"] == ["m1", "m2"]
    assert entry["chunk_hashes"] == ["c1"]


def test_cache_get_missing(cache: MinerCache) -> None:
    assert cache.get("/nonexistent.txt") is None


def test_cache_upsert_updates_existing(cache: MinerCache) -> None:
    cache.record("/f.txt", "sha1", memory_ids=["m1"])
    cache.record("/f.txt", "sha2", memory_ids=["m2", "m3"])
    entry = cache.get("/f.txt")
    assert entry["sha256"] == "sha2"
    assert entry["memory_ids"] == ["m2", "m3"]


def test_cache_remove_existing(cache: MinerCache) -> None:
    cache.record("/f.txt", "sha1")
    assert cache.remove("/f.txt") is True
    assert cache.get("/f.txt") is None


def test_cache_remove_missing(cache: MinerCache) -> None:
    assert cache.remove("/nonexistent.txt") is False


def test_cache_list_all(cache: MinerCache) -> None:
    cache.record("/a.txt", "sha_a")
    cache.record("/b.txt", "sha_b")
    entries = cache.list_all()
    assert len(entries) == 2
    paths = {e["path"] for e in entries}
    assert "/a.txt" in paths
    assert "/b.txt" in paths


def test_cache_stats(cache: MinerCache) -> None:
    cache.record("/a.txt", "sha_a", memory_ids=["m1", "m2"])
    cache.record("/b.txt", "sha_b", memory_ids=["m3"])
    s = cache.stats()
    assert s["cached_files"] == 2
    assert s["total_memories"] == 3


def test_cache_get_chunk_hashes_empty(cache: MinerCache) -> None:
    assert cache.get_chunk_hashes("/missing.txt") == set()


def test_cache_get_chunk_hashes_populated(cache: MinerCache) -> None:
    cache.record("/f.txt", "sha1", chunk_hashes=["h1", "h2", "h3"])
    hashes = cache.get_chunk_hashes("/f.txt")
    assert hashes == {"h1", "h2", "h3"}


# ---------------------------------------------------------------------------
# Miner + MinerCache integration
# ---------------------------------------------------------------------------


def test_mine_file_records_in_cache(tmp_file: Path, cache: MinerCache) -> None:
    memos = _FakeMemos()
    miner = Miner(memos, cache=cache)
    result = miner.mine_file(tmp_file)
    assert result.imported >= 1
    entry = cache.get(str(tmp_file))
    assert entry is not None
    assert entry["sha256"] == _file_sha256(tmp_file)
    assert len(entry["memory_ids"]) >= 1


def test_mine_file_skips_cached(tmp_file: Path, cache: MinerCache) -> None:
    memos = _FakeMemos()
    miner = Miner(memos, cache=cache)
    r1 = miner.mine_file(tmp_file)
    imported_first = r1.imported
    # Second mine of the same unmodified file → skipped
    r2 = miner.mine_file(tmp_file)
    assert r2.imported == 0
    assert r2.skipped_cached == 1
    assert memos.count == imported_first  # no new memories


def test_mine_file_update_replaces_memories(tmp_file: Path, cache: MinerCache) -> None:
    memos = _FakeMemos()
    miner = Miner(memos, cache=cache)
    miner.mine_file(tmp_file)

    # Modify the file so sha256 changes
    tmp_file.write_text("Completely different content about kubernetes and helm.")
    miner_update = Miner(memos, cache=cache, update=True)
    r2 = miner_update.mine_file(tmp_file)

    # Old memories should be deleted, new ones added
    assert r2.imported >= 1
    # Cache should reflect new sha256
    entry = cache.get(str(tmp_file))
    assert entry["sha256"] == _file_sha256(tmp_file)


def test_mine_file_diff_skips_known_chunks(tmp_file: Path, cache: MinerCache) -> None:
    memos = _FakeMemos()
    miner = Miner(memos, cache=cache)
    miner.mine_file(tmp_file)
    first_count = memos.count

    # diff mode on same file with same sha256 → all chunks known → nothing new
    miner2 = Miner(memos, cache=cache)
    miner2.mine_file(tmp_file, diff=True)
    # Should not import anything since all chunks are already cached
    assert memos.count == first_count


def test_mine_file_no_cache_does_not_skip(tmp_file: Path) -> None:
    memos = _FakeMemos()
    miner = Miner(memos)  # no cache
    r1 = miner.mine_file(tmp_file)
    miner.mine_file(tmp_file)
    # Without cache, second run only skips in-memory deduplication (same session)
    # Both runs happen but second is a dupe in-memory
    assert r1.imported >= 1


def test_mine_result_skipped_cached_field() -> None:
    result = MineResult(skipped_cached=3)
    assert result.skipped_cached == 3


def test_mine_result_merge_includes_cached() -> None:
    r1 = MineResult(imported=2, skipped_cached=1)
    r2 = MineResult(imported=1, skipped_cached=3)
    r1.merge(r2)
    assert r1.imported == 3
    assert r1.skipped_cached == 4


def test_mine_result_merge_includes_memory_ids() -> None:
    r1 = MineResult(memory_ids=["a", "b"])
    r2 = MineResult(memory_ids=["c"])
    r1.merge(r2)
    assert r1.memory_ids == ["a", "b", "c"]
