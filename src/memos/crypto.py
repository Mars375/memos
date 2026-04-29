"""Encryption at rest for MemOS memories.

Uses Fernet from the cryptography library for authenticated encryption.
Keys are derived from a passphrase via PBKDF2-HMAC-SHA256.

Usage:
    from memos.crypto import MemoryCrypto

    crypto = MemoryCrypto.from_passphrase("my-secret-key")
    encrypted = crypto.encrypt("sensitive data")
    decrypted = crypto.decrypt(encrypted)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from cryptography.fernet import Fernet, InvalidToken

_FERNET_PREFIX = "memos:v2:"
_PBKDF2_ITERATIONS = 1_200_000
_LEGACY_PBKDF2_ITERATIONS = 600_000


def _derive_key(passphrase: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a 32-byte key from passphrase using PBKDF2."""
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, _PBKDF2_ITERATIONS)
    return key, salt


def _derive_legacy_key(passphrase: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive the pre-v2 key used by legacy ciphertexts."""
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, _LEGACY_PBKDF2_ITERATIONS)
    return key, salt


def _fernet_from_key(key: bytes) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(key))


class MemoryCrypto:
    """Symmetric encryption for memory content at rest.

    New writes use Fernet authenticated encryption. Legacy ciphertexts from
    the previous XOR/SHA-256 implementation remain decryptable so existing
    encrypted stores can be read and rewritten safely.
    """

    def __init__(
        self, key: bytes, salt: bytes, *, passphrase: str | None = None, legacy_key: bytes | None = None
    ) -> None:
        self._key = key
        self._salt = salt
        self._passphrase = passphrase
        self._legacy_key = legacy_key or key

    @classmethod
    def from_passphrase(cls, passphrase: str, *, salt_hex: str | None = None) -> "MemoryCrypto":
        """Create a crypto instance from a passphrase.

        Args:
            passphrase: Human-readable secret.
            salt_hex: Optional hex-encoded salt (for deterministic key derivation).
        """
        salt = bytes.fromhex(salt_hex) if salt_hex else None
        key, salt = _derive_key(passphrase, salt)
        legacy_key, _ = _derive_legacy_key(passphrase, salt)
        return cls(key, salt, passphrase=passphrase, legacy_key=legacy_key)

    @property
    def salt_hex(self) -> str:
        return self._salt.hex()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string, return a versioned encoded ciphertext."""
        if not plaintext:
            return ""
        token = _fernet_from_key(self._key).encrypt(plaintext.encode("utf-8")).decode("ascii")
        envelope = {
            "v": 2,
            "alg": "fernet",
            "kdf": "pbkdf2-sha256",
            "iterations": _PBKDF2_ITERATIONS,
            "salt": self._salt.hex(),
            "token": token,
        }
        payload = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        return _FERNET_PREFIX + base64.urlsafe_b64encode(payload).decode("ascii")

    def decrypt(self, encoded: str) -> str:
        """Decrypt base64-encoded ciphertext back to plaintext."""
        if not encoded:
            return ""
        if encoded.startswith(_FERNET_PREFIX):
            return self._decrypt_v2(encoded)
        return self._decrypt_legacy(encoded)

    def _decrypt_v2(self, encoded: str) -> str:
        payload = encoded[len(_FERNET_PREFIX) :]
        try:
            envelope = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
            salt = bytes.fromhex(envelope["salt"])
            token = envelope["token"].encode("ascii")
            if envelope.get("v") != 2 or envelope.get("alg") != "fernet":
                raise ValueError
            key = self._key
            if salt != self._salt:
                if self._passphrase is None:
                    raise ValueError
                key, _ = _derive_key(self._passphrase, salt)
            return _fernet_from_key(key).decrypt(token).decode("utf-8")
        except (InvalidToken, KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Integrity check failed: ciphertext may be corrupted or key is wrong") from exc

    def _decrypt_legacy(self, encoded: str) -> str:
        payload = base64.b64decode(encoded)
        mac = payload[16:32]
        nonce = payload[32:48]
        cipher = payload[48:]
        # Verify HMAC
        expected_mac = hashlib.sha256(self._legacy_key + nonce + cipher).digest()[:16]
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("Integrity check failed: ciphertext may be corrupted or key is wrong")
        # Decrypt
        stream = self._legacy_keystream(nonce, len(cipher))
        data = bytes(a ^ b for a, b in zip(cipher, stream))
        return data.decode("utf-8")

    def _legacy_keystream(self, nonce: bytes, length: int) -> bytes:
        """Generate the pre-v2 deterministic keystream for legacy decrypts."""
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            block_input = self._legacy_key + nonce + counter.to_bytes(8, "big")
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
