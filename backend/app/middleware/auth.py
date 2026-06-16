"""Auth dependency — extract Bearer JWT, verify, load user.

Use as `Depends(get_current_user)` on protected endpoints.
For admin: `Depends(require_admin)`.
For destructive admin ops: `Depends(require_step_up)` after `require_admin`.

R6 — coordinated with Argus R4 (TOTP step-up). The `X-Step-Up-TOTP` header
carries a 6-digit TOTP code; we verify it against the admin's enrolled secret
and raise TwoFactorRequiredError if missing/invalid.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    AuthTokenInvalidError,
    ForbiddenError,
    TwoFactorRequiredError,
)
from app.core.logging import user_id_ctx
from app.core.security import decode_token, verify_totp
from app.db.session import get_db
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise AuthTokenInvalidError(
            "Missing bearer token", code="AUTH_TOKEN_MISSING", status_code=401
        )

    # Optional Redis-backed denylist (per-jti).
    try:
        payload = decode_token(creds.credentials, expected_type="access")
    except JWTError as exc:
        raise AuthTokenInvalidError(str(exc)) from exc

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthTokenInvalidError("Invalid subject claim") from exc

    # Check denylist if available
    limiter = getattr(request.app.state, "rate_limiter", None)
    jti = payload.get("jti")
    if limiter is not None and jti:
        try:
            if await limiter.redis.exists(f"jwt:revoked:{jti}"):
                raise AuthTokenInvalidError("Token revoked")
        except AuthTokenInvalidError:
            raise
        except Exception:  # noqa: BLE001 — fail open on redis outage
            pass

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthTokenInvalidError("User not found or disabled")

    request.state.user_id = str(user.id)
    user_id_ctx.set(str(user.id))
    return user


async def require_admin(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Admin-gate. Re-loads role from DB (in case token was minted before
    role change) and 403's non-admins. Coordinates with Argus R4 spec.
    """
    # Re-fetch from DB to catch role changes since token issuance.
    fresh = await db.execute(
        select(User).where(User.id == current.id, User.deleted_at.is_(None))
    )
    user = fresh.scalar_one_or_none()
    if user is None or user.role != "admin":
        raise ForbiddenError("Admin role required", code="ADMIN_REQUIRED")
    return user


async def require_step_up(
    request: Request,
    current: User = Depends(require_admin),
    x_step_up_totp: str | None = Header(default=None, alias="X-Step-Up-TOTP"),
) -> User:
    """Step-up TOTP gate for destructive admin actions.

    The admin MUST have TOTP enrolled and present a fresh 6-digit code in
    `X-Step-Up-TOTP`. Argus R4 docs the threat model.
    """
    if current.totp_secret is None:
        raise TwoFactorRequiredError(
            "Admin must enroll TOTP before performing this action",
            code="ADMIN_TOTP_NOT_ENROLLED",
        )
    if not x_step_up_totp:
        raise TwoFactorRequiredError(
            "X-Step-Up-TOTP header required for this action",
            code="ADMIN_STEP_UP_REQUIRED",
        )
    # totp_secret is bytes (LargeBinary) — try utf-8 decode (we store base32).
    try:
        secret = current.totp_secret.decode("ascii") if isinstance(current.totp_secret, (bytes, bytearray)) else current.totp_secret
    except Exception as exc:  # noqa: BLE001
        raise TwoFactorRequiredError("TOTP secret corrupt") from exc
    if not verify_totp(secret, x_step_up_totp):
        raise TwoFactorRequiredError("Invalid TOTP code", code="ADMIN_STEP_UP_INVALID")
    request.state.step_up_verified = True
    return current
