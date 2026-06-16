"""Notification endpoints — list + mark read."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.notification import NotificationPublic

router = APIRouter()

ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get("", response_model=list[NotificationPublic], responses=ERROR_RESPONSES)
async def list_notifications(
    _user: User = Depends(get_current_user),
    _db: AsyncSession = Depends(get_db),
) -> list[NotificationPublic]:
    # TODO: real implementation in NotificationService
    return []


@router.post(
    "/{notification_id}/read",
    response_model=MessageResponse,
    responses=ERROR_RESPONSES,
)
async def mark_read(
    notification_id: UUID,
    _user: User = Depends(get_current_user),
    _db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    # TODO
    return MessageResponse(message="ok")
