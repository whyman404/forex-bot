"""Strategy catalog (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.strategy import StrategyPublic
from app.services.strategy_service import StrategyService

router = APIRouter()

ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get("", response_model=list[StrategyPublic], responses=ERROR_RESPONSES)
async def list_strategies(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StrategyPublic]:
    return await StrategyService(db).list_catalog()


@router.get("/{code}", response_model=StrategyPublic, responses=ERROR_RESPONSES)
async def get_strategy(
    code: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyPublic:
    return await StrategyService(db).get_by_code(code)
