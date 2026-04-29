"""Tests for Docker setup (Dockerfile)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_exists():
    assert (ROOT / "Dockerfile").is_file(), "Dockerfile missing"


def test_dockerfile_installs_memos():
    content = (ROOT / "Dockerfile").read_text()
    assert "pip install" in content
    assert ".[server,chroma,local,parquet]" in content
    assert "dev" not in content


def test_dockerfile_uses_multistage_non_root_runtime():
    content = (ROOT / "Dockerfile").read_text()
    assert "FROM python:3.11-slim AS builder" in content
    assert "FROM python:3.11-slim AS runtime" in content
    assert "USER memos" in content
    assert "build-essential" in content
    runtime_stage = content.split("FROM python:3.11-slim AS runtime", maxsplit=1)[1]
    assert "build-essential" not in runtime_stage


def test_dockerfile_excludes_tests_and_tools_from_runtime_image():
    content = (ROOT / "Dockerfile").read_text()
    assert "COPY tests/" not in content
    assert "COPY tools/" not in content


def test_dockerfile_sets_data_volume_defaults_and_healthcheck():
    content = (ROOT / "Dockerfile").read_text()
    assert "ENV MEMOS_PERSIST_PATH=/data/.memos/store.json" in content
    assert "ENV MEMOS_CACHE_PATH=/data/.memos/embeddings.db" in content
    assert "HEALTHCHECK" in content


def test_readme_uses_non_root_docker_volume_path():
    content = (ROOT / "README.md").read_text()
    assert "-v memos-data:/data/.memos" in content
    assert "/root/.memos" not in content


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
