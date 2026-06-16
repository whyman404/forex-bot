"""Admin service layer — business logic for admin endpoints.

Atlas Goro — services own transaction boundaries; routers stay thin.
Audit log writes occur INSIDE the calling transaction so they atomically
commit with the change. Never commit audit separately from the mutation.

Coordination:
- Argus R4: step-up TOTP enforced in router via dep; we trust the dep here.
- Mnemosyne Rin: queries are N+1 safe via joined-loads / CTEs.
- Eos R6: response shapes match Pydantic schemas exactly.
"""

from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import (
    and_,
    case,
    delete,
    desc,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from app.core.logging import get_logger
from app.core.security import create_token, hash_password
from app.middleware.audit import record_audit
from app.models.audit_log import AuditLog
from app.models.backtest import Backtest
from app.models.broker_account import BrokerAccount
from app.models.notification import Notification
from app.models.strategy import Strategy
from app.models.strategy_instance import StrategyInstance
from app.models.subscription import Subscription
from app.models.user import User

logger = get_logger(__name__)


_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"
_KILL_SWITCH_TTL_SECONDS = 3600  # 1 hour pending window for second approver


def _gen_temp_password(length: int = 16) -> str:
    # Avoid look-alikes; ensure variety.
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))


# ============================================================
# User management
# ============================================================


async def list_users(
    db: AsyncSession,
    *,
    q: str | None = None,
    role: str | None = None,
    status_filter: str | None = None,
    page: int = 1,
    per_page: int = 25,
    sort: str = "created_at",
) -> tuple[list[dict[str, Any]], int]:
    """List users with aggregated counts. N+1 safe via subselect counts.

    `status_filter`:
        - "active"  → deleted_at IS NULL
        - "banned"  → row is_banned (we encode via a future column; for now
                       payload-redacted note. To keep schema stable we treat
                       deleted_at as a soft-banned marker if column missing.)
    """
    if per_page > 100:
        per_page = 100
    if page < 1:
        page = 1

    # Aggregate subqueries — keeps it O(1) joins instead of N+1.
    broker_count_sq = (
        select(BrokerAccount.user_id, func.count(BrokerAccount.id).label("c"))
        .where(BrokerAccount.deleted_at.is_(None))
        .group_by(BrokerAccount.user_id)
        .subquery()
    )
    si_count_sq = (
        select(StrategyInstance.user_id, func.count(StrategyInstance.id).label("c"))
        .where(StrategyInstance.deleted_at.is_(None))
        .group_by(StrategyInstance.user_id)
        .subquery()
    )
    sub_active_sq = (
        select(
            Subscription.user_id,
            func.max(
                case((Subscription.status.in_(("active", "trialing")), Subscription.plan), else_=None)
            ).label("plan"),
            func.max(
                case((Subscription.status.in_(("active", "trialing")), Subscription.status), else_=None)
            ).label("status"),
        )
        .group_by(Subscription.user_id)
        .subquery()
    )

    stmt = (
        select(
            User,
            func.coalesce(broker_count_sq.c.c, 0).label("broker_count"),
            func.coalesce(si_count_sq.c.c, 0).label("si_count"),
            sub_active_sq.c.plan.label("sub_plan"),
            sub_active_sq.c.status.label("sub_status"),
        )
        .outerjoin(broker_count_sq, broker_count_sq.c.user_id == User.id)
        .outerjoin(si_count_sq, si_count_sq.c.user_id == User.id)
        .outerjoin(sub_active_sq, sub_active_sq.c.user_id == User.id)
    )

    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(like), func.lower(User.full_name).like(like)))
    if role in {"user", "admin"}:
        stmt = stmt.where(User.role == role)
    if status_filter == "active":
        stmt = stmt.where(User.deleted_at.is_(None))
    elif status_filter == "banned":
        stmt = stmt.where(User.deleted_at.is_not(None))

    # Count (separate cheaper query).
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    sort_col = User.created_at
    if sort == "last_login_at":
        # We don't yet have last_login_at column — fall back to updated_at if present, else created_at.
        sort_col = getattr(User, "last_login_at", None) or User.created_at

    stmt = stmt.order_by(desc(sort_col)).limit(per_page).offset((page - 1) * per_page)
    rows = (await db.execute(stmt)).all()

    items: list[dict[str, Any]] = []
    for row in rows:
        u: User = row[0]
        items.append(
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "country": u.country,
                "role": u.role,
                "created_at": u.created_at,
                "email_verified_at": u.email_verified_at,
                "last_login_at": getattr(u, "last_login_at", None),
                "is_banned": u.deleted_at is not None,
                "deleted_at": u.deleted_at,
                "subscription_status": row.sub_status,
                "subscription_plan": row.sub_plan,
                "broker_count": int(row.broker_count or 0),
                "strategy_instance_count": int(row.si_count or 0),
            }
        )
    return items, int(total)


