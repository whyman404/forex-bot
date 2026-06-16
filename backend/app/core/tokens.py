"""Opaque one-shot tokens — email verification & password reset.

Atlas Goro — we generate cryptographically random tokens client-side and store
only their SHA-256 hash on the server. Stolen DB rows cannot replay the link.
"""

from __future__ import annotations

import hashlib
import secrets


def generate_opaque_token(nbytes: int = 32) -> str:
    """URL-safe random token. Default 32 bytes → 43 chars base64."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()
