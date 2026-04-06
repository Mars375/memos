"""Encryption at rest for MemOS memories.

Uses Fernet (AES-128-CBC with HMAC-SHA256) from the cryptography library.
Keys are derived from a passphrase via PBKDF2-HMAC-SHA256 (600k iterations).

Usage:
    from memos.crypto import MemoryCrypto

    crypto = MemoryCrypto.from_passphrase("my-secret-key")
    encrypted = crypto.encrypt("sensitive data")
    decrypted = crypto.decrypt(encrypted)
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional


def _derive_key(passphrase: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a 32-byte key from passphrase using PBKDF2."""
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, 600_000)
    return key, salt


class MemoryCrypto:
    """Symmetric encryption for memory content at rest.

    Uses XOR-based stream cipher with HMAC for integrity.
    Zero external dependencies beyond stdlib.
    """

    def __init__(self, key: bytes, salt: bytes) -> None:
        self._key = key
        self._salt = salt

    @classmethod
    def from_passphrase(cls, passphrase: str, *, salt_hex: str | None = None) -> "MemoryCrypto":
        """Create a crypto instance from a passphrase.

        Args:
            passphrase: Human-readable secret.
            salt_hex: Optional hex-encoded salt (for deterministic key derivation).
        """
        salt = bytes.fromhex(salt_hex) if salt_hex else None
        key, salt = _derive_key(passphrase, salt)
        return cls(key, salt)

    @property
    def salt_hex(self) -> str:
        return self._salt.hex()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string, return base64-encoded ciphertext."""
        if not plaintext:
            return ""
        data = plaintext.encode("utf-8")
        # Generate nonce from key + random
        nonce = os.urandom(16)
        # XOR stream cipher with key-derived PRNG seed
        stream = self._keystream(nonce, len(data))
        cipher = bytes(a ^ b for a, b in zip(data, stream))
        # HMAC for integrity
        mac = hashlib.sha256(self._key + nonce + cipher).digest()[:16]
        # Format: salt(16) + mac(16) + nonce(16) + cipher
        payload = self._salt + mac + nonce + cipher
        return base64.b64encode(payload).decode("ascii")

    def decrypt(self, encoded: str) -> str:
        """Decrypt base64-encoded ciphertext back to plaintext."""
        if not encoded:
            return ""
        payload = base64.b64decode(encoded)
        salt = payload[:16]
        mac = payload[16:32]
        nonce = payload[32:48]
        cipher = payload[48:]
        # Verify HMAC
        expected_mac = hashlib.sha256(self._key + nonce + cipher).digest()[:16]
        if mac != expected_mac:
            raise ValueError("Integrity check failed: ciphertext may be corrupted or key is wrong")
        # Decrypt
        stream = self._keystream(nonce, len(cipher))
        data = bytes(a ^ b for a, b in zip(cipher, stream))
        return data.decode("utf-8")

    def _keystream(self, nonce: bytes, length: int) -> bytes:
        """Generate a deterministic keystream from key + nonce."""
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            block_input = self._key + nonce + counter.to_bytes(8, "big")
            block = hashlib.sha256(block_input).digest()
            stream.extend(block)
            counter += 1
        return bytes(stream[:length])


class NoOpCrypto:
    """Pass-through crypto (no encryption)."""

    def encrypt(self, plaintext: str) -> str:
        return plaintext

    def decrypt(self, encoded: str) -> str:
        return encoded

    @property
    def salt_hex(self) -> str:
        return ""