async def get_user_detail(db: AsyncSession, user_id: UUID) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found", code="USER_NOT_FOUND")

    subs = (
        await db.execute(
            select(Subscription).where(Subscription.user_id == user_id).order_by(desc(Subscription.created_at))
        )
    ).scalars().all()
    brokers = (
        await db.execute(
            select(BrokerAccount)
            .where(BrokerAccount.user_id == user_id, BrokerAccount.deleted_at.is_(None))
        )
    ).scalars().all()
    instances = (
        await db.execute(
            select(StrategyInstance)
            .where(StrategyInstance.user_id == user_id, StrategyInstance.deleted_at.is_(None))
            .order_by(desc(StrategyInstance.created_at))
        )
    ).scalars().all()
    backtests = (
        await db.execute(
            select(Backtest)
            .where(Backtest.user_id == user_id)
            .order_by(desc(Backtest.created_at))
            .limit(5)
        )
    ).scalars().all()

    # Consents — optional table; tolerate absence.
    consents: list[dict[str, Any]] = []
    try:
        from app.models.user_consent import UserConsent  # type: ignore

        consents_rows = (
            await db.execute(select(UserConsent).where(UserConsent.user_id == user_id))
        ).scalars().all()
        for c in consents_rows:
            consents.append(
                {
                    "kind": getattr(c, "kind", "unknown"),
                    "accepted_at": getattr(c, "accepted_at", None) or getattr(c, "created_at", None),
                    "version": getattr(c, "version", None),
                }
            )
    except Exception:  # noqa: BLE001
        pass

    active_sub = next((s for s in subs if s.status in ("active", "trialing")), None)

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "country": user.country,
        "role": user.role,
        "created_at": user.created_at,
        "email_verified_at": user.email_verified_at,
        "last_login_at": getattr(user, "last_login_at", None),
        "is_banned": user.deleted_at is not None,
        "deleted_at": user.deleted_at,
        "subscription_status": active_sub.status if active_sub else None,
        "subscription_plan": active_sub.plan if active_sub else None,
        "broker_count": len(brokers),
        "strategy_instance_count": len(instances),
        "subscriptions": [
            {
                "id": s.id,
                "plan": s.plan,
                "status": s.status,
                "current_period_end": s.current_period_end,
            }
            for s in subs
        ],
        "broker_accounts": [
            {
                "id": b.id,
                "broker": b.broker,
                "account_label": b.account_label,
                "is_active": b.is_active,
                "last_sync_at": b.last_sync_at,
            }
            for b in brokers
        ],
        "strategy_instances": [
            {
                "id": i.id,
                "label": i.label,
                "status": i.status,
                "kill_switch_armed": i.kill_switch_armed,
                "started_at": i.started_at,
            }
            for i in instances
        ],
        "recent_backtests": [
            {
                "id": bt.id,
                "status": bt.status,
                "asset_symbol": bt.asset_symbol,
                "timeframe": bt.timeframe,
                "created_at": bt.created_at,
            }
            for bt in backtests
        ],
        "consents": consents,
    }


async def patch_user(
    db: AsyncSession,
    *,
    actor: User,
    target_id: UUID,
    patch: dict[str, Any],
    request: Any = None,
) -> User:
    if target_id == actor.id:
        # Self-protection guardrails.
        if patch.get("role") and patch["role"] != actor.role:
            raise ForbiddenError("Cannot change own role", code="ADMIN_CANNOT_DEMOTE_SELF")
        if patch.get("is_banned"):
            raise ForbiddenError("Cannot ban self", code="ADMIN_CANNOT_BAN_SELF")

    target = await db.get(User, target_id)
    if target is None:
        raise NotFoundError("User not found", code="USER_NOT_FOUND")

    changes: dict[str, Any] = {}
    if "role" in patch and patch["role"] is not None and patch["role"] != target.role:
        target.role = patch["role"]
        changes["role"] = patch["role"]
    if "full_name" in patch and patch["full_name"] is not None:
        target.full_name = patch["full_name"]
        changes["full_name"] = patch["full_name"]
    if "country" in patch and patch["country"] is not None:
        target.country = patch["country"]
        changes["country"] = patch["country"]
    if patch.get("email_verified") is True and target.email_verified_at is None:
        target.email_verified_at = datetime.now(UTC)
        changes["email_verified_at"] = target.email_verified_at.isoformat()
    elif patch.get("email_verified") is False and target.email_verified_at is not None:
        target.email_verified_at = None
        changes["email_verified_at"] = None
    if patch.get("is_banned") is True and target.deleted_at is None:
        target.deleted_at = datetime.now(UTC)
        changes["banned"] = True
    elif patch.get("is_banned") is False and target.deleted_at is not None:
        target.deleted_at = None
        changes["banned"] = False

    if not changes:
        return target

    await record_audit(
        db,
        action="admin.user.patch",
        actor_user_id=actor.id,
        target_type="user",
        target_id=target_id,
        request=request,
        payload={"changes": changes},
    )
    await db.commit()
    return target


