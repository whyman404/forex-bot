"""Admin endpoints — role-gated. Use sparingly; prefer dedicated admin app long-term."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.errors import ErrorResponse
from app.middleware.auth import require_admin
from app.models.user import User
from app.schemas.common import MessageResponse

router = APIRouter(dependencies=[Depends(require_admin)])

ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
}


@router.get("/ping", response_model=MessageResponse, responses=ERROR_RESPONSES)
async def admin_ping(current: User = Depends(require_admin)) -> MessageResponse:
    return MessageResponse(message=f"pong, {current.email}")
