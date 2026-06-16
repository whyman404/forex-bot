"""Backtest — historical simulation job + result.

Schema: docs/database/schema.sql §4.7
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


from app.db.base import Base


class Backtest(Base):
    __tablename__ = "backtests"
    __table_args__ = (
        CheckConstraint(
            "timeframe IN ('M1','M5','M15','M30','H1','H4','D1')", name="timeframe"
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','failed')", name="status"
        ),
        CheckConstraint("end_date >= start_date", name="end_after_start"),
        CheckConstraint(
            "win_rate_pct IS NULL OR (win_rate_pct >= 0 AND win_rate_pct <= 100)",
            name="win_rate_pct",
        ),
        CheckConstraint(
            "total_trades IS NULL OR total_trades >= 0", name="total_trades"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        nullable=False,
    )

    asset_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="queued"
    )

    total_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    sharpe: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    sortino: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equity_curve_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    trades_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
