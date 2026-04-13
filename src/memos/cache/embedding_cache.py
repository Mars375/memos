"""Persistent embedding cache backed by SQLite.

Avoids recomputing embeddings for the same text across sessions.
Supports configurable TTL, max size, and provides hit/miss statistics.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional


@dataclass
class CacheStats:
    """Cache performance statistics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0
    max_size: int = 0
    hit_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "size": self.size,
            "max_size": self.max_size,
            "hit_rate": round(self.hit_rate, 4),
        }


class EmbeddingCache:
    """SQLite-backed persistent embedding cache.

    Features:
    - Deterministic key from text content + model name
    - Configurable TTL (time-to-live) per entry
    - LRU eviction when max_size is exceeded
    - Thread-safe via a single Lock
    - Stats tracking (hits, misses, evictions)

    Usage:
        cache = EmbeddingCache(path="~/.memos/embeddings.db")
        cache.put("hello world", [0.1, 0.2, ...], model="nomic-embed-text")
        vec = cache.get("hello world", model="nomic-embed-text")
    """

    def __init__(
        self,
        path: str = "~/.memos/embeddings.db",
        *,
        max_size: int = 50_000,
        ttl_seconds: float = 0,
    ) -> None:
        """Initialize the embedding cache.

        Args:
            path: Path to the SQLite database file.
            max_size: Maximum number of entries. Oldest evicted first.
            ttl_seconds: Time-to-live for entries. 0 = no expiry.
        """
        self._path = Path(path).expanduser().resolve()
        self._max_size = max(1, max_size)
        self._ttl = max(0, ttl_seconds)
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the cache table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    cache_key TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    accessed_at REAL NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_accessed
                ON embedding_cache(accessed_at)
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @staticmethod
    def _make_key(text: str, model: str) -> str:
        """Generate a deterministic cache key from text + model."""
        payload = f"{model}::{text}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, text: str, *, model: str = "") -> Optional[list[float]]:
        """Retrieve a cached embedding.

        Args:
            text: The original text that was embedded.
            model: The embedding model name.

        Returns:
            The cached embedding vector, or None if not found / expired.
        """
        key = self._make_key(text, model)
        now = time.time()

        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT embedding, created_at FROM embedding_cache WHERE cache_key = ?",
                    (key,),
                ).fetchone()

                if row is None:
                    self._misses += 1
                    return None

                # Check TTL
                if self._ttl > 0 and (now - row[1]) > self._ttl:
                    conn.execute(
                        "DELETE FROM embedding_cache WHERE cache_key = ?", (key,)
                    )
                    conn.commit()
                    self._misses += 1
                    return None

                # Update access metadata (LRU tracking)
                conn.execute(
                    """UPDATE embedding_cache
                       SET accessed_at = ?, access_count = access_count + 1
                       WHERE cache_key = ?""",
                    (now, key),
                )
                conn.commit()
                self._hits += 1
                return json.loads(row[0])

    def put(
        self,
        text: str,
        embedding: list[float],
        *,
        model: str = "",
    ) -> None:
        """Store an embedding in the cache.

        Args:
            text: The original text.
            embedding: The embedding vector.
            model: The embedding model name.
        """
        key = self._make_key(text, model)
        now = time.time()
        blob = json.dumps(embedding)

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO embedding_cache
                       (cache_key, embedding, model, created_at, accessed_at, access_count)
                       VALUES (?, ?, ?, ?, ?, 1)
                       ON CONFLICT(cache_key) DO UPDATE SET
                         embedding = excluded.embedding,
                         accessed_at = excluded.accessed_at,
                         access_count = access_count + 1""",
                    (key, blob, model, now, now),
                )
                conn.commit()

            # Evict if over max_size
            self._evict_if_needed()

    def invalidate(self, text: str, *, model: str = "") -> bool:
        """Remove a specific entry from the cache.

        Returns:
            True if an entry was removed, False otherwise.
        """
        key = self._make_key(text, model)
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM embedding_cache WHERE cache_key = ?", (key,)
                )
                conn.commit()
                return cursor.rowcount > 0

    def clear(self) -> int:
        """Clear all entries from the cache.

        Returns:
            Number of entries removed.
        """
        with self._lock:
            with self._connect() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM embedding_cache"
                ).fetchone()[0]
                conn.execute("DELETE FROM embedding_cache")
                conn.commit()
                return count

    def stats(self) -> CacheStats:
        """Get cache performance statistics."""
        with self._lock:
            with self._connect() as conn:
                size = conn.execute(
                    "SELECT COUNT(*) FROM embedding_cache"
                ).fetchone()[0]

        total = self._hits + self._misses
        hit_rate = (self._hits / total) if total > 0 else 0.0

        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            evictions=self._evictions,
            size=size,
            max_size=self._max_size,
            hit_rate=hit_rate,
        )

    def _evict_if_needed(self) -> None:
        """Evict oldest-accessed entries if over max_size."""
        with self._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM embedding_cache"
            ).fetchone()[0]

            if count <= self._max_size:
                return

            excess = count - self._max_size
            conn.execute(
                """DELETE FROM embedding_cache
                   WHERE cache_key IN (
                       SELECT cache_key FROM embedding_cache
                       ORDER BY accessed_at ASC
                       LIMIT ?
                   )""",
                (excess,),
            )
            conn.commit()
            self._evictions += excess

    def __len__(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM embedding_cache"
            ).fetchone()[0]

    def __contains__(self, text: str) -> bool:
        return self.get(text) is not None