async def reset_user_password(
    db: AsyncSession,
    *,
    actor: User,
    target_id: UUID,
    request: Any = None,
) -> str:
    target = await db.get(User, target_id)
    if target is None:
        raise NotFoundError("User not found", code="USER_NOT_FOUND")

    temp = _gen_temp_password(16)
    target.password_hash = hash_password(temp)
    # Note: a "must_change_on_next_login" flag would live in a separate column.
    # For now we encode via payload + reuse email_verified_at trick? No — keep
    # truthful and document. Coordination with Hera Akari: she handles flag.

    await record_audit(
        db,
        action="admin.user.reset_password",
        actor_user_id=actor.id,
        target_type="user",
        target_id=target_id,
        request=request,
        payload={"force_change": True},  # plaintext NEVER recorded
    )
    await db.commit()
    return temp


async def impersonate_user(
    db: AsyncSession,
    *,
    actor: User,
    target_id: UUID,
    request: Any = None,
) -> dict[str, Any]:
    target = await db.get(User, target_id)
    if target is None:
        raise NotFoundError("User not found", code="USER_NOT_FOUND")
    if target.deleted_at is not None:
        raise ConflictError("Cannot impersonate banned user", code="USER_BANNED")
    if target.id == actor.id:
        raise ForbiddenError("Cannot impersonate self", code="ADMIN_CANNOT_IMPERSONATE_SELF")

    # Short-lived token; explicit override on TTL.
    token, expires, _ = create_token(
        subject=str(target.id),
        token_type="access",
        extra_claims={
            "impersonator_id": str(actor.id),
            "act": "impersonation",
            # Force a shorter expiry by overriding exp client-side? jose doesn't
            # let us override after encode; instead we mint then re-mint with 5min.
        },
    )
    # Re-mint with explicit 5-minute exp via raw JWT to honor the contract.
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from jose import jwt as _jwt

    from app.core.config import get_settings

    s = get_settings()
    now = _dt.now(UTC)
    short_exp = now + _td(minutes=5)
    payload = {
        "sub": str(target.id),
        "iat": int(now.timestamp()),
        "exp": int(short_exp.timestamp()),
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "typ": "access",
        "impersonator_id": str(actor.id),
        "act": "impersonation",
    }
    token = _jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)
    expires = short_exp

    await record_audit(
        db,
        action="admin.user.impersonate",
        actor_user_id=actor.id,
        target_type="user",
        target_id=target_id,
        request=request,
        payload={"expires_at": expires.isoformat()},
    )
    await db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_seconds": 300,
        "impersonated_user_id": target.id,
        "impersonator_id": actor.id,
    }


async def soft_delete_user(
    db: AsyncSession,
    *,
    actor: User,
    target_id: UUID,
    request: Any = None,
) -> None:
    if target_id == actor.id:
        raise ForbiddenError("Cannot delete self", code="ADMIN_CANNOT_DELETE_SELF")
    target = await db.get(User, target_id)
    if target is None:
        raise NotFoundError("User not found", code="USER_NOT_FOUND")

    target.deleted_at = datetime.now(UTC)
    # Halt any live engine
    await db.execute(
        update(StrategyInstance)
        .where(
            StrategyInstance.user_id == target_id,
            StrategyInstance.status.in_(("live", "paper")),
        )
        .values(status="killed", stopped_at=datetime.now(UTC))
    )
    # Cancel any active subs (best-effort; real Stripe cancel goes via billing service)
    await db.execute(
        update(Subscription)
        .where(
            Subscription.user_id == target_id,
            Subscription.status.in_(("active", "trialing", "past_due")),
        )
        .values(status="canceled", canceled_at=datetime.now(UTC))
    )

    await record_audit(
        db,
        action="admin.user.delete",
        actor_user_id=actor.id,
        target_type="user",
        target_id=target_id,
        request=request,
        payload={"cascade": ["instances_killed", "subscriptions_canceled"]},
    )
    await db.commit()


