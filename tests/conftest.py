"""Shared test fixtures for MemOS test suite."""

from __future__ import annotations

import pytest
from memos.core import MemOS
from memos.knowledge_graph import KnowledgeGraph
from memos.api import create_fastapi_app
from memos.storage.memory_backend import InMemoryBackend

# --- MemOS instances ---


@pytest.fixture()
def memos_empty() -> MemOS:
    """Bare in-memory MemOS instance (no data)."""
    return MemOS(backend="memory")


# Alias for backward compat — many test files use `mem` for an empty MemOS
@pytest.fixture()
def mem(memos_empty) -> MemOS:
    """Backward-compat alias."""
    return memos_empty


@pytest.fixture()
def memos_with_sample_data() -> MemOS:
    """In-memory MemOS pre-populated with 3 memories (alpha, beta, gamma)."""
    mem = MemOS(backend="memory")
    mem.learn("Alpha memory about python programming", tags=["python", "coding"], importance=0.8)
    mem.learn("Beta memory about async patterns", tags=["async", "python"], importance=0.6)
    mem.learn("Gamma memory about devops deployment", tags=["devops", "docker"], importance=0.7)
    return mem


# --- KnowledgeGraph ---


@pytest.fixture()
def kg():
    """In-memory KnowledgeGraph (yield with cleanup)."""
    graph = KnowledgeGraph(db_path=":memory:")
    yield graph
    graph.close()


# --- FastAPI app + client ---


@pytest.fixture()
def app(memos_empty):
    """FastAPI test app with in-memory backend."""
    return create_fastapi_app(memos=memos_empty)


@pytest.fixture()
def client(app):
    """TestClient for the FastAPI app."""
    from starlette.testclient import TestClient

    return TestClient(app)
