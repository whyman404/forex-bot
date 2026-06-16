"""Admin endpoints — role-gated. Destructive ops require step-up TOTP.

Atlas Goro — every mutation goes through `admin_service.*`, which writes
audit_log inside the same transaction. Read endpoints stay in the router
when trivial; complex aggregates live in the service.

Rate limit: 60rpm baseline; broadcast 1 per 5min (gated via dep).
Coordination:
- Argus R4: step-up TOTP via `require_step_up` for destructive ops.
- Eos R6: response shapes match `app/schemas/admin.py` exactly.
- Mnemosyne Rin: queries are N+1 safe (joined subqueries).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorResponse, RateLimitedError
from app.db.session import get_db
from app.middleware.auth import require_admin, require_step_up
from app.middleware.rate_limit import rate_limit
from app.models.user import User
from app.schemas.admin import (
    AdminMetricsSnapshot,
    AuditLogEntry,
    BroadcastRequest,
    BroadcastResponse,
    DependencyHealth,
    GrantPlanRequest,
    ImpersonationRequest,
    ImpersonationResponse,
    KillAllResponse,
    KillSwitchRequest,
    KillSwitchStatus,
    Mt5BridgeStatus,
    ProbeResponse,
    ResetPasswordResponse,
    StrategyAdminPatch,
    SubscriptionAdminMini,
    UserAdminDetail,
    UserAdminSummary,
    UserPatchAdmin,
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services import admin_service

router = APIRouter(dependencies=[Depends(require_admin), Depends(rate_limit(scope="admin", per_min=60))])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


# ============================================================
# Sanity / ping
# ============================================================


@router.get("/ping", response_model=MessageResponse, responses=ERROR_RESPONSES)
async def admin_ping(current: User = Depends(require_admin)) -> MessageResponse:
    return MessageResponse(message=f"pong, {current.email}")


# ============================================================
# Users
# ============================================================


@router.get(
    "/users",
    response_model=PaginatedResponse[UserAdminSummary],
    responses=ERROR_RESPONSES,
    summary="List users with filters + aggregated counts",
)
async def list_users_endpoint(
    q: str | None = Query(default=None, max_length=200),
    role: str | None = Query(default=None, pattern="^(user|admin)$"),
    user_status: str | None = Query(default=None, alias="status", pattern="^(active|banned)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="created_at", pattern="^(created_at|last_login_at)$"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[UserAdminSummary]:
    items, total = await admin_service.list_users(
        db, q=q, role=role, status_filter=user_status, page=page, per_page=per_page, sort=sort
    )
    return PaginatedResponse[UserAdminSummary](
        items=[UserAdminSummary(**i) for i in items],
        total=total,
        page=page,
        page_size=per_page,
    )


@router.get(
    "/users/{user_id}",
    response_model=UserAdminDetail,
    responses=ERROR_RESPONSES,
    summary="Full user profile + related entities",
)
async def get_user_detail_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> UserAdminDetail:
    detail = await admin_service.get_user_detail(db, user_id)
    return UserAdminDetail(**detail)


@router.patch(
    "/users/{user_id}",
    response_model=UserAdminSummary,
    responses=ERROR_RESPONSES,
    summary="Patch user fields (role, full_name, country, verified, banned)",
)
async def patch_user_endpoint(
    user_id: UUID,
    body: UserPatchAdmin,
    request: Request,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserAdminSummary:
    # If banning, require step-up TOTP (defense in depth).
    if body.is_banned is True:
        await require_step_up(
            request,
            current,
            x_step_up_totp=request.headers.get("X-Step-Up-TOTP"),
        )
    target = await admin_service.patch_user(
        db,
        actor=current,
        target_id=user_id,
        patch=body.model_dump(exclude_unset=True),
        request=request,
    )
    return UserAdminSummary(
        id=target.id,
        email=target.email,
        full_name=target.full_name,
        country=target.country,
        role=target.role,
        created_at=target.created_at,
        email_verified_at=target.email_verified_at,
        last_login_at=getattr(target, "last_login_at", None),
        is_banned=target.deleted_at is not None,
        deleted_at=target.deleted_at,
    )


@router.post(
    "/users/{user_id}/reset-password",
    response_model=ResetPasswordResponse,
    responses=ERROR_RESPONSES,
    summary="Generate temp password (returned ONCE)",
)
async def reset_password_endpoint(
    user_id: UUID,
    request: Request,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ResetPasswordResponse:
    temp = await admin_service.reset_user_password(
        db, actor=current, target_id=user_id, request=request
    )
    return ResetPasswordResponse(user_id=user_id, temporary_password=temp)


@router.post(
    "/users/{user_id}/impersonate",
    response_model=ImpersonationResponse,
    responses=ERROR_RESPONSES,
    summary="Mint 5-min token as target user (requires step-up TOTP)",
)
async def impersonate_endpoint(
    user_id: UUID,
    body: ImpersonationRequest,
    request: Request,
    current: User = Depends(require_step_up),
    db: AsyncSession = Depends(get_db),
) -> ImpersonationResponse:
    out = await admin_service.impersonate_user(
        db, actor=current, target_id=user_id, request=request
    )
    return ImpersonationResponse(**out)


@router.delete(
    "/users/{user_id}",
    response_model=MessageResponse,
    responses=ERROR_RESPONSES,
    summary="Soft delete user; cancels subs + kills engines",
)
async def delete_user_endpoint(
    user_id: UUID,
    request: Request,
    current: User = Depends(require_step_up),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await admin_service.soft_delete_user(
        db, actor=current, target_id=user_id, request=request
    )
    return MessageResponse(message="User soft-deleted; subs canceled; engines killed")


# ============================================================
# Subscriptions
# ============================================================


@router.get(
    "/subscriptions",
    response_model=PaginatedResponse[SubscriptionAdminMini],
    responses=ERROR_RESPONSES,
)
async def list_subs_endpoint(
    sub_status: str | None = Query(default=None, alias="status"),
    plan: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[SubscriptionAdminMini]:
    items, total = await admin_service.list_subscriptions(
        db, status_filter=sub_status, plan=plan, page=page, per_page=per_page
    )
    return PaginatedResponse[SubscriptionAdminMini](
        items=[
            SubscriptionAdminMini(
                id=s.id, plan=s.plan, status=s.status, current_period_end=s.current_period_end
            )
            for s in items
        ],
        total=total,
        page=page,
        page_size=per_page,
    )


@router.post(
    "/subscriptions/{sub_id}/cancel",
    response_model=SubscriptionAdminMini,
    responses=ERROR_RESPONSES,
)
async def cancel_sub_endpoint(
    sub_id: UUID,
    request: Request,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionAdminMini:
    sub = await admin_service.admin_cancel_subscription(
        db, actor=current, sub_id=sub_id, request=request
    )
    return SubscriptionAdminMini(
        id=sub.id, plan=sub.plan, status=sub.status, current_period_end=sub.current_period_end
    )


@router.post(
    "/users/{user_id}/grant-plan",
    response_model=SubscriptionAdminMini,
    responses=ERROR_RESPONSES,
)
async def grant_plan_endpoint(
    user_id: UUID,
    body: GrantPlanRequest,
    request: Request,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionAdminMini:
    sub = await admin_service.grant_plan(
        db,
        actor=current,
        user_id=user_id,
        plan_code=body.plan_code,
        duration_days=body.duration_days,
        reason=body.reason,
        request=request,
    )
    return SubscriptionAdminMini(
        id=sub.id, plan=sub.plan, status=sub.status, current_period_end=sub.current_period_end
    )


# ============================================================
# Audit log viewer
# ============================================================


@router.get(
    "/audit-log",
    response_model=PaginatedResponse[AuditLogEntry],
    responses=ERROR_RESPONSES,
)
async def audit_log_endpoint(
    actor_id: UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=64),
    target_type: str | None = Query(default=None, max_length=32),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[AuditLogEntry]:
    rows, total = await admin_service.list_audit_log(
        db,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        since=since,
        until=until,
        page=page,
        per_page=per_page,
    )
    return PaginatedResponse[AuditLogEntry](
        items=[
            AuditLogEntry(
                id=r.id,
                actor_user_id=r.actor_user_id,
                action=r.action,
                target_type=r.target_type,
                target_id=r.target_id,
                payload_redacted=r.payload_redacted,
                ip_addr=str(r.ip_addr) if r.ip_addr else None,
                user_agent=r.user_agent,
                created_at=r.created_at,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=per_page,
    )


@router.get(
    "/audit-log/{entry_id}",
    response_model=AuditLogEntry,
    responses=ERROR_RESPONSES,
)
async def audit_entry_endpoint(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AuditLogEntry:
    r = await admin_service.get_audit_entry(db, entry_id=entry_id)
    return AuditLogEntry(
        id=r.id,
        actor_user_id=r.actor_user_id,
        action=r.action,
        target_type=r.target_type,
        target_id=r.target_id,
        payload_redacted=r.payload_redacted,
        ip_addr=str(r.ip_addr) if r.ip_addr else None,
        user_agent=r.user_agent,
        created_at=r.created_at,
    )


# ============================================================
# System metrics + health
# ============================================================


@router.get("/metrics", response_model=AdminMetricsSnapshot, responses=ERROR_RESPONSES)
async def metrics_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AdminMetricsSnapshot:
    redis = getattr(request.app.state, "redis", None)
    snap = await admin_service.metrics_snapshot(db, redis=redis)
    return AdminMetricsSnapshot(**snap)


@router.get(
    "/health/dependencies",
    response_model=DependencyHealth,
    responses=ERROR_RESPONSES,
)
async def health_deps_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DependencyHealth:
    redis = getattr(request.app.state, "redis", None)
    out = await admin_service.dependency_health(db, redis=redis)
    return DependencyHealth(**out)


# ============================================================
# Strategy management
# ============================================================


@router.get("/strategies", responses=ERROR_RESPONSES)
async def list_strategies_endpoint(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = await admin_service.list_all_strategies(db)
    return [
        {
            "id": str(r.id),
            "code": r.code,
            "display_name": r.display_name,
            "asset_class": r.asset_class,
            "risk_rating": r.risk_rating,
            "is_enabled": r.is_enabled,
            "version": r.version,
            "default_params": r.default_params,
        }
        for r in rows
    ]


@router.patch("/strategies/{code}", responses=ERROR_RESPONSES)
async def patch_strategy_endpoint(
    code: str,
    body: StrategyAdminPatch,
    request: Request,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await admin_service.patch_strategy(
        db, actor=current, code=code, patch=body.model_dump(exclude_unset=True), request=request
    )
    return {
        "code": row.code,
        "is_enabled": row.is_enabled,
        "risk_rating": row.risk_rating,
        "default_params": row.default_params,
    }


@router.post(
    "/strategies/{code}/kill-all-instances",
    response_model=KillAllResponse,
    responses=ERROR_RESPONSES,
)
async def kill_all_strategy_instances_endpoint(
    code: str,
    request: Request,
    current: User = Depends(require_step_up),
    db: AsyncSession = Depends(get_db),
) -> KillAllResponse:
    n = await admin_service.kill_all_strategy_instances(
        db, actor=current, code=code, request=request
    )
    return KillAllResponse(strategy_code=code, instances_killed=n)


# ============================================================
# MT5 bridge pool
# ============================================================


@router.get("/mt5-bridges", responses=ERROR_RESPONSES)
async def mt5_bridges_endpoint(
    db: AsyncSession = Depends(get_db),
) -> list[Mt5BridgeStatus]:
    rows = await admin_service.list_mt5_bridges(db)
    return [Mt5BridgeStatus(**r) for r in rows]


@router.post(
    "/mt5-bridges/{bridge_id}/probe",
    response_model=ProbeResponse,
    responses=ERROR_RESPONSES,
)
async def probe_bridge_endpoint(
    bridge_id: UUID,
    request: Request,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ProbeResponse:
    out = await admin_service.probe_mt5_bridge(
        db, actor=current, bridge_id=bridge_id, request=request
    )
    return ProbeResponse(**out)


# ============================================================
# Broadcast
# ============================================================


async def _broadcast_throttle(request: Request) -> None:
    """Custom 1-per-5min throttle: keyed by user, scoped 'admin:broadcast'."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    import time as _time

    user_id = getattr(request.state, "user_id", "anon")
    window = int(_time.time() // 300)  # 5-minute window
    key = f"rl:admin:broadcast:{user_id}:{window}"
    try:
        count = await limiter.redis.incr(key)
        if count == 1:
            await limiter.redis.expire(key, 360)
    except Exception:  # noqa: BLE001 — fail open
        return
    if count > 1:
        raise RateLimitedError(
            "Broadcast rate exceeded (1 per 5 minutes)",
            details={"scope": "admin:broadcast", "window_seconds": 300},
        )


@router.post(
    "/notifications/broadcast",
    response_model=BroadcastResponse,
    responses=ERROR_RESPONSES,
)
async def broadcast_endpoint(
    body: BroadcastRequest,
    request: Request,
    _throttle: None = Depends(_broadcast_throttle),
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BroadcastResponse:
    # Step-up TOTP required for email-all
    if body.channel == "email" and body.audience == "all":
        await require_step_up(
            request, current, x_step_up_totp=request.headers.get("X-Step-Up-TOTP")
        )
    queued = await admin_service.broadcast_notification(
        db,
        actor=current,
        title=body.title,
        body=body.body,
        audience=body.audience,
        channel=body.channel,
        request=request,
    )
    return BroadcastResponse(queued_count=queued, audience=body.audience, channel=body.channel)


# ============================================================
# Global kill switch
# ============================================================


@router.post(
    "/system/global-kill-switch",
    response_model=KillSwitchStatus,
    responses=ERROR_RESPONSES,
)
async def engage_kill_switch_endpoint(
    body: KillSwitchRequest,
    request: Request,
    current: User = Depends(require_step_up),
    db: AsyncSession = Depends(get_db),
) -> KillSwitchStatus:
    redis = getattr(request.app.state, "redis", None)
    out = await admin_service.engage_global_kill_switch(
        db, actor=current, reason=body.reason, redis=redis, request=request
    )
    return KillSwitchStatus(**out)


@router.post(
    "/system/global-kill-switch/disarm",
    response_model=KillSwitchStatus,
    responses=ERROR_RESPONSES,
)
async def disarm_kill_switch_endpoint(
    body: KillSwitchRequest,
    request: Request,
    current: User = Depends(require_step_up),
    db: AsyncSession = Depends(get_db),
) -> KillSwitchStatus:
    redis = getattr(request.app.state, "redis", None)
    out = await admin_service.disarm_global_kill_switch(
        db, actor=current, reason=body.reason, redis=redis, request=request
    )
    return KillSwitchStatus(**out)


@router.get(
    "/system/global-kill-switch",
    response_model=KillSwitchStatus,
    responses=ERROR_RESPONSES,
)
async def kill_switch_status_endpoint(request: Request) -> KillSwitchStatus:
    redis = getattr(request.app.state, "redis", None)
    out = await admin_service.kill_switch_status(redis=redis)
    return KillSwitchStatus(**out)
