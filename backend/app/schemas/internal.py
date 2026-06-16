"""Internal endpoint schemas — trading-engine ↔ backend.

Atlas Goro — these come from a *trusted* peer (Kairos engine). Still validate
shape; defense in depth. HMAC verifies provenance, schema verifies content.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class InternalSignal(BaseModel):
    strategy_instance_id: UUID
    ts: datetime
    direction: str = Field(pattern=r"^(long|short)$")
    price: Decimal
    sl: Decimal | None = None
    tp: Decimal | None = None
    reason: dict = Field(default_factory=dict)
    status: str = Field(default="generated")
    broker_order_id: str | None = None


class InternalTradeFill(BaseModel):
    strategy_instance_id: UUID
    broker_account_id: UUID
    signal_id: UUID | None = None
    symbol: str
    side: str = Field(pattern=r"^(buy|sell)$")
    lot_size: Decimal
    entry_price: Decimal
    entry_at: datetime
    exit_price: Decimal | None = None
    exit_at: datetime | None = None
    sl: Decimal | None = None
    tp: Decimal | None = None
    commission_cents: int = 0
    swap_cents: int = 0
    gross_pnl_cents: int | None = None
    net_pnl_cents: int | None = None
    status: str = Field(pattern=r"^(open|closed|canceled)$")
    broker_ticket: str | None = None


class InternalHealth(BaseModel):
    strategy_instance_id: UUID
    status: str
    open_positions: int = 0
    daily_loss_cents: int = 0
    kill_switch_armed: bool = True
    heartbeat_at: datetime


class InternalAck(BaseModel):
    accepted: bool = True
    id: UUID | None = None
