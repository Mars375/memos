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
]

# ChromaBackend imported lazily to avoid hard dep on chromadb
def __getattr__(name: str):
    if name == "ChromaBackend":
        from .chroma_backend import ChromaBackend
        return ChromaBackend
    raise AttributeError(name)
