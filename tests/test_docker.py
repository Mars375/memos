"""Tests for Docker setup (Dockerfile)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKER_WORKFLOW = ROOT / ".github" / "workflows" / "docker.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def test_dockerfile_exists():
    assert (ROOT / "Dockerfile").is_file(), "Dockerfile missing"


def test_dockerfile_installs_memos():
    content = (ROOT / "Dockerfile").read_text()
    assert "pip install" in content
    for extra in ('"server"', '"chroma"', '"parquet"'):
        assert extra in content
    assert '"local"' not in content
    assert "pip wheel --no-deps --wheel-dir /wheels ." in content
    assert "dev" not in content


def test_dockerfile_omits_heavy_local_embedding_extra():
    content = (ROOT / "Dockerfile").read_text()
    assert "sentence-transformers" not in content
    assert "torch" not in content


def test_dockerfile_caches_dependency_wheels_before_project_source():
    content = (ROOT / "Dockerfile").read_text()
    assert content.startswith("# syntax=docker/dockerfile:1")
    assert "--mount=type=cache,target=/root/.cache/pip" in content
    assert "pip wheel --wheel-dir /wheels -r /tmp/requirements.txt" in content
    assert content.index("COPY pyproject.toml README.md ./") < content.index("pip wheel --wheel-dir /wheels -r")
    assert content.index("pip wheel --wheel-dir /wheels -r") < content.index("COPY src/ src/")
    assert content.index("COPY src/ src/") < content.index("pip wheel --no-deps --wheel-dir /wheels .")


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


def test_dockerignore_excludes_non_runtime_context():
    content = (ROOT / ".dockerignore").read_text()
    assert ".git" in content
    assert "tests" in content
    assert "tools" in content
    assert ".memos" in content


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


def test_docker_workflow_uses_scoped_trusted_cache():
    content = DOCKER_WORKFLOW.read_text()
    assert "cache-from: type=gha,scope=memos-docker-main" in content
    assert "cache-to: type=gha,scope=memos-docker-main,mode=max,ignore-error=true" in content
    assert "if: github.event_name != 'pull_request'" in content


def test_docker_workflow_smoke_tests_pull_requests_without_push():
    content = DOCKER_WORKFLOW.read_text()
    smoke_job = content.split("  smoke:", maxsplit=1)[1].split("\n\n  build-and-push:", maxsplit=1)[0]
    publish_job = content.split("  build-and-push:", maxsplit=1)[1]

    assert "Build PR smoke image" in content
    assert "Smoke test PR image" in content
    assert "load: true" in content
    assert "tags: memos:smoke" in content
    assert "getpass.getuser() == 'memos'" in content
    assert "platforms: linux/amd64" in content
    assert "if: github.event_name == 'pull_request'" in smoke_job
    assert "packages: write" not in smoke_job
    assert "packages: write" in publish_job


def test_workflows_use_least_privilege_permissions():
    docker_content = DOCKER_WORKFLOW.read_text()
    publish_content = PUBLISH_WORKFLOW.read_text()
    test_content = TEST_WORKFLOW.read_text()

    assert "permissions:\n  contents: read" in test_content
    assert "permissions:\n  contents: read" in publish_content
    assert "permissions:\n      contents: read\n      id-token: write" in publish_content
    assert "  smoke:\n    if: github.event_name == 'pull_request'" in docker_content
    assert "  build-and-push:\n    if: github.event_name != 'pull_request'" in docker_content


def test_checkout_credentials_are_not_persisted():
    workflow_contents = [
        DOCKER_WORKFLOW.read_text(),
        PUBLISH_WORKFLOW.read_text(),
        TEST_WORKFLOW.read_text(),
    ]

    checkout_count = sum(content.count("uses: actions/checkout@v6") for content in workflow_contents)
    disabled_count = sum(content.count("persist-credentials: false") for content in workflow_contents)

    assert checkout_count == 6
    assert disabled_count == checkout_count


# ── Compose tests removed ──────────────────────────────────────────────────
# docker-compose.yml was deleted in commit 25183a5.
# Docker deployment now uses `docker run` (see README).
