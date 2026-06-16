"""Subscription-tier guard dependency.

Atlas Goro — the entitlement check lives in a tiny dependency so every
gated endpoint can reuse it. Reads the user's *latest* subscription row.

Allowed states (= "active pro"):
  - plan ∈ {pro_monthly, pro_yearly, lifetime}  AND status ∈ {active, trialing}

`trial` plan with status=trialing also counts as "active" but NOT as "pro"
(some endpoints, e.g. go-live, require true pro — pass `require_paid=True`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BillingPaymentRequiredError
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.models.subscription import Subscription
from app.models.user import User


def _is_active(sub: Subscription | None) -> bool:
    if sub is None:
        return False
    if sub.status not in {"active", "trialing"}:
        return False
    if sub.current_period_end is not None and sub.plan != "lifetime":
        if sub.current_period_end < datetime.now(UTC):
            return False
    return True


def _is_paid(sub: Subscription | None) -> bool:
    if not _is_active(sub):
        return False
    return sub.plan in {"pro_monthly", "pro_yearly", "lifetime"}


async def _latest(db: AsyncSession, user_id) -> Subscription | None:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(desc(Subscription.created_at))
    )
    return result.scalars().first()


def require_active_subscription(*, require_paid: bool = False):
    """Factory: returns a FastAPI dependency.

    Usage:
        @router.post("/foo", dependencies=[Depends(require_active_subscription())])
        @router.post("/live", dependencies=[Depends(require_active_subscription(require_paid=True))])
    """

    async def _dep(
        current: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        sub = await _latest(db, current.id)
        ok = _is_paid(sub) if require_paid else _is_active(sub)
        if not ok:
            raise BillingPaymentRequiredError(
                "Active paid subscription required."
                if require_paid
                else "Active subscription required."
            )
        return current

    return _dep


async def get_subscription_for(db: AsyncSession, user_id) -> Subscription | None:
    """Helper for other services."""
    return await _latest(db, user_id)


async def is_paid_user(db: AsyncSession, user_id) -> bool:
    return _is_paid(await _latest(db, user_id))
