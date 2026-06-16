"""Strategy + strategy instance schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrategyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    display_name: str
    description: str | None
    asset_class: str
    risk_rating: str
    version: int
    default_params: dict[str, Any]
    is_enabled: bool
    # R5: surface external-service dependency so the UI can show the
    # extra TV-health gate banner on the strategy detail page.
    requires_external_service: bool = False


class StrategyInstanceCreateRequest(BaseModel):
    strategy_code: str = Field(min_length=1, max_length=64)
    broker_account_id: UUID
    label: str = Field(min_length=1, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)
    risk_percent: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0"), le=Decimal("10"))
    max_daily_loss_cents: int = Field(default=10_000_00, ge=0)
    mode: Literal["paper", "live"] = "paper"


class StrategyInstanceUpdateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    params: dict[str, Any] | None = None
    risk_percent: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("10"))
    max_daily_loss_cents: int | None = Field(default=None, ge=0)


class StrategyInstancePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy_id: UUID
    broker_account_id: UUID
    label: str
    status: Literal["paper", "live", "stopped", "killed"]
    params: dict[str, Any]
    risk_percent: Decimal
    max_daily_loss_cents: int
    daily_loss_today_cents: int
    kill_switch_armed: bool
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
