"""Tests for SkillsExporter — P10 skills-as-markdown."""

from __future__ import annotations

import argparse

from memos.skills import _SKILL_TEMPLATES, SkillsExporter, SkillsExportResult


class TestSkillsExporter:
    def test_list_skills_returns_all(self):
        exporter = SkillsExporter()
        skills = exporter.list_skills()
        assert len(skills) >= 8
        assert "memos-recall" in skills
        assert "memos-wake-up" in skills
        assert "memos-learn" in skills
        assert "memos-kg-add" in skills

    def test_export_writes_all_skills(self, tmp_path):
        exporter = SkillsExporter()
        result = exporter.export(str(tmp_path), format="claude-code")
        assert isinstance(result, SkillsExportResult)
        assert result.written == len(_SKILL_TEMPLATES)
        assert result.skipped == 0
        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == len(_SKILL_TEMPLATES)

    def test_export_creates_output_dir(self, tmp_path):
        out = tmp_path / "nested" / "commands"
        exporter = SkillsExporter()
        exporter.export(str(out))
        assert out.is_dir()

    def test_export_skips_existing_by_default(self, tmp_path):
        exporter = SkillsExporter()
        # First export
        exporter.export(str(tmp_path))
        # Second export — all files exist, should skip all
        result = exporter.export(str(tmp_path))
        assert result.written == 0
        assert result.skipped == len(_SKILL_TEMPLATES)

    def test_export_overwrite_flag(self, tmp_path):
        exporter = SkillsExporter()
        exporter.export(str(tmp_path))
        result = exporter.export(str(tmp_path), overwrite=True)
        assert result.written == len(_SKILL_TEMPLATES)
        assert result.skipped == 0

    def test_export_specific_skills(self, tmp_path):
        exporter = SkillsExporter()
        result = exporter.export(str(tmp_path), skills=["memos-recall", "memos-stats"])
        assert result.written == 2
        assert (tmp_path / "memos-recall.md").exists()
        assert (tmp_path / "memos-stats.md").exists()
        assert not (tmp_path / "memos-learn.md").exists()

    def test_export_result_str(self, tmp_path):
        exporter = SkillsExporter()
        result = exporter.export(str(tmp_path))
        s = str(result)
        assert "written=" in s
        assert "skipped=" in s

    def test_claude_code_format_replaces_query(self, tmp_path):
        exporter = SkillsExporter()
        exporter.export(str(tmp_path), format="claude-code")
        recall_content = (tmp_path / "memos-recall.md").read_text()
        # $QUERY should be replaced with $ARGUMENTS for Claude Code
        assert "$ARGUMENTS" in recall_content or "$QUERY" not in recall_content

    def test_skill_content_is_valid_markdown(self, tmp_path):
        exporter = SkillsExporter()
        exporter.export(str(tmp_path))
        for md_file in tmp_path.glob("*.md"):
            content = md_file.read_text()
            assert content.startswith("# ")  # H1 header

    def test_unknown_skill_silently_skipped(self, tmp_path):
        exporter = SkillsExporter()
        result = exporter.export(str(tmp_path), skills=["nonexistent-skill"])
        assert result.written == 0


class TestCLI:
    def test_skills_export_cli(self, tmp_path, capsys):
        from memos.cli import cmd_skills_export

        ns = argparse.Namespace(
            output=str(tmp_path),
            format="claude-code",
            skills=None,
            overwrite=False,
            list_skills=False,
            with_context=False,
        )
        cmd_skills_export(ns)
        out = capsys.readouterr().out
        assert "Skills exported to:" in out
        assert "Written:" in out

    def test_skills_list_flag(self, tmp_path, capsys):
        from memos.cli import cmd_skills_export

        ns = argparse.Namespace(
            output=str(tmp_path),
            format="claude-code",
            skills=None,
            overwrite=False,
            list_skills=True,
            with_context=False,
        )
        cmd_skills_export(ns)
        out = capsys.readouterr().out
        assert "memos-recall" in out
        # Nothing should be written when --list is used
        assert not list(tmp_path.glob("*.md"))

    def test_skills_export_cli_command_registered(self):
        """skills-export must appear in the memos help output."""
        import subprocess

        result = subprocess.run(["memos", "--help"], capture_output=True, text=True)
        assert "skills-export" in result.stdout or "skills-export" in result.stderr
