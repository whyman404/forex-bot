"""Strategy — catalog entry (read-only, seeded by Mnemosyne).

Schema: docs/database/schema.sql §4.5
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Strategy(Base, TimestampMixin):
    __tablename__ = "strategies"
    __table_args__ = (
        CheckConstraint(
            "code IN ('london_breakout','ny_killzone','ema_adx','ema_rsi','donchian','grid')",
            name="code",
        ),
        CheckConstraint("asset_class IN ('gold','btc')", name="asset_class"),
        CheckConstraint("risk_rating IN ('low','medium','high')", name="risk_rating"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    code: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    default_params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_rating: Mapped[str] = mapped_column(String(8), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
