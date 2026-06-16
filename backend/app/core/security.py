"""Security primitives: password hashing, JWT, TOTP.

Atlas Goro — these are *primitives*. Auth flow lives in `app/services/auth_service.py`.

References:
- Argon2id parameters: OWASP Password Storage Cheat Sheet (2024)
- JWT best practices: RFC 8725
- TOTP: RFC 6238, default 30s period, 6 digits
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import pyotp
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# ---- Password hashing ---------------------------------------------------------

# Argon2id is the OWASP recommendation. Tune time_cost via load test in staging.
_pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__time_cost=3,
    argon2__memory_cost=65536,  # 64 MiB
    argon2__parallelism=4,
)


def hash_password(plain: str) -> str:
    """Return Argon2id hash of plaintext password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verify of password against stored hash."""
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:  # noqa: BLE001 — corrupted hash should not crash login
        return False


def needs_rehash(hashed: str) -> bool:
    """True if stored hash uses outdated parameters and should be re-hashed on next login."""
    return _pwd_context.needs_update(hashed)


# ---- JWT --------------------------------------------------------------------

TokenType = Literal["access", "refresh"]


def create_token(
    subject: str,
    token_type: TokenType,
    *,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, datetime, str]:
    """Mint a JWT.

    Returns:
        (token, expires_at, jti) — jti is the unique token id (for revocation list).
    """
    settings = get_settings()
    now = datetime.now(UTC)
    jti = str(uuid4())

    if token_type == "access":
        expires = now + timedelta(minutes=settings.jwt_access_token_ttl_min)
    else:
        expires = now + timedelta(days=settings.jwt_refresh_token_ttl_days)

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": jti,
        "typ": token_type,
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires, jti


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode + verify JWT.

    Raises JWTError on invalid signature, expiry, audience, or type mismatch.
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    if expected_type and payload.get("typ") != expected_type:
        raise JWTError(f"expected token type {expected_type!r}, got {payload.get('typ')!r}")
    return payload


# ---- TOTP -------------------------------------------------------------------


def generate_totp_secret() -> str:
    """Generate a new TOTP shared secret (base32)."""
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, account_name: str) -> str:
    """otpauth:// URI for QR-code enrollment."""
    settings = get_settings()
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_name,
        issuer_name=settings.totp_issuer,
    )


def verify_totp(secret: str, code: str, *, valid_window: int = 1) -> bool:
    """Verify a 6-digit TOTP code. `valid_window=1` allows ±30s clock skew."""
    if not code or not code.isdigit() or len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=valid_window)


# ---- Misc -------------------------------------------------------------------


def generate_secure_token(nbytes: int = 32) -> str:
    """URL-safe random token — for email verify, password reset, etc."""
    return secrets.token_urlsafe(nbytes)
