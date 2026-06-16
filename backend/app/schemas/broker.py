"""Broker account schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BrokerAccountCreateRequest(BaseModel):
    broker: Literal["exness_mt5", "binance", "bybit"] = Field(description="Supported broker codes")
    account_label: str = Field(min_length=1, max_length=120)
    # MT5-specific (when broker == 'exness_mt5')
    mt5_login: int | None = None
    mt5_server: str | None = None
    leverage: int | None = Field(default=None, gt=0, le=2000)
    account_currency: str | None = Field(default=None, min_length=3, max_length=3)
    # Broker-specific secret payload (login/password or API key/secret)
    credentials: dict = Field(description="Broker-specific secret payload (encrypted at rest)")


class BrokerAccountUpdateRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    credentials: dict | None = None


class BrokerAccountPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    broker: str
    account_label: str
    mt5_login: int | None = None
    mt5_server: str | None = None
    leverage: int | None = None
    account_currency: str | None = None
    is_active: bool
    last_sync_at: datetime | None = None
    created_at: datetime


class BrokerConnectionTestResponse(BaseModel):
    ok: bool
    broker: str
    account_id: UUID
    latency_ms: int | None = None
    detail: str | None = None
