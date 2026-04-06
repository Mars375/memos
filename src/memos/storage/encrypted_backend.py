"""Encrypted storage wrapper — encrypts memory content at rest."""

from __future__ import annotations

from typing import Optional

from ..models import MemoryItem
from .base import StorageBackend
from ..crypto import MemoryCrypto, NoOpCrypto


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
            metadata=enc_meta,
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
                except Exception:
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
            metadata=dec_meta,
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
        # Search works on encrypted content — we decrypt results after
        results = self._inner.search(query, limit=limit, namespace=namespace)
        return [self._decrypt_item(i) for i in results]

    def list_namespaces(self) -> list[str]:
        return self._inner.list_namespaces()
