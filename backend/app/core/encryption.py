"""Envelope encryption for broker credentials (ADR-005).

Design (envelope pattern):
  - KEK (Key Encryption Key) — 256-bit, stored in KMS / secret manager.
    Loaded once at startup from `Settings.encryption_kek_base64`.
  - DEK (Data Encryption Key) — 256-bit, freshly generated *per record*.
    Encrypted by KEK using AES-256-GCM, stored next to the ciphertext.
  - Payload — encrypted by DEK using AES-256-GCM.

DB columns (Mnemosyne owns schema, this is the contract):
  ciphertext      BYTEA  — AES-GCM(DEK, payload, nonce_payload, aad=AAD)
  nonce_payload   BYTEA  — 12 bytes
  encrypted_dek   BYTEA  — AES-GCM(KEK, DEK, nonce_dek)
  nonce_dek       BYTEA  — 12 bytes
  key_version     INT    — KEK version for rotation

Atlas Goro — keep this module *boring* and easy to audit.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Self

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_NONCE_LEN = 12  # 96 bits — NIST recommended for AES-GCM
_DEK_LEN = 32  # 256 bits


@dataclass(frozen=True, slots=True)
class EncryptedBlob:
    """Self-contained encrypted payload. Map 1:1 to DB columns."""

    ciphertext: bytes
    nonce_payload: bytes
    encrypted_dek: bytes
    nonce_dek: bytes
    key_version: int

    def to_dict(self) -> dict[str, bytes | int]:
        return {
            "ciphertext": self.ciphertext,
            "nonce_payload": self.nonce_payload,
            "encrypted_dek": self.encrypted_dek,
            "nonce_dek": self.nonce_dek,
            "key_version": self.key_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, bytes | int]) -> Self:
        return cls(
            ciphertext=d["ciphertext"],  # type: ignore[arg-type]
            nonce_payload=d["nonce_payload"],  # type: ignore[arg-type]
            encrypted_dek=d["encrypted_dek"],  # type: ignore[arg-type]
            nonce_dek=d["nonce_dek"],  # type: ignore[arg-type]
            key_version=d["key_version"],  # type: ignore[arg-type]
        )


def _load_kek() -> bytes:
    settings = get_settings()
    raw = base64.b64decode(settings.encryption_kek_base64)
    if len(raw) != 32:
        raise ValueError("KEK must be exactly 32 bytes (256-bit) after base64 decode")
    return raw


def encrypt(plaintext: bytes, *, aad: bytes = b"") -> EncryptedBlob:
    """Envelope-encrypt plaintext.

    Args:
        plaintext: secret bytes (e.g. broker login JSON)
        aad: additional authenticated data — bind ciphertext to a context
             (e.g. b"user_id:42|broker:exness"). NOT secret; tamper-evident.
    """
    if not isinstance(plaintext, bytes):
        raise TypeError("plaintext must be bytes")

    settings = get_settings()
    kek = _load_kek()

    # 1. Fresh DEK
    dek = os.urandom(_DEK_LEN)

    # 2. Encrypt payload with DEK
    nonce_payload = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(dek).encrypt(nonce_payload, plaintext, aad or None)

    # 3. Wrap DEK with KEK
    nonce_dek = os.urandom(_NONCE_LEN)
    encrypted_dek = AESGCM(kek).encrypt(nonce_dek, dek, None)

    return EncryptedBlob(
        ciphertext=ciphertext,
        nonce_payload=nonce_payload,
        encrypted_dek=encrypted_dek,
        nonce_dek=nonce_dek,
        key_version=settings.encryption_key_version,
    )


def decrypt(blob: EncryptedBlob, *, aad: bytes = b"") -> bytes:
    """Inverse of `encrypt`. Raises `cryptography.exceptions.InvalidTag` on tamper."""
    # For now we keep one KEK version. Multi-version rotation: lookup keyring[blob.key_version].
    kek = _load_kek()

    dek = AESGCM(kek).decrypt(blob.nonce_dek, blob.encrypted_dek, None)
    try:
        return AESGCM(dek).decrypt(blob.nonce_payload, blob.ciphertext, aad or None)
    finally:
        # Best-effort zeroize. Python doesn't guarantee, but reduces residency.
        dek = b"\x00" * len(dek)  # noqa: F841


def encrypt_str(plaintext: str, *, aad: bytes = b"") -> EncryptedBlob:
    return encrypt(plaintext.encode("utf-8"), aad=aad)


def decrypt_to_str(blob: EncryptedBlob, *, aad: bytes = b"") -> str:
    return decrypt(blob, aad=aad).decode("utf-8")
