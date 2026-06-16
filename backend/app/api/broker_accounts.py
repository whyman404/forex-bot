"""Broker account endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import rate_limit
from app.models.user import User
from app.schemas.broker import (
    BrokerAccountCreateRequest,
    BrokerAccountPublic,
    BrokerAccountUpdateRequest,
    BrokerConnectionTestResponse,
)
from app.services.broker_service import BrokerService

router = APIRouter()

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=BrokerAccountPublic,
    responses=ERROR_RESPONSES,
)
async def create_broker_account(
    payload: BrokerAccountCreateRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerAccountPublic:
    return await BrokerService(db).create(current.id, payload)


@router.get("", response_model=list[BrokerAccountPublic], responses=ERROR_RESPONSES)
async def list_broker_accounts(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BrokerAccountPublic]:
    return await BrokerService(db).list_for_user(current.id)


@router.patch(
    "/{account_id}",
    response_model=BrokerAccountPublic,
    responses=ERROR_RESPONSES,
)
async def update_broker_account(
    account_id: UUID,
    payload: BrokerAccountUpdateRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerAccountPublic:
    return await BrokerService(db).update(current.id, account_id, payload)


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERROR_RESPONSES,
)
async def delete_broker_account(
    account_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await BrokerService(db).delete(current.id, account_id)


@router.post(
    "/{account_id}/test-connection",
    response_model=BrokerConnectionTestResponse,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit(scope="broker-test", per_min=10))],
)
async def test_connection(
    account_id: UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerConnectionTestResponse:
    return await BrokerService(db).test_connection(current.id, account_id)
