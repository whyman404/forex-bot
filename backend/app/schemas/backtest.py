"""Backtest schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BacktestCreateRequest(BaseModel):
    strategy_code: str = Field(min_length=1, max_length=64)
    asset_symbol: str = Field(min_length=1, max_length=16)
    timeframe: Literal["M1", "M5", "M15", "M30", "H1", "H4", "D1"] = "H1"
    params: dict[str, Any] = Field(default_factory=dict)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _range_ok(self) -> "BacktestCreateRequest":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class BacktestPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy_id: UUID
    asset_symbol: str
    timeframe: str
    status: Literal["queued", "running", "completed", "failed"]
    start_date: date
    end_date: date

    total_return_pct: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    sharpe: Decimal | None = None
    sortino: Decimal | None = None
    profit_factor: Decimal | None = None
    win_rate_pct: Decimal | None = None
    total_trades: int | None = None
    equity_curve_url: str | None = None

    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class EquityPoint(BaseModel):
    t: datetime
    equity: Decimal


class EquityCurveResponse(BaseModel):
    backtest_id: UUID
    points: list[EquityPoint]
