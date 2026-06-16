"""Compliance endpoints — GDPR / PDPA data export, consents, deletion.

Atlas Goro — sensitive ops here. Account deletion *cancels Stripe sub first*
(if any) then soft-deletes. Hard-purge is queued via Redis for a 30-day
grace window worker (TODO: dedicated purge_worker).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from sqlalchemy import desc, select

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ErrorResponse
from app.core.logging import get_logger
from app.db.session import get_db
from app.middleware.audit import record_audit
from app.middleware.auth import get_current_user
from app.models.subscription import Subscription
from app.models.user import User
from app.models.user_consent import UserConsent
from app.schemas.common import MessageResponse
from app.schemas.consent import ConsentPublic, ConsentRequest

logger = get_logger(__name__)

router = APIRouter()

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.post(
    "/me/consent",
    status_code=status.HTTP_201_CREATED,
    response_model=ConsentPublic,
    responses=ERROR_RESPONSES,
    summary="Record a consent decision (TOS / privacy / marketing / data_processing)",
)
async def record_consent(
    payload: ConsentRequest,
    request: Request,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConsentPublic:
    ip = request.client.host if request.client else None
    row = UserConsent(
        user_id=current.id,
        kind=payload.kind,
        version=payload.version,
        accepted=payload.accepted,
        ip_addr=ip,
    )
    db.add(row)
    await record_audit(
        db,
        action="user_consent.recorded",
        actor_user_id=current.id,
        target_type="user_consent",
        payload={
            "kind": payload.kind,
            "version": payload.version,
            "accepted": payload.accepted,
        },
    )
    await db.commit()
    await db.refresh(row)
    return ConsentPublic.model_validate(row)


@router.get(
    "/me/consent",
    response_model=list[ConsentPublic],
    responses=ERROR_RESPONSES,
    summary="List consents signed by current user",
)
async def list_consents(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConsentPublic]:
    result = await db.execute(
        select(UserConsent)
        .where(UserConsent.user_id == current.id)
        .order_by(desc(UserConsent.created_at))
    )
    return [ConsentPublic.model_validate(r) for r in result.scalars().all()]


@router.get(
    "/me/export",
    response_model=MessageResponse,
    responses=ERROR_RESPONSES,
    summary="Queue an async data export — email link when ready",
)
async def request_export(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Queue a job; worker compiles JSON archive and emails a signed link."""
    settings = get_settings()
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.lpush(
            "gdpr_export_queue",
            json.dumps({"user_id": str(current.id), "queued_at": datetime.now(UTC).isoformat()}),
        )
        await redis.aclose()
    except Exception as exc:  # noqa: BLE001
        logger.warning("gdpr_export_queue_failed", err=str(exc))

    await record_audit(
        db,
        action="gdpr.export.requested",
        actor_user_id=current.id,
        target_type="user",
        target_id=current.id,
    )
    await db.commit()
    return MessageResponse(
        message="Export queued. You will receive an email when ready."
    )


@router.delete(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=MessageResponse,
    responses=ERROR_RESPONSES,
    summary="Delete account — soft delete + 30-day hard purge",
)
async def delete_account(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Cancel Stripe sub (best-effort) → soft delete → enqueue hard purge."""
    settings = get_settings()
    # 1) Cancel active subscriptions in Stripe
    try:
        from app.services.billing_service import StripeAdapter

        adapter = StripeAdapter(settings.stripe_api_key)
        result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == current.id,
                Subscription.status.in_(("active", "trialing", "past_due")),
                Subscription.stripe_subscription_id.isnot(None),
            )
        )
        for sub in result.scalars().all():
            if not adapter.offline and sub.stripe_subscription_id:
                try:
                    adapter.sdk.Subscription.delete(sub.stripe_subscription_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "stripe_subscription_cancel_failed",
                        sub_id=str(sub.id),
                        err=str(exc),
                    )
            sub.status = "canceled"
            sub.canceled_at = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001
        logger.warning("delete_account_stripe_skip", err=str(exc))

    # 2) Soft delete
    current.deleted_at = datetime.now(UTC)

    # 3) Enqueue hard-purge worker (TODO worker side)
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.lpush(
            "gdpr_purge_queue",
            json.dumps(
                {
                    "user_id": str(current.id),
                    "purge_after": (datetime.now(UTC).timestamp() + 30 * 86400),
                }
            ),
        )
        await redis.aclose()
    except Exception as exc:  # noqa: BLE001
        logger.warning("gdpr_purge_queue_failed", err=str(exc))

    await record_audit(
        db,
        action="gdpr.account.deleted",
        actor_user_id=current.id,
        target_type="user",
        target_id=current.id,
    )
    await db.commit()
    return MessageResponse(
        message="Account scheduled for deletion. Hard purge in 30 days."
    )
