"""StrategyInstance — a user-deployed strategy on a broker account.

Schema: docs/database/schema.sql §4.6
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class StrategyInstance(Base, TimestampMixin):
    __tablename__ = "strategy_instances"
    __table_args__ = (
        CheckConstraint(
            "status IN ('paper','live','stopped','killed')", name="status"
        ),
        CheckConstraint(
            "risk_percent >= 0 AND risk_percent <= 10", name="risk_percent"
        ),
        CheckConstraint("max_daily_loss_cents >= 0", name="max_daily_loss_cents"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategies.id", ondelete="RESTRICT"), nullable=False
    )

    label: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    max_daily_loss_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    daily_loss_today_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    kill_switch_armed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    last_signal_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    live_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
