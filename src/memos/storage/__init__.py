"""Storage backends."""

from .base import StorageBackend
from .async_base import AsyncStorageBackend
from .async_wrapper import AsyncWrapper
from .memory_backend import InMemoryBackend

__all__ = [
    "StorageBackend",
    "AsyncStorageBackend",
    "AsyncWrapper",
    "InMemoryBackend",
    "ChromaBackend",
    "QdrantBackend",
]


def __getattr__(name: str):
    if name == "ChromaBackend":
        from .chroma_backend import ChromaBackend
        return ChromaBackend
    if name == "QdrantBackend":
        from .qdrant_backend import QdrantBackend
        return QdrantBackend
    raise AttributeError(name)
