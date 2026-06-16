"""Auth endpoints — signup, login, refresh, logout, MFA, password reset."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import rate_limit
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenPair,
    TotpEnrollResponse,
    TotpVerifyRequest,
    VerifyEmailRequest,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService

router = APIRouter()

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


def _redis(request: Request):  # type: ignore[no-untyped-def]
    """Return the redis client if wired by lifespan, else None."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    return limiter.redis if limiter is not None else None


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenPair,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit(scope="auth-signup", per_min=10))],
)
async def signup(
    payload: SignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    return await AuthService(db, redis=_redis(request)).signup(payload)


@router.post(
    "/login",
    response_model=TokenPair,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit(scope="auth-login", per_min=10))],
)
async def login(
    payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenPair:
    ip = request.client.host if request.client else None
    return await AuthService(db, redis=_redis(request)).login(payload, ip=ip)


@router.post("/refresh", response_model=TokenPair, responses=ERROR_RESPONSES)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    return await AuthService(db, redis=_redis(request)).refresh(payload.refresh_token)


@router.post("/logout", response_model=MessageResponse, responses=ERROR_RESPONSES)
async def logout(
    payload: LogoutRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MessageResponse:
    await AuthService(db, redis=_redis(request)).logout(payload.refresh_token)
    return MessageResponse(message="logged out")


@router.post("/verify-email", response_model=MessageResponse, responses=ERROR_RESPONSES)
async def verify_email(
    payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    await AuthService(db).verify_email(payload.token)
    return MessageResponse(message="email verified")


@router.get("/verify-email", response_model=MessageResponse, responses=ERROR_RESPONSES)
async def verify_email_get(
    token: str = Query(min_length=8, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """GET variant — used by email links so users click once and confirm."""
    await AuthService(db).verify_email(token)
    return MessageResponse(message="email verified")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit(scope="auth-reset", per_min=3))],
)
async def forgot_password(
    payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    await AuthService(db).request_password_reset(payload.email)
    return MessageResponse(message="if the email exists, a reset link was sent")


@router.post("/reset-password", response_model=MessageResponse, responses=ERROR_RESPONSES)
async def reset_password(
    payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    await AuthService(db).reset_password(payload.token, payload.new_password)
    return MessageResponse(message="password reset")


@router.post(
    "/totp/enroll", response_model=TotpEnrollResponse, responses=ERROR_RESPONSES
)
async def totp_enroll(
    current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> TotpEnrollResponse:
    secret, uri = await AuthService(db).enroll_totp(str(current.id))
    return TotpEnrollResponse(secret=secret, provisioning_uri=uri)


@router.post("/totp/verify", response_model=MessageResponse, responses=ERROR_RESPONSES)
async def totp_verify(
    payload: TotpVerifyRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await AuthService(db).verify_totp(str(current.id), payload.code)
    return MessageResponse(message="totp enabled")
