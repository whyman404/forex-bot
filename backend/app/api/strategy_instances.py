"""Strategy instance endpoints — create, list, update, start, stop, kill, go-live, revert."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal import read_router as _live_read_router
from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import rate_limit
from app.models.user import User
from app.schemas.live import GateResult
from app.schemas.strategy import (
    StrategyInstanceCreateRequest,
    StrategyInstancePublic,
    StrategyInstanceUpdateRequest,
)
from app.services.live_gate_service import LiveGateService
from app.services.strategy_service import StrategyService
from app.services.subscription_guard import require_active_subscription

router = APIRouter()

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    402: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=StrategyInstancePublic,
    responses=ERROR_RESPONSES,
)
async def create_instance(
    payload: StrategyInstanceCreateRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyInstancePublic:
    return await StrategyService(db).create_instance(current.id, payload)


@router.get("", response_model=list[StrategyInstancePublic], responses=ERROR_RESPONSES)
async def list_instances(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StrategyInstancePublic]:
    return await StrategyService(db).list_instances(current.id)


@router.patch(
    "/{instance_id}",
    response_model=StrategyInstancePublic,
    responses=ERROR_RESPONSES,
)
async def update_instance(
    instance_id: UUID,
    payload: StrategyInstanceUpdateRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyInstancePublic:
    return await StrategyService(db).update_instance(current.id, instance_id, payload)


@router.post(
    "/{instance_id}/start",
    response_model=StrategyInstancePublic,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit(scope="instance-control", per_min=20))],
)
async def start_instance(
    instance_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyInstancePublic:
    return await StrategyService(db).start_instance(current.id, instance_id)


@router.post(
    "/{instance_id}/stop",
    response_model=StrategyInstancePublic,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit(scope="instance-control", per_min=20))],
)
async def stop_instance(
    instance_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyInstancePublic:
    return await StrategyService(db).stop_instance(current.id, instance_id)


@router.post(
    "/{instance_id}/kill",
    response_model=StrategyInstancePublic,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit(scope="instance-control", per_min=5))],
)
async def kill_instance(
    instance_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyInstancePublic:
    return await StrategyService(db).kill_instance(current.id, instance_id)


# ---- Live trading transitions ---------------------------------------------


@router.post(
    "/{instance_id}/preflight",
    response_model=GateResult,
    responses=ERROR_RESPONSES,
    summary="Run live-trading gate checks WITHOUT flipping status",
)
async def preflight_live(
    instance_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GateResult:
    return await LiveGateService(db).can_go_live(instance_id, current)


@router.post(
    "/{instance_id}/go-live",
    response_model=StrategyInstancePublic,
    responses=ERROR_RESPONSES,
    summary="Flip instance to live (after gate pass + OMS dispatch)",
    dependencies=[
        Depends(rate_limit(scope="instance-control", per_min=10)),
        Depends(require_active_subscription(require_paid=True)),
    ],
)
async def go_live(
    instance_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyInstancePublic:
    _gate, instance = await StrategyService(db).go_live(current, instance_id)
    return StrategyInstancePublic.model_validate(instance)


@router.post(
    "/{instance_id}/revert-to-paper",
    response_model=StrategyInstancePublic,
    responses=ERROR_RESPONSES,
    summary="Graceful revert: close open positions via OMS then flip paper",
    dependencies=[Depends(rate_limit(scope="instance-control", per_min=10))],
)
async def revert_to_paper(
    instance_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyInstancePublic:
    return await StrategyService(db).revert_to_paper(current.id, instance_id)


# ---- Read-side helpers (signals/trades/health) — mounted at end -----------
router.include_router(_live_read_router)
