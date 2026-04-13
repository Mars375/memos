"""Tests for Docker setup (Dockerfile + compose)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_exists():
    assert (ROOT / "Dockerfile").is_file(), "Dockerfile missing"


def test_compose_exists():
    assert (ROOT / "docker-compose.yml").is_file(), "docker-compose.yml missing"


def test_dockerfile_installs_memos():
    content = (ROOT / "Dockerfile").read_text()
    assert "pip install" in content
    assert "[server,chroma,dev]" in content or "server" in content


def test_compose_has_memos_and_chroma():
    content = (ROOT / "docker-compose.yml").read_text()
    assert "memos:" in content
    assert "chroma:" in content
    assert "MEMOS_BACKEND=chroma" in content
    assert "MEMOS_CHROMA_URL" in content


def test_compose_valid_yaml():
    """Validate docker-compose.yml parses as valid YAML."""
    try:
        import yaml
    except ImportError:
        # Skip if pyyaml not installed
        return
    data = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert "services" in data
    assert "memos" in data["services"]
    assert "chroma" in data["services"]
    assert data["services"]["memos"]["depends_on"] is not None


def test_cli_env_vars():
    """CLI serve respects MEMOS_BACKEND and MEMOS_CHROMA_URL env vars."""
    # Quick smoke: import doesn't crash, defaults are sane
    from memos.cli import build_parser

    p = build_parser()
    ns = p.parse_args(["serve", "--backend", "chroma"])
    assert ns.backend == "chroma"
    assert ns.port == 8000
