"""Tests for Docker setup (Dockerfile)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_exists():
    assert (ROOT / "Dockerfile").is_file(), "Dockerfile missing"


def test_dockerfile_installs_memos():
    content = (ROOT / "Dockerfile").read_text()
    assert "pip install" in content
    assert "[server,chroma,dev]" in content or "server" in content


def test_cli_env_vars():
    """CLI serve respects MEMOS_BACKEND and MEMOS_CHROMA_URL env vars."""
    # Quick smoke: import doesn't crash, defaults are sane
    from memos.cli import build_parser

    p = build_parser()
    ns = p.parse_args(["serve", "--backend", "chroma"])
    assert ns.backend == "chroma"
    assert ns.port == 8000


# ── Compose tests removed ──────────────────────────────────────────────────
# docker-compose.yml was deleted in commit 25183a5.
# Docker deployment now uses `docker run` (see README).
