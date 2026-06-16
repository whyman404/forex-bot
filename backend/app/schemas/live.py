"""Live-trading + consent schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GateCheck(BaseModel):
    name: str
    passed: bool
    detail: str | None = None


class GateResult(BaseModel):
    """Returned from /strategy-instances/{id}/go-live preflight."""

    passed: bool
    failed_checks: list[GateCheck] = Field(default_factory=list)
    warnings: list[GateCheck] = Field(default_factory=list)
    checks: list[GateCheck] = Field(default_factory=list)


class LiveConsentRequest(BaseModel):
    strategy_code: str = Field(min_length=1, max_length=48)
    risk_acknowledged: bool
    version: str = Field(default="v1", max_length=16)


class LiveConsentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy_code: str
    version: str
    risk_acknowledged: bool
    created_at: datetime


class StrategyInstanceHealth(BaseModel):
    """Live OMS heartbeat snapshot."""

    instance_id: UUID
    status: str
    last_heartbeat_at: datetime | None = None
    last_signal_at: datetime | None = None
    open_positions: int = 0
    daily_loss_cents: int = 0
    kill_switch_armed: bool = True
