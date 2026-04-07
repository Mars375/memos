"""Embedding cache — persistent disk-backed LRU cache for vector embeddings."""

from .embedding_cache import EmbeddingCache, CacheStats

__all__ = ["EmbeddingCache", "CacheStats"]
