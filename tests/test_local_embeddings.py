from __future__ import annotations

from pathlib import Path

import httpx

from memos.cache.embedding_cache import EmbeddingCache
from memos.core import MemOS
from memos.models import MemoryItem
from memos.retrieval.engine import RetrievalEngine
from memos.storage.memory_backend import InMemoryBackend


class _FakeEmbedder:
    model_name = "fake-local-model"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def encode(self, text: str):
        self.calls.append(text)
        text = text.lower()
        if "cat" in text or "feline" in text:
            return [1.0, 0.0]
        if "docker" in text or "container" in text:
            return [0.0, 1.0]
        return [0.1, 0.1]


def test_retrieval_engine_uses_pluggable_embedder_without_ollama(monkeypatch) -> None:
    store = InMemoryBackend()
    store.upsert(MemoryItem(id="a", content="cat sleeps on sofa"))
    store.upsert(MemoryItem(id="b", content="docker container registry"))

    engine = RetrievalEngine(store=store, embedder=_FakeEmbedder())

    def _boom(*args, **kwargs):  # pragma: no cover
        raise AssertionError("Ollama should not be called when a local embedder works")

    monkeypatch.setattr(httpx, "post", _boom)

    results = engine.search("feline friend", top=2)

    assert results
    assert results[0].item.id == "a"
    assert results[0].match_reason == "semantic"


def test_retrieval_engine_caches_local_embeddings_under_local_model_name(tmp_path: Path) -> None:
    store = InMemoryBackend()
    embedder = _FakeEmbedder()
    engine = RetrievalEngine(store=store, embedder=embedder)
    cache = EmbeddingCache(path=str(tmp_path / "embeddings.db"))
    engine.set_cache(cache)

    vec = engine._get_embedding("feline friend")

    assert vec == [1.0, 0.0]
    assert cache.get("feline friend", model="fake-local-model") == [1.0, 0.0]
    assert cache.get("feline friend", model="nomic-embed-text") is None


def test_memos_local_backend_wires_local_embedder(monkeypatch, tmp_path: Path) -> None:
    def _fake_encode(self, text: str):
        text = text.lower()
        if "cat" in text or "feline" in text:
            return [1.0, 0.0]
        if "docker" in text:
            return [0.0, 1.0]
        return [0.1, 0.1]

    def _boom(*args, **kwargs):  # pragma: no cover
        raise AssertionError("Ollama should not be used by backend='local'")

    monkeypatch.setattr("memos.embeddings.local.LocalEmbedder.encode", _fake_encode)
    monkeypatch.setattr(httpx, "post", _boom)

    mem = MemOS(
        backend="local",
        persist_path=str(tmp_path / "store.json"),
        cache_path=str(tmp_path / "embeddings.db"),
        sanitize=False,
        local_model="all-MiniLM-L6-v2",
    )
    mem.learn("cat sleeps on sofa", tags=["pet"])
    mem.learn("docker container registry", tags=["infra"])

    results = mem.recall("feline friend", top=2)

    assert results
    assert results[0].item.content == "cat sleeps on sofa"
    assert mem._retrieval._embed_model == "all-MiniLM-L6-v2"
    assert mem._retrieval._embedder is not None
