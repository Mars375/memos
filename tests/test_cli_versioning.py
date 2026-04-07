"""Tests for CLI versioning commands (v0.12.0)."""

import json
import time
import pytest
from unittest.mock import patch
from memos.cli import main, _parse_timestamp, _fmt_ts
from memos.core import MemOS


@pytest.fixture
def mem():
    """Create a MemOS instance for testing."""
    return MemOS(backend="memory")


@pytest.fixture
def mem_with_versions(mem):
    """Create a MemOS instance with versioned memories."""
    item1 = mem.learn("Initial content about AI", tags=["ai"], importance=0.5)
    time.sleep(0.01)
    # Update by learning similar content (creates new item)
    # For versioning, we need to use the same item_id
    # Let's learn then update via storage upsert
    mem.learn("Updated content about AI and ML", tags=["ai", "ml"], importance=0.7)
    time.sleep(0.01)
    mem.learn("Final content about AI, ML, and deep learning", tags=["ai", "ml", "dl"], importance=0.9)

    item2 = mem.learn("Separate memory about cooking", tags=["food"], importance=0.3)
    time.sleep(0.01)
    # For true version history, we need the same item to be updated
    # Let's use storage.upsert directly
    from memos.models import MemoryItem
    updated_item1 = MemoryItem(
        id=item1.id,
        content="Updated content about AI and ML",
        tags=["ai", "ml"],
        importance=0.7,
    )
    mem._store.upsert(updated_item1)
    mem.versioning.record_version(updated_item1, source="upsert")
    time.sleep(0.01)

    final_item1 = MemoryItem(
        id=item1.id,
        content="Final content about AI, ML, and deep learning",
        tags=["ai", "ml", "dl"],
        importance=0.9,
    )
    mem._store.upsert(final_item1)
    mem.versioning.record_version(final_item1, source="upsert")

    return mem, item1.id, item2.id


@pytest.fixture
def mock_mem(mem):
    """Patch _get_memos to return our shared MemOS instance."""
    with patch('memos.cli._get_memos', return_value=mem):
        yield mem


class TestTimestampParsing:
    """Tests for _parse_timestamp helper."""

    def test_epoch_float(self):
        ts = 1712457600.0
        assert _parse_timestamp(str(ts)) == ts

    def test_epoch_int(self):
        ts = 1712457600
        assert _parse_timestamp(str(ts)) == float(ts)

    def test_iso_8601_date(self):
        result = _parse_timestamp("2024-04-07")
        assert result > 1712419200

    def test_iso_8601_datetime(self):
        result = _parse_timestamp("2024-04-07T12:00:00")
        assert result > 0

    def test_relative_hours(self):
        result = _parse_timestamp("1h")
        expected = time.time() - 3600
        assert abs(result - expected) < 1

    def test_relative_days(self):
        result = _parse_timestamp("2d")
        expected = time.time() - 2 * 86400
        assert abs(result - expected) < 1

    def test_relative_weeks(self):
        result = _parse_timestamp("1w")
        expected = time.time() - 604800
        assert abs(result - expected) < 1

    def test_relative_minutes(self):
        result = _parse_timestamp("30m")
        expected = time.time() - 1800
        assert abs(result - expected) < 1

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_timestamp("not-a-timestamp")


class TestFmtTs:
    """Tests for _fmt_ts helper."""

    def test_basic(self):
        result = _fmt_ts(1712457600.0)
        assert "2024" in result
        assert ":" in result

    def test_now(self):
        result = _fmt_ts(time.time())
        assert len(result) == 19


