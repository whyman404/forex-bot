"""Live-trading consent endpoints."""

from __future__ import annotations

from sqlalchemy import desc, select

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.middleware.audit import record_audit
from app.middleware.auth import get_current_user
from app.models.live_consent import LiveConsent
from app.models.user import User
from app.schemas.live import LiveConsentPublic, LiveConsentRequest

router = APIRouter()

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=LiveConsentPublic,
    responses=ERROR_RESPONSES,
    summary="Sign live-trading agreement for a specific strategy",
)
async def create_live_consent(
    payload: LiveConsentRequest,
    request: Request,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LiveConsentPublic:
    ip = request.client.host if request.client else None
    row = LiveConsent(
        user_id=current.id,
        strategy_code=payload.strategy_code,
        version=payload.version,
        risk_acknowledged=payload.risk_acknowledged,
        ip_addr=ip,
    )
    db.add(row)
    await record_audit(
        db,
        action="live_consent.signed",
        actor_user_id=current.id,
        target_type="live_consent",
        payload={
            "strategy_code": payload.strategy_code,
            "version": payload.version,
            "risk_acknowledged": payload.risk_acknowledged,
        },
    )
    await db.commit()
    await db.refresh(row)
    return LiveConsentPublic.model_validate(row)


@router.get(
    "",
    response_model=list[LiveConsentPublic],
    responses=ERROR_RESPONSES,
    summary="List live-trading consents signed by current user",
)
async def list_live_consents(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LiveConsentPublic]:
    result = await db.execute(
        select(LiveConsent)
        .where(LiveConsent.user_id == current.id)
        .order_by(desc(LiveConsent.created_at))
    )
    return [LiveConsentPublic.model_validate(r) for r in result.scalars().all()]
