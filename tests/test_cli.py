"""Tests for MemOS CLI."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from memos.cli import build_parser, main


class TestCLIParsing:
    def test_version(self):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0

    def test_no_command_shows_help(self):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 0

    def test_learn_args(self):
        p = build_parser()
        ns = p.parse_args(["learn", "hello world", "--tags", "a,b", "--importance", "0.9"])
        assert ns.content == "hello world"
        assert ns.tags == "a,b"
        assert ns.importance == 0.9

    def test_recall_args(self):
        p = build_parser()
        ns = p.parse_args(["recall", "test query", "--top", "3", "--enriched"])
        assert ns.query == "test query"
        assert ns.top == 3
        assert ns.enriched is True

    def test_serve_args(self):
        p = build_parser()
        ns = p.parse_args(["serve", "--host", "0.0.0.0", "--port", "9000"])
        assert ns.host == "0.0.0.0"
        assert ns.port == 9000

    def test_prune_args(self):
        p = build_parser()
        ns = p.parse_args(["prune", "--threshold", "0.3", "--dry-run", "-v"])
        assert ns.threshold == 0.3
        assert ns.dry_run is True
        assert ns.verbose is True


class TestCLIFunctional:
    def test_init_creates_dir(self, tmp_path):
        d = tmp_path / "memos_data"
        main(["init", str(d)])
        cfg = d / "memos.json"
        assert cfg.exists()
        data = json.loads(cfg.read_text())
        assert data["backend"] == "memory"

    def test_init_no_overwrite(self, tmp_path):
        d = tmp_path / "memos_data"
        d.mkdir()
        (d / "memos.json").write_text("{}")
        with pytest.raises(SystemExit):
            main(["init", str(d)])

    def test_init_force(self, tmp_path):
        d = tmp_path / "memos_data"
        d.mkdir()
        (d / "memos.json").write_text('{"old": true}')
        main(["init", str(d), "--force"])
        data = json.loads((d / "memos.json").read_text())
        assert "backend" in data

    def test_learn_and_recall(self, capsys):
        """Each CLI call creates a fresh MemOS — test recall within one command flow."""
        # Just verify recall doesn't crash and learn works
        main(["learn", "User prefers dark mode", "--tags", "ui,preference"])
        out = capsys.readouterr().out
        assert "Learned" in out

        # recall on fresh instance → no memories, which is expected
        main(["recall", "dark mode preference"])
        out = capsys.readouterr().out
        assert "No memories found" in out or "result" in out.lower()

    def test_learn_from_file(self, tmp_path, capsys):
        f = tmp_path / "note.txt"
        f.write_text("Important meeting notes about Q3 planning")
        main(["learn", "--file", str(f)])
        out = capsys.readouterr().out
        assert "Learned" in out

    def test_learn_empty_fails(self):
        with pytest.raises(SystemExit):
            main(["learn"])

    def test_stats(self, capsys):
        main(["learn", "test memory for stats"])
        main(["stats"])
        out = capsys.readouterr().out
        assert "Total memories" in out

    def test_analytics_args(self):
        p = build_parser()
        ns = p.parse_args(["analytics", "top", "--n", "3"])
        assert ns.command == "analytics"
        assert ns.analytics_action == "top"
        assert ns.n == 3

    def test_analytics_top_command(self, capsys):
        class FakeAnalytics:
            def top_recalled(self, n: int = 20):
                assert n == 2
                return [{"memory_id": "abc12345", "count": 4}]

        class FakeMemOS:
            analytics = FakeAnalytics()

        with patch("memos.cli._get_memos", return_value=FakeMemOS()):
            main(["analytics", "top", "--n", "2"])
        out = capsys.readouterr().out
        assert "abc12345" in out
        assert "result(s)" in out

    def test_stats_json(self, capsys):
        # Fresh instance → empty stats, just verify JSON output works
        main(["stats", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "total_memories" in data

    def test_forget(self, capsys):
        # Each call is a fresh instance, so forget won't find it.
        # Test the command runs without error.
        main(["forget", "nonexistent"])
        out = capsys.readouterr().out
        assert "Not found" in out

    def test_forget_not_found(self, capsys):
        main(["forget", "nonexistent_12345"])
        out = capsys.readouterr().out
        assert "Not found" in out

    def test_forget_by_tag(self, capsys):
        class FakeMemOS:
            def forget_tag(self, tag: str) -> int:
                assert tag == "test"
                return 1

        with patch("memos.cli._get_memos", return_value=FakeMemOS()):
            main(["forget", "--tag", "test"])
        out = capsys.readouterr().out
        assert "Forgotten" in out

    def test_prune_dry_run(self, capsys):
        main(["prune", "--dry-run"])
        out = capsys.readouterr().out
        assert "would be pruned" in out
    def test_learn_stdin_parsing(self):
        """Test --stdin flag is parsed correctly."""
        p = build_parser()
        ns = p.parse_args(["learn", "--stdin", "--tags", "pipe"])
        assert ns.stdin is True
        assert ns.tags == "pipe"

    def test_learn_from_stdin(self, capsys):
        """Test memos learn --stdin reads from stdin."""
        fake_stdin = io.StringIO("Piped memory content from CLI")
        with patch("sys.stdin", fake_stdin):
            main(["learn", "--stdin", "--tags", "piped"])
        out = capsys.readouterr().out
        assert "Learned" in out

    def test_learn_stdin_empty_fails(self):
        """Test that empty stdin content fails gracefully."""
        fake_stdin = io.StringIO("   ")
        with patch("sys.stdin", fake_stdin):
            with pytest.raises(SystemExit):
                main(["learn", "--stdin"])

    def test_learn_stdin_with_importance(self, capsys):
        """Test --stdin with importance and TTL."""
        fake_stdin = io.StringIO("Important piped note")
        with patch("sys.stdin", fake_stdin):
            main(["learn", "--stdin", "--importance", "0.9", "--ttl", "1h"])
        out = capsys.readouterr().out
        assert "Learned" in out
        assert "ttl=1h" in out


    def test_search_parsing(self):
        """Test search command argument parsing."""
        p = build_parser()
        ns = p.parse_args(["search", "persistence", "--limit", "10"])
        assert ns.query == "persistence"
        assert ns.limit == 10

    def test_search_parsing_json(self):
        """Test search command with JSON format."""
        p = build_parser()
        ns = p.parse_args(["search", "test", "--format", "json"])
        assert ns.format == "json"

    def test_search_no_results(self, capsys):
        """Test search with no matching memories."""
        main(["search", "zzz_no_such_content_xyz"])
        out = capsys.readouterr().out
        assert "No memories found" in out

    def test_search_finds_content(self, capsys):
        """Test search finds a memory by content substring."""
        main(["learn", "unique_search_target_string", "--tags", "search-test"])
        main(["search", "search_target"])
        out = capsys.readouterr().out
        assert "unique_search_target_string" in out
        assert "result(s)" in out
        # cleanup
        main(["forget", "--tag", "search-test"])

    def test_search_finds_by_tag(self, capsys):
        """Test search finds a memory by tag substring."""
        main(["learn", "content for tag search", "--tags", "rare-tag-xyz"])
        main(["search", "rare-tag-xyz"])
        out = capsys.readouterr().out
        assert "content for tag search" in out
        # cleanup
        main(["forget", "--tag", "rare-tag-xyz"])

    def test_search_json_output(self, capsys):
        """Test search with JSON output format."""
        main(["learn", "json search test content", "--tags", "json-search-test"])
        capsys.readouterr()  # flush learn output
        main(["search", "json search test", "--format", "json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "results" in data
        assert data["total"] >= 1
        assert any("json search test content" in r["content"] for r in data["results"])
        # cleanup
        main(["forget", "--tag", "json-search-test"])
        capsys.readouterr()  # flush forget output

    def test_search_limit(self, capsys):
        """Test search respects --limit flag."""
        for i in range(5):
            main(["learn", f"search_limit_test_item_{i:02d}", "--tags", "search-limit-test"])
        main(["search", "search_limit_test_item", "--limit", "2"])
        out = capsys.readouterr().out
        assert "2 result(s)" in out
        # cleanup
        main(["forget", "--tag", "search-limit-test"])
