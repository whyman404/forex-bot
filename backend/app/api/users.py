"""User endpoints — profile + account deletion."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserPublic, UserUpdateRequest

router = APIRouter()

ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get("/me", response_model=UserPublic, responses=ERROR_RESPONSES)
async def get_me(current: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current)


@router.patch("/me", response_model=UserPublic, responses=ERROR_RESPONSES)
async def update_me(
    payload: UserUpdateRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    if payload.full_name is not None:
        current.full_name = payload.full_name
    await db.commit()
    await db.refresh(current)
    return UserPublic.model_validate(current)


# NOTE: DELETE /users/me is owned by the compliance router (cancels Stripe sub
# first then soft-deletes + enqueues 30-day hard purge). See app/api/compliance.py.
