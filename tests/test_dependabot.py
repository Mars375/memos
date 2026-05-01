"""Tests for Dependabot maintenance configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPENDABOT_CONFIG = ROOT / ".github" / "dependabot.yml"


def test_dependabot_groups_python_dependencies():
    content = DEPENDABOT_CONFIG.read_text()
    pip_section = content.split("  - package-ecosystem: pip", maxsplit=1)[1].split(
        "  - package-ecosystem: github-actions",
        maxsplit=1,
    )[0]

    assert "groups:" in pip_section
    assert "python-dependencies:" in pip_section
    assert '          - "*"' in pip_section


def test_dependabot_groups_github_actions_dependencies():
    content = DEPENDABOT_CONFIG.read_text()
    actions_section = content.split("  - package-ecosystem: github-actions", maxsplit=1)[1]

    assert "groups:" in actions_section
    assert "github-actions:" in actions_section
    assert '          - "*"' in actions_section
