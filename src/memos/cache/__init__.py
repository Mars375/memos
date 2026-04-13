"""Embedding cache — persistent disk-backed LRU cache for vector embeddings."""

from .embedding_cache import CacheStats, EmbeddingCache

__all__ = ["EmbeddingCache", "CacheStats"]
