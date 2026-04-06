"""Tests for encryption at rest."""

import pytest

from memos.crypto import MemoryCrypto, NoOpCrypto
from memos.models import MemoryItem
from memos.storage.memory_backend import InMemoryBackend
from memos.storage.encrypted_backend import EncryptedStorageBackend
from memos import MemOS


class TestMemoryCrypto:
    """Test the core crypto module."""

    def test_encrypt_decrypt_roundtrip(self):
        crypto = MemoryCrypto.from_passphrase("test-secret")
        plaintext = "This is sensitive data"
        encrypted = crypto.encrypt(plaintext)
        assert encrypted != plaintext
        assert crypto.decrypt(encrypted) == plaintext

    def test_encrypt_empty_string(self):
        crypto = MemoryCrypto.from_passphrase("key")
        assert crypto.encrypt("") == ""
        assert crypto.decrypt("") == ""

    def test_different_passphrases_produce_different_ciphertext(self):
        c1 = MemoryCrypto.from_passphrase("secret1")
        c2 = MemoryCrypto.from_passphrase("secret2")
        enc1 = c1.encrypt("same data")
        enc2 = c2.encrypt("same data")
        assert enc1 != enc2

    def test_wrong_key_fails(self):
        c1 = MemoryCrypto.from_passphrase("correct")
        c2 = MemoryCrypto.from_passphrase("wrong")
        encrypted = c1.encrypt("secret stuff")
        with pytest.raises(ValueError, match="Integrity check failed"):
            c2.decrypt(encrypted)

    def test_deterministic_key_derivation(self):
        salt = "ab" * 16  # 16 bytes = 32 hex chars
        c1 = MemoryCrypto.from_passphrase("key", salt_hex=salt)
        c2 = MemoryCrypto.from_passphrase("key", salt_hex=salt)
        assert c1._key == c2._key
        enc = c1.encrypt("data")
        assert c2.decrypt(enc) == "data"

    def test_unicode_content(self):
        crypto = MemoryCrypto.from_passphrase("key")
        text = "Héllo wörld 🌍 日本語テスト"
        assert crypto.decrypt(crypto.encrypt(text)) == text

    def test_long_content(self):
        crypto = MemoryCrypto.from_passphrase("key")
        text = "A" * 10_000
        assert crypto.decrypt(crypto.encrypt(text)) == text

    def test_salt_hex_property(self):
        crypto = MemoryCrypto.from_passphrase("key")
        assert len(crypto.salt_hex) == 32  # 16 bytes = 32 hex chars


class TestNoOpCrypto:
    def test_passthrough(self):
        c = NoOpCrypto()
        assert c.encrypt("hello") == "hello"
        assert c.decrypt("hello") == "hello"
        assert c.salt_hex == ""


class TestEncryptedStorageBackend:
    """Test the encrypted storage wrapper."""

    def _make_item(self, content="test memory", **kw):
        return MemoryItem(
            id="test-id",
            content=content,
            tags=["test"],
            importance=0.5,
            metadata=kw.get("metadata", {}),
        )

    def test_encrypts_content_at_rest(self):
        inner = InMemoryBackend()
        crypto = MemoryCrypto.from_passphrase("pass")
        enc = EncryptedStorageBackend(inner, crypto)
        item = self._make_item("secret content")
        enc.upsert(item)
        # Inner storage should have encrypted content
        raw = inner.get("test-id")
        assert raw is not None
        assert raw.content != "secret content"
        assert raw.metadata.get("_encrypted") is True

    def test_decrypts_on_read(self):
        inner = InMemoryBackend()
        crypto = MemoryCrypto.from_passphrase("pass")
        enc = EncryptedStorageBackend(inner, crypto)
        item = self._make_item("secret content")
        enc.upsert(item)
        result = enc.get("test-id")
        assert result.content == "secret content"

    def test_encrypts_sensitive_metadata(self):
        inner = InMemoryBackend()
        crypto = MemoryCrypto.from_passphrase("pass")
        enc = EncryptedStorageBackend(inner, crypto)
        item = self._make_item(metadata={"api_key": "sk-12345", "name": "public"})
        enc.upsert(item)
        raw = inner.get("test-id")
        assert raw.metadata["api_key"] != "sk-12345"
        assert raw.metadata["name"] == "public"
        # Decrypt
        result = enc.get("test-id")
        assert result.metadata["api_key"] == "sk-12345"
        assert result.metadata["name"] == "public"

    def test_list_all_decrypts(self):
        inner = InMemoryBackend()
        crypto = MemoryCrypto.from_passphrase("pass")
        enc = EncryptedStorageBackend(inner, crypto)
        enc.upsert(self._make_item("hello", metadata={"id": "a"}))
        enc.upsert(MemoryItem(id="b", content="world", metadata={}))
        items = enc.list_all()
        assert len(items) == 2
        contents = {i.content for i in items}
        assert contents == {"hello", "world"}

    def test_delete_works(self):
        inner = InMemoryBackend()
        crypto = MemoryCrypto.from_passphrase("pass")
        enc = EncryptedStorageBackend(inner, crypto)
        enc.upsert(self._make_item())
        assert enc.delete("test-id") is True
        assert enc.get("test-id") is None

    def test_no_crypto_passthrough(self):
        inner = InMemoryBackend()
        enc = EncryptedStorageBackend(inner)
        item = self._make_item("plain")
        enc.upsert(item)
        result = enc.get("test-id")
        assert result.content == "plain"
        raw = inner.get("test-id")
        assert raw.content == "plain"

    def test_namespaced_operations(self):
        inner = InMemoryBackend()
        crypto = MemoryCrypto.from_passphrase("pass")
        enc = EncryptedStorageBackend(inner, crypto)
        enc.upsert(self._make_item("ns-content"), namespace="agent1")
        result = enc.get("test-id", namespace="agent1")
        assert result.content == "ns-content"
        assert enc.get("test-id", namespace="agent2") is None


class TestMemOSWithEncryption:
    """Integration: MemOS with encryption_key."""

    def test_encrypted_learn_and_recall(self):
        mem = MemOS(backend="memory", encryption_key="my-secret")
        mem.learn("User secret token is tok-abc123", tags=["credential"])
        # Raw storage should be encrypted
        raw_items = mem._store._inner.list_all()
        assert all(i.metadata.get("_encrypted") for i in raw_items)
        # Recall should decrypt
        results = mem.recall("secret token")
        assert any("tok-abc123" in r.item.content for r in results)

    def test_without_encryption_works_as_before(self):
        mem = MemOS(backend="memory")
        mem.learn("normal memory")
        results = mem.recall("normal")
        assert len(results) > 0
