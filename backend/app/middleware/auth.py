"""Auth dependency — extract Bearer JWT, verify, load user.

Use as `Depends(get_current_user)` on protected endpoints.
For admin: `Depends(require_admin)`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthTokenInvalidError, ForbiddenError
from app.core.logging import user_id_ctx
from app.core.security import decode_token
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


async def require_admin(current: User = Depends(get_current_user)) -> User:
    if current.role != "admin":
        raise ForbiddenError("Admin role required")
    return current
