"""Encrypted storage wrapper — encrypts memory content at rest."""

from __future__ import annotations

import re
from typing import Optional

from ..crypto import MemoryCrypto, NoOpCrypto
from ..models import MemoryItem
from .base import StorageBackend


class EncryptedStorageBackend(StorageBackend):
    """Wraps any StorageBackend to encrypt content and metadata values at rest.

    Content is encrypted before writing and decrypted after reading.
    Tags, importance, and timestamps are stored in plaintext for querying.
    """

    def __init__(self, inner: StorageBackend, crypto: MemoryCrypto | None = None) -> None:
        self._inner = inner
        self._crypto: MemoryCrypto | NoOpCrypto = crypto or NoOpCrypto()

    def _encrypt_item(self, item: MemoryItem) -> MemoryItem:
        """Return a copy with encrypted content and sensitive metadata."""
        enc_content = self._crypto.encrypt(item.content)

        # Encrypt metadata values that look sensitive
        enc_meta = {}
        sensitive_keys = {"password", "secret", "token", "key", "credential", "api_key"}
        for k, v in item.metadata.items():
            if any(s in k.lower() for s in sensitive_keys) and isinstance(v, str):
                enc_meta[k] = self._crypto.encrypt(v)
            else:
                enc_meta[k] = v
        enc_meta["_encrypted"] = True

        return MemoryItem(
            id=item.id,
            content=enc_content,
            tags=list(item.tags),
            importance=item.importance,
            created_at=item.created_at,
            accessed_at=item.accessed_at,
            access_count=item.access_count,
            relevance_score=item.relevance_score,
            metadata=enc_meta,
            ttl=item.ttl,
        )

    def _decrypt_item(self, item: MemoryItem) -> MemoryItem:
        """Return a copy with decrypted content and sensitive metadata."""
        if not item.metadata.get("_encrypted"):
            return item

        dec_content = self._crypto.decrypt(item.content)

        dec_meta = {}
        sensitive_keys = {"password", "secret", "token", "key", "credential", "api_key"}
        for k, v in item.metadata.items():
            if k == "_encrypted":
                continue
            if any(s in k.lower() for s in sensitive_keys) and isinstance(v, str):
                try:
                    dec_meta[k] = self._crypto.decrypt(v)
                except (ValueError, UnicodeDecodeError):
                    dec_meta[k] = v  # Not encrypted, keep as-is
            else:
                dec_meta[k] = v

        return MemoryItem(
            id=item.id,
            content=dec_content,
            tags=list(item.tags),
            importance=item.importance,
            created_at=item.created_at,
            accessed_at=item.accessed_at,
            access_count=item.access_count,
            relevance_score=item.relevance_score,
            metadata=dec_meta,
            ttl=item.ttl,
        )

    def upsert(self, item: MemoryItem, *, namespace: str = "") -> None:
        self._inner.upsert(self._encrypt_item(item), namespace=namespace)

    def get(self, item_id: str, *, namespace: str = "") -> Optional[MemoryItem]:
        item = self._inner.get(item_id, namespace=namespace)
        if item is None:
            return None
        return self._decrypt_item(item)

    def delete(self, item_id: str, *, namespace: str = "") -> bool:
        return self._inner.delete(item_id, namespace=namespace)

    def list_all(self, *, namespace: str = "") -> list[MemoryItem]:
        return [self._decrypt_item(i) for i in self._inner.list_all(namespace=namespace)]

    def search(self, query: str, limit: int = 20, *, namespace: str = "") -> list[MemoryItem]:
        # Search the decrypted projection so encrypted-at-rest storage remains usable.
        query_lower = query.lower().strip()
        if not query_lower:
            return self.list_all(namespace=namespace)[:limit]

        query_tokens = set(re.findall(r"\w+", query_lower))
        scored: list[tuple[float, MemoryItem]] = []
        for item in self.list_all(namespace=namespace):
            content_lower = item.content.lower()
            content_tokens = set(re.findall(r"\w+", content_lower))
            overlap = query_tokens & content_tokens
            score = float(len(overlap))
            if query_lower in content_lower:
                score += 2.0
            if any(tag.lower() in query_lower or query_lower in tag.lower() for tag in item.tags):
                score += 1.0
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def list_namespaces(self) -> list[str]:
        return self._inner.list_namespaces()
