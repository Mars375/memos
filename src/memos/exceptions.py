"""Lightweight exception hierarchy for MemOS.

This module defines a small, stable base of domain-specific exceptions.
It is intentionally *behaviour-neutral*: no existing code raises these yet.
The hierarchy exists so that future refactors can narrow ``raise`` sites
and callers can ``except`` on concrete types without breaking changes.
"""


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class MemosError(Exception):
    """Base exception for all MemOS domain errors."""


# ---------------------------------------------------------------------------
# Storage layer
# ---------------------------------------------------------------------------


class StorageError(MemosError):
    """Base for storage-backend failures."""


class StorageConnectionError(StorageError):
    """Could not reach or initialise the storage backend."""


class StorageWriteError(StorageError):
    """Write / persist operation failed."""


class StorageReadError(StorageError):
    """Read / query operation failed."""


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


class EmbeddingError(MemosError):
    """Base for embedding-provider failures."""


class EmbeddingModelError(EmbeddingError):
    """Model could not be loaded or is missing."""


class EmbeddingHostError(EmbeddingError):
    """Remote embedding host (e.g. Ollama) is unreachable."""


# ---------------------------------------------------------------------------
# Ingest / parsing
# ---------------------------------------------------------------------------


class IngestError(MemosError):
    """Base for ingestion and parsing failures."""


class IngestParseError(IngestError):
    """Source document could not be parsed."""


class IngestChunkError(IngestError):
    """Chunking step failed."""


# ---------------------------------------------------------------------------
# Wiki engine
# ---------------------------------------------------------------------------


class WikiError(MemosError):
    """Base for living-wiki failures."""


class WikiPageError(WikiError):
    """Page creation or update failed."""


class WikiLintError(WikiError):
    """Wiki lint / consistency check failure."""


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------


class KnowledgeGraphError(MemosError):
    """Base for knowledge-graph failures."""


# ---------------------------------------------------------------------------
# API / HTTP surface
# ---------------------------------------------------------------------------


class APIError(MemosError):
    """Base for REST / MCP API failures."""


class AuthenticationError(APIError):
    """Request lacks valid credentials."""


class RateLimitError(APIError):
    """Caller exceeded rate limits."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ConfigurationError(MemosError):
    """Invalid or missing configuration."""
