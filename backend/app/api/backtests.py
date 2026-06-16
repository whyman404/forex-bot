"""Backtest endpoints — enqueue + retrieve."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import rate_limit
from app.models.user import User
from app.schemas.backtest import (
    BacktestCreateRequest,
    BacktestPublic,
    EquityCurveResponse,
)
from app.services.backtest_service import BacktestService

router = APIRouter()

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    402: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _redis(request: Request):  # type: ignore[no-untyped-def]
    limiter = getattr(request.app.state, "rate_limiter", None)
    return limiter.redis if limiter is not None else None


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BacktestPublic,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit(scope="backtest-enqueue", per_min=10))],
)
async def enqueue_backtest(
    payload: BacktestCreateRequest,
    request: Request,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacktestPublic:
    return await BacktestService(db, redis=_redis(request)).enqueue(current.id, payload)


@router.get("", response_model=list[BacktestPublic], responses=ERROR_RESPONSES)
async def list_backtests(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BacktestPublic]:
    return await BacktestService(db).list_for_user(current.id)


@router.get("/{backtest_id}", response_model=BacktestPublic, responses=ERROR_RESPONSES)
async def get_backtest(
    backtest_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacktestPublic:
    return await BacktestService(db).get(current.id, backtest_id)


@router.get(
    "/{backtest_id}/equity-curve",
    response_model=EquityCurveResponse,
    responses=ERROR_RESPONSES,
)
async def get_equity_curve(
    backtest_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EquityCurveResponse:
    return await BacktestService(db).equity_curve(current.id, backtest_id)