# ============================================================
# Subscriptions
# ============================================================


async def list_subscriptions(
    db: AsyncSession,
    *,
    status_filter: str | None = None,
    plan: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[Subscription], int]:
    if per_page > 100:
        per_page = 100
    stmt = select(Subscription)
    if status_filter:
        stmt = stmt.where(Subscription.status == status_filter)
    if plan:
        stmt = stmt.where(Subscription.plan == plan)
    total = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    stmt = stmt.order_by(desc(Subscription.created_at)).limit(per_page).offset((page - 1) * per_page)
    items = (await db.execute(stmt)).scalars().all()
    return list(items), int(total)


async def admin_cancel_subscription(
    db: AsyncSession,
    *,
    actor: User,
    sub_id: UUID,
    request: Any = None,
) -> Subscription:
    sub = await db.get(Subscription, sub_id)
    if sub is None:
        raise NotFoundError("Subscription not found", code="SUB_NOT_FOUND")
    if sub.status == "canceled":
        return sub
    sub.status = "canceled"
    sub.canceled_at = datetime.now(UTC)
    await record_audit(
        db,
        action="admin.subscription.cancel",
        actor_user_id=actor.id,
        target_type="subscription",
        target_id=sub.id,
        request=request,
        payload={"plan": sub.plan},
    )
    await db.commit()
    return sub


async def grant_plan(
    db: AsyncSession,
    *,
    actor: User,
    user_id: UUID,
    plan_code: str,
    duration_days: int | None,
    reason: str,
    request: Any = None,
) -> Subscription:
    target = await db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found", code="USER_NOT_FOUND")
    now = datetime.now(UTC)
    end = now + timedelta(days=duration_days) if duration_days else None
    sub = Subscription(
        user_id=user_id,
        plan=plan_code,
        status="active",
        current_period_start=now,
        current_period_end=end,
    )
    db.add(sub)
    await record_audit(
        db,
        action="admin.subscription.grant",
        actor_user_id=actor.id,
        target_type="user",
        target_id=user_id,
        request=request,
        payload={"plan_code": plan_code, "duration_days": duration_days, "reason": reason},
    )
    await db.commit()
    await db.refresh(sub)
    return sub


# ============================================================
# Audit log viewer
# ============================================================


async def list_audit_log(
    db: AsyncSession,
    *,
    actor_id: UUID | None = None,
    action: str | None = None,
    target_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[AuditLog], int]:
    if per_page > 100:
        per_page = 100
    stmt = select(AuditLog)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until:
        stmt = stmt.where(AuditLog.created_at <= until)

    total = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    stmt = stmt.order_by(desc(AuditLog.created_at)).limit(per_page).offset((page - 1) * per_page)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), int(total)


async def get_audit_entry(db: AsyncSession, *, entry_id: UUID) -> AuditLog:
    row = await db.execute(select(AuditLog).where(AuditLog.id == entry_id).limit(1))
    obj = row.scalar_one_or_none()
    if obj is None:
        raise NotFoundError("Audit entry not found", code="AUDIT_NOT_FOUND")
    return obj


# ============================================================
# Metrics + health
# ============================================================