class TestCmdHistory:
    """Tests for 'memos history' command."""

    def test_history_basic(self, mem_with_versions, mock_mem, capsys):
        mem, item1_id, _ = mem_with_versions
        main(["history", item1_id, "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Version history" in out
        assert "v  1" in out
        assert "v  2" in out
        assert "v  3" in out

    def test_history_json(self, mem_with_versions, mock_mem, capsys):
        mem, item1_id, _ = mem_with_versions
        main(["history", item1_id, "--json", "--backend", "memory"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_history_no_versions(self, mem, mock_mem, capsys):
        item = mem.learn("No versions test")
        mem.versioning.clear()
        main(["history", item.id, "--backend", "memory"])
        out = capsys.readouterr().out
        assert "No version history" in out


class TestCmdDiff:
    """Tests for 'memos diff' command."""

    def test_diff_versions(self, mem_with_versions, mock_mem, capsys):
        mem, item1_id, _ = mem_with_versions
        main(["diff", item1_id, "--v1", "1", "--v2", "3", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Diff:" in out
        assert "v1 -> v3" in out

    def test_diff_latest(self, mem_with_versions, mock_mem, capsys):
        mem, item1_id, _ = mem_with_versions
        main(["diff", item1_id, "--latest", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Diff:" in out

    def test_diff_json(self, mem_with_versions, mock_mem, capsys):
        mem, item1_id, _ = mem_with_versions
        main(["diff", item1_id, "--v1", "1", "--v2", "2", "--json", "--backend", "memory"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "from_version" in data
        assert "changes" in data
        assert "content" in data["changes"]

    def test_diff_no_versions(self, mem, mock_mem, capsys):
        item = mem.learn("Single version")
        main(["diff", item.id, "--latest", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Fewer than 2 versions" in out


class TestCmdRollback:
    """Tests for 'memos rollback' command."""

    def test_rollback_dry_run(self, mem_with_versions, mock_mem, capsys):
        mem, item1_id, _ = mem_with_versions
        main(["rollback", item1_id, "--version", "1", "--dry-run", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Would roll back" in out
        assert "dry-run" in out

    def test_rollback_preview(self, mem_with_versions, mock_mem, capsys):
        mem, item1_id, _ = mem_with_versions
        main(["rollback", item1_id, "--version", "1", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Will roll back" in out
        assert "Use --yes to confirm" in out

    def test_rollback_confirmed(self, mem_with_versions, mock_mem, capsys):
        mem, item1_id, _ = mem_with_versions
        main(["rollback", item1_id, "--version", "1", "--yes", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "OK Rolled back" in out
        # Verify the content was actually rolled back
        results = mem.recall("Initial content about AI", top=5)
        assert len(results) > 0

    def test_rollback_version_not_found(self, mem, mock_mem, capsys):
        item = mem.learn("Test item")
        with pytest.raises(SystemExit):
            main(["rollback", item.id, "--version", "999", "--yes", "--backend", "memory"])


class TestCmdSnapshotAt:
    """Tests for 'memos snapshot-at' command."""

    def test_snapshot_basic(self, mem_with_versions, mock_mem, capsys):
        mem, item1_id, item2_id = mem_with_versions
        main(["snapshot-at", str(time.time()), "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Snapshot at" in out
        assert "memories" in out

    def test_snapshot_json(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["snapshot-at", str(time.time()), "--json", "--backend", "memory"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)

    def test_snapshot_past(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["snapshot-at", "0", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "no memories" in out

    def test_snapshot_relative(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["snapshot-at", "1w", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Snapshot at" in out


class TestCmdRecallAt:
    """Tests for 'memos recall-at' command."""

    def test_recall_at_basic(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["recall-at", "AI", "--at", str(time.time()), "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Recall at" in out

    def test_recall_at_json(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["recall-at", "AI", "--at", str(time.time()), "--json", "--backend", "memory"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)

    def test_recall_at_past(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["recall-at", "AI", "--at", "0", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "No memories found" in out


class TestCmdVersionStats:
    """Tests for 'memos version-stats' command."""

    def test_version_stats_basic(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["version-stats", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Versioning Statistics" in out
        assert "Total versions" in out
        assert "Tracked items" in out

    def test_version_stats_json(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["version-stats", "--json", "--backend", "memory"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "total_versions" in data
        assert "total_items" in data or "tracked_items" in data
        assert data["total_versions"] > 0


class TestCmdVersionGC:
    """Tests for 'memos version-gc' command."""

    def test_version_gc_dry_run(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["version-gc", "--dry-run", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Current:" in out
        assert "Would remove" in out

    def test_version_gc_no_old_versions(self, mem_with_versions, mock_mem, capsys):
        mem, _, _ = mem_with_versions
        main(["version-gc", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "OK Garbage collected" in out


class TestCLIVersioningIntegration:
    """Integration tests for versioning CLI commands end-to-end."""

    def test_full_versioning_workflow(self, mem, mock_mem, capsys):
        """Learn -> update -> history -> diff -> rollback -> verify."""
        from memos.models import MemoryItem

        # Learn initial
        item = mem.learn("Version 1: hello world", tags=["v1"], importance=0.5)
        time.sleep(0.01)

        # Update to v2
        v2 = MemoryItem(id=item.id, content="Version 2: hello world updated", tags=["v1", "v2"], importance=0.7)
        mem._store.upsert(v2)
        mem.versioning.record_version(v2, source="upsert")
        time.sleep(0.01)

        # Update to v3
        v3 = MemoryItem(id=item.id, content="Version 3: final version", tags=["v1", "v2", "v3"], importance=0.9)
        mem._store.upsert(v3)
        mem.versioning.record_version(v3, source="upsert")

        # History
        main(["history", item.id, "--backend", "memory"])
        out = capsys.readouterr().out
        assert "3 versions" in out

        # Diff
        main(["diff", item.id, "--v1", "1", "--v2", "3", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "v1 -> v3" in out

        # Stats
        main(["version-stats", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "Total versions" in out

        # Rollback
        main(["rollback", item.id, "--version", "1", "--yes", "--backend", "memory"])
        out = capsys.readouterr().out
        assert "OK Rolled back" in out

        # Verify rollback created a new version
        versions = mem.history(item.id)
        assert len(versions) == 4  # 3 originals + 1 rollback
        last = versions[-1]
        assert "rollback" in last.source