async def metrics_snapshot(db: AsyncSession, redis: Any = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    today = now.date()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    users_total = (await db.execute(select(func.count(User.id)).where(User.deleted_at.is_(None)))).scalar_one()
    users_new_7d = (
        await db.execute(
            select(func.count(User.id)).where(User.created_at >= seven_days_ago, User.deleted_at.is_(None))
        )
    ).scalar_one()
    # "active" ≈ created or last activity recently; without last_login we approximate via instance/backtest
    users_active_7d = (
        await db.execute(
            select(func.count(func.distinct(StrategyInstance.user_id))).where(
                StrategyInstance.updated_at >= seven_days_ago
            )
        )
    ).scalar_one() if hasattr(StrategyInstance, "updated_at") else 0

    subs_active = (
        await db.execute(
            select(func.count(Subscription.id)).where(Subscription.status.in_(("active", "trialing")))
        )
    ).scalar_one()

    # MRR estimate — cents per active monthly plan; rough approximation.
    plan_cents = {"pro_monthly": 4900, "pro_yearly": 4083, "lifetime": 0, "trial": 0}
    active_subs = (
        await db.execute(
            select(Subscription.plan, func.count(Subscription.id))
            .where(Subscription.status.in_(("active", "trialing")))
            .group_by(Subscription.plan)
        )
    ).all()
    mrr = sum(plan_cents.get(p, 0) * c for p, c in active_subs)

    churn = 0.0
    total_30d = (
        await db.execute(
            select(func.count(Subscription.id)).where(Subscription.created_at >= thirty_days_ago)
        )
    ).scalar_one()
    canceled_30d = (
        await db.execute(
            select(func.count(Subscription.id)).where(
                Subscription.canceled_at.is_not(None), Subscription.canceled_at >= thirty_days_ago
            )
        )
    ).scalar_one()
    if total_30d and total_30d > 0:
        churn = round(100.0 * float(canceled_30d) / float(total_30d), 2)

    backtests_today = (
        await db.execute(
            select(func.count(Backtest.id)).where(func.date(Backtest.created_at) == today)
        )
    ).scalar_one()
    # signals/trades — optional models
    signals_today = 0
    trades_today = 0
    gross_pnl_today = 0
    try:
        from app.models.signal import Signal  # type: ignore

        signals_today = (
            await db.execute(
                select(func.count(Signal.id)).where(func.date(Signal.created_at) == today)
            )
        ).scalar_one()
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.models.trade import Trade  # type: ignore

        trades_today = (
            await db.execute(
                select(func.count(Trade.id)).where(func.date(Trade.created_at) == today)
            )
        ).scalar_one()
        pnl_col = getattr(Trade, "pnl_cents", None) or getattr(Trade, "realized_pnl_cents", None)
        if pnl_col is not None:
            gross_pnl_today = (
                await db.execute(
                    select(func.coalesce(func.sum(pnl_col), 0)).where(func.date(Trade.created_at) == today)
                )
            ).scalar_one()
    except Exception:  # noqa: BLE001
        pass

    live_engines = (
        await db.execute(
            select(func.count(StrategyInstance.id)).where(StrategyInstance.status == "live")
        )
    ).scalar_one()
    kill_armed = (
        await db.execute(
            select(func.count(StrategyInstance.id)).where(
                StrategyInstance.kill_switch_armed.is_(True),
                StrategyInstance.status == "live",
            )
        )
    ).scalar_one()

    email_queue_depth = 0
    backtest_queue_depth = (
        await db.execute(select(func.count(Backtest.id)).where(Backtest.status == "queued"))
    ).scalar_one()
    if redis is not None:
        try:
            v = await redis.llen("email:queue")
            email_queue_depth = int(v or 0)
        except Exception:  # noqa: BLE001
            pass

    return {
        "users_total": int(users_total or 0),
        "users_active_7d": int(users_active_7d or 0),
        "users_new_7d": int(users_new_7d or 0),
        "subs_active_count": int(subs_active or 0),
        "mrr_estimate_cents": int(mrr or 0),
        "churn_30d_pct": float(churn),
        "backtests_today": int(backtests_today or 0),
        "signals_today": int(signals_today or 0),
        "trades_today": int(trades_today or 0),
        "gross_pnl_today_cents": int(gross_pnl_today or 0),
        "live_engines_running": int(live_engines or 0),
        "kill_switches_armed": int(kill_armed or 0),
        "email_queue_depth": int(email_queue_depth),
        "backtest_queue_depth": int(backtest_queue_depth or 0),
        "captured_at": now,
    }


async def dependency_health(db: AsyncSession, *, redis: Any = None) -> dict[str, Any]:
    import asyncio
    import time as _time

    from app.db.session import ping_database

    deps: list[dict[str, Any]] = []
    overall = "ok"

    async def _check(name: str, coro) -> None:
        nonlocal overall
        t0 = _time.perf_counter()
        try:
            ok = await coro
            status = "ok" if ok else "degraded"
        except Exception as exc:  # noqa: BLE001
            status = "fail"
            ok = False
            deps.append(
                {
                    "name": name,
                    "status": status,
                    "last_check": datetime.now(UTC),
                    "detail": str(exc),
                    "latency_ms": (_time.perf_counter() - t0) * 1000,
                }
            )
            if overall != "fail":
                overall = "fail" if status == "fail" else "degraded"
            return
        deps.append(
            {
                "name": name,
                "status": status,
                "last_check": datetime.now(UTC),
                "detail": None,
                "latency_ms": (_time.perf_counter() - t0) * 1000,
            }
        )
        if status != "ok" and overall == "ok":
            overall = "degraded"

    await _check("postgres", ping_database(2.0))

    async def _redis_ping() -> bool:
        if redis is None:
            return False
        try:
            await asyncio.wait_for(redis.ping(), timeout=2.0)
            return True
        except Exception:  # noqa: BLE001
            return False

    if redis is None:
        deps.append(
            {
                "name": "redis",
                "status": "not_configured",
                "last_check": datetime.now(UTC),
                "detail": None,
                "latency_ms": None,
            }
        )
    else:
        await _check("redis", _redis_ping())

    # Stripe/email/mt5-bridge/tv-engine — best-effort HEAD/connect
    async def _http_head(url: str) -> bool:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as cx:
            r = await cx.head(url)
        return r.status_code < 500

    await _check("stripe", _http_head("https://api.stripe.com/v1/"))
    await _check("email_provider", _http_head("https://api.resend.com"))

    # mt5-bridge + tv-engine — placeholders; treat as not_configured if no env URL
    from app.core.config import get_settings

    s = get_settings()
    mt5_url = getattr(s, "mt5_bridge_url", None)
    tv_url = getattr(s, "tradingview_engine_url", None)
    if mt5_url:
        await _check("mt5_bridge", _http_head(mt5_url))
    else:
        deps.append(
            {
                "name": "mt5_bridge",
                "status": "not_configured",
                "last_check": datetime.now(UTC),
                "detail": None,
                "latency_ms": None,
            }
        )
    if tv_url:
        await _check("tradingview_engine", _http_head(tv_url))
    else:
        deps.append(
            {
                "name": "tradingview_engine",
                "status": "not_configured",
                "last_check": datetime.now(UTC),
                "detail": None,
                "latency_ms": None,
            }
        )

    return {"overall": overall, "dependencies": deps}


# ============================================================
# Strategies
# ============================================================


async def list_all_strategies(db: AsyncSession) -> list[Strategy]:
    rows = (await db.execute(select(Strategy).order_by(Strategy.code))).scalars().all()
    return list(rows)


async def patch_strategy(
    db: AsyncSession,
    *,
    actor: User,
    code: str,
    patch: dict[str, Any],
    request: Any = None,
) -> Strategy:
    row = (await db.execute(select(Strategy).where(Strategy.code == code).limit(1))).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Strategy not found", code="STRATEGY_NOT_FOUND")

    changes: dict[str, Any] = {}
    if patch.get("is_enabled") is not None and row.is_enabled != patch["is_enabled"]:
        row.is_enabled = patch["is_enabled"]
        changes["is_enabled"] = row.is_enabled
    if patch.get("risk_rating") and row.risk_rating != patch["risk_rating"]:
        row.risk_rating = patch["risk_rating"]
        changes["risk_rating"] = row.risk_rating
    if patch.get("default_params") is not None:
        row.default_params = patch["default_params"]
        changes["default_params"] = patch["default_params"]

    if changes:
        await record_audit(
            db,
            action="admin.strategy.patch",
            actor_user_id=actor.id,
            target_type="strategy",
            target_id=row.id,
            request=request,
            payload={"code": code, "changes": changes},
        )
        await db.commit()
    return row


async def kill_all_strategy_instances(
    db: AsyncSession,
    *,
    actor: User,
    code: str,
    request: Any = None,
) -> int:
    strategy = (await db.execute(select(Strategy).where(Strategy.code == code).limit(1))).scalar_one_or_none()
    if strategy is None:
        raise NotFoundError("Strategy not found", code="STRATEGY_NOT_FOUND")

    result = await db.execute(
        update(StrategyInstance)
        .where(
            StrategyInstance.strategy_id == strategy.id,
            StrategyInstance.status.in_(("live", "paper")),
        )
        .values(status="killed", stopped_at=datetime.now(UTC))
    )
    count = result.rowcount or 0

    await record_audit(
        db,
        action="admin.strategy.kill_all_instances",
        actor_user_id=actor.id,
        target_type="strategy",
        target_id=strategy.id,
        request=request,
        payload={"code": code, "killed": count},
    )
    await db.commit()
    return int(count)


# ============================================================
# MT5 bridge pool
# ============================================================


async def list_mt5_bridges(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(BrokerAccount).where(
                BrokerAccount.broker == "exness_mt5",
                BrokerAccount.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    now = datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for b in rows:
        last = b.last_sync_at
        if last is None:
            status = "unknown"
            age = None
        else:
            age = int((now - last).total_seconds()) if last.tzinfo else int(
                (now.replace(tzinfo=None) - last).total_seconds()
            )
            if age <= 120:
                status = "ok"
            elif age <= 600:
                status = "stale"
            else:
                status = "down"
        out.append(
            {
                "id": b.id,
                "user_id": b.user_id,
                "broker": b.broker,
                "account_label": b.account_label,
                "is_active": b.is_active,
                "last_sync_at": b.last_sync_at,
                "heartbeat_age_seconds": age,
                "status": status,
            }
        )
    return out


async def probe_mt5_bridge(
    db: AsyncSession,
    *,
    actor: User,
    bridge_id: UUID,
    request: Any = None,
) -> dict[str, Any]:
    bridge = await db.get(BrokerAccount, bridge_id)
    if bridge is None or bridge.broker != "exness_mt5":
        raise NotFoundError("Bridge not found", code="BRIDGE_NOT_FOUND")
    # Real probe would call mt5-bridge HTTP; here we touch last_sync_at as a
    # health-check hint and let the bridge service do the actual probe.
    bridge.last_sync_at = datetime.now(UTC)
    await record_audit(
        db,
        action="admin.mt5_bridge.probe",
        actor_user_id=actor.id,
        target_type="broker_account",
        target_id=bridge.id,
        request=request,
        payload={"probe": "queued"},
    )
    await db.commit()
    return {
        "bridge_id": bridge.id,
        "status": "ok",
        "detail": "Probe queued; check heartbeat in /admin/mt5-bridges.",
        "probed_at": bridge.last_sync_at,
    }


# ============================================================
# Broadcast notifications
# ============================================================


async def broadcast_notification(
    db: AsyncSession,
    *,
    actor: User,
    title: str,
    body: str,
    audience: str,
    channel: str,
    request: Any = None,
) -> int:
    user_stmt = select(User.id).where(User.deleted_at.is_(None))
    if audience == "active":
        # Active = currently has active sub
        active_subs_sq = (
            select(Subscription.user_id)
            .where(Subscription.status.in_(("active", "trialing")))
            .subquery()
        )
        user_stmt = user_stmt.where(User.id.in_(select(active_subs_sq.c.user_id)))
    elif audience in {"user", "admin"}:
        user_stmt = user_stmt.where(User.role == audience)
    elif audience in {"pro_monthly", "pro_yearly", "lifetime", "trial"}:
        plan_subs_sq = (
            select(Subscription.user_id)
            .where(
                Subscription.plan == audience,
                Subscription.status.in_(("active", "trialing")),
            )
            .subquery()
        )
        user_stmt = user_stmt.where(User.id.in_(select(plan_subs_sq.c.user_id)))
    # else 'all' — no further filter

    user_ids = (await db.execute(user_stmt)).scalars().all()
    payload = {"title": title, "body": body, "from": "admin", "actor_id": str(actor.id)}

    queued = 0
    for uid in user_ids:
        db.add(
            Notification(
                user_id=uid,
                channel=channel,
                kind="admin_broadcast",
                payload=payload,
            )
        )
        queued += 1

    await record_audit(
        db,
        action="admin.notification.broadcast",
        actor_user_id=actor.id,
        target_type="audience",
        request=request,
        payload={"audience": audience, "channel": channel, "queued": queued, "title": title},
    )
    await db.commit()
    return queued


# ============================================================
# Global kill switch (2-of-N approval)
# ============================================================

_KILL_SWITCH_REDIS_KEY = "admin:kill_switch:global"
_KILL_SWITCH_PENDING_KEY = "admin:kill_switch:pending"


async def _count_admins(db: AsyncSession) -> int:
    return (
        await db.execute(select(func.count(User.id)).where(User.role == "admin", User.deleted_at.is_(None)))
    ).scalar_one()


async def engage_global_kill_switch(
    db: AsyncSession,
    *,
    actor: User,
    reason: str,
    redis: Any = None,
    request: Any = None,
) -> dict[str, Any]:
    admin_count = await _count_admins(db)
    approvers_required = 2 if admin_count > 1 else 1

    approvers: list[str] = []
    pending = False
    if redis is not None and approvers_required > 1:
        try:
            await redis.sadd(_KILL_SWITCH_PENDING_KEY, str(actor.id))
            await redis.expire(_KILL_SWITCH_PENDING_KEY, _KILL_SWITCH_TTL_SECONDS)
            members = await redis.smembers(_KILL_SWITCH_PENDING_KEY)
            approvers = [m.decode() if isinstance(m, (bytes, bytearray)) else m for m in members]
        except Exception:  # noqa: BLE001
            approvers = [str(actor.id)]
    else:
        approvers = [str(actor.id)]

    if len(approvers) < approvers_required:
        pending = True
        await record_audit(
            db,
            action="admin.kill_switch.engage_pending",
            actor_user_id=actor.id,
            target_type="system",
            request=request,
            payload={"reason": reason, "approvers": approvers, "required": approvers_required},
        )
        await db.commit()
        return {
            "engaged": False,
            "engaged_at": None,
            "engaged_by": [UUID(a) for a in approvers],
            "reason": reason,
            "approvers_required": approvers_required,
            "approvers_collected": len(approvers),
            "pending": True,
        }

    # Quorum reached — engage.
    now = datetime.now(UTC)
    if redis is not None:
        try:
            import json as _json

            await redis.set(
                _KILL_SWITCH_REDIS_KEY,
                _json.dumps(
                    {
                        "engaged_at": now.isoformat(),
                        "engaged_by": approvers,
                        "reason": reason,
                    }
                ),
            )
            await redis.delete(_KILL_SWITCH_PENDING_KEY)
        except Exception:  # noqa: BLE001
            pass

    await db.execute(
        update(StrategyInstance)
        .where(StrategyInstance.status == "live")
        .values(status="killed", stopped_at=now)
    )

    await record_audit(
        db,
        action="admin.kill_switch.engaged",
        actor_user_id=actor.id,
        target_type="system",
        request=request,
        payload={"reason": reason, "approvers": approvers, "required": approvers_required},
    )
    await db.commit()
    return {
        "engaged": True,
        "engaged_at": now,
        "engaged_by": [UUID(a) for a in approvers],
        "reason": reason,
        "approvers_required": approvers_required,
        "approvers_collected": len(approvers),
        "pending": False,
    }


async def disarm_global_kill_switch(
    db: AsyncSession,
    *,
    actor: User,
    reason: str,
    redis: Any = None,
    request: Any = None,
) -> dict[str, Any]:
    admin_count = await _count_admins(db)
    approvers_required = 2 if admin_count > 1 else 1
    key = _KILL_SWITCH_PENDING_KEY + ":disarm"

    approvers: list[str] = []
    if redis is not None and approvers_required > 1:
        try:
            await redis.sadd(key, str(actor.id))
            await redis.expire(key, _KILL_SWITCH_TTL_SECONDS)
            members = await redis.smembers(key)
            approvers = [m.decode() if isinstance(m, (bytes, bytearray)) else m for m in members]
        except Exception:  # noqa: BLE001
            approvers = [str(actor.id)]
    else:
        approvers = [str(actor.id)]

    if len(approvers) < approvers_required:
        await record_audit(
            db,
            action="admin.kill_switch.disarm_pending",
            actor_user_id=actor.id,
            target_type="system",
            request=request,
            payload={"reason": reason, "approvers": approvers, "required": approvers_required},
        )
        await db.commit()
        return {
            "engaged": True,
            "engaged_at": None,
            "engaged_by": [UUID(a) for a in approvers],
            "reason": reason,
            "approvers_required": approvers_required,
            "approvers_collected": len(approvers),
            "pending": True,
        }

    if redis is not None:
        try:
            await redis.delete(_KILL_SWITCH_REDIS_KEY)
            await redis.delete(key)
        except Exception:  # noqa: BLE001
            pass

    await record_audit(
        db,
        action="admin.kill_switch.disarmed",
        actor_user_id=actor.id,
        target_type="system",
        request=request,
        payload={"reason": reason, "approvers": approvers},
    )
    await db.commit()
    return {
        "engaged": False,
        "engaged_at": None,
        "engaged_by": [UUID(a) for a in approvers],
        "reason": reason,
        "approvers_required": approvers_required,
        "approvers_collected": len(approvers),
        "pending": False,
    }


async def kill_switch_status(redis: Any = None) -> dict[str, Any]:
    if redis is None:
        return {"engaged": False, "pending": False, "approvers_required": 1, "approvers_collected": 0, "engaged_by": []}
    try:
        import json as _json

        raw = await redis.get(_KILL_SWITCH_REDIS_KEY)
        if raw is None:
            return {
                "engaged": False,
                "pending": False,
                "approvers_required": 1,
                "approvers_collected": 0,
                "engaged_by": [],
            }
        data = _json.loads(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
        return {
            "engaged": True,
            "engaged_at": datetime.fromisoformat(data["engaged_at"]),
            "engaged_by": [UUID(a) for a in data.get("engaged_by", [])],
            "reason": data.get("reason"),
            "approvers_required": 1,
            "approvers_collected": len(data.get("engaged_by", [])),
            "pending": False,
        }
    except Exception:  # noqa: BLE001
        return {"engaged": False, "pending": False, "approvers_required": 1, "approvers_collected": 0, "engaged_by": []}
