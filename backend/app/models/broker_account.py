"""BrokerAccount — user's connected broker (Exness MT5, Binance, ...).

Schema: docs/database/schema.sql §4.4
Encryption: ADR-005 — envelope (KEK-wrapped DEK + GCM payload).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BrokerAccount(Base, TimestampMixin):
    __tablename__ = "broker_accounts"
    __table_args__ = (
        CheckConstraint(
            "broker IN ('exness_mt5','binance','bybit')", name="broker"
        ),
        CheckConstraint(
            "leverage IS NULL OR (leverage > 0 AND leverage <= 2000)", name="leverage"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    broker: Mapped[str] = mapped_column(String(24), nullable=False)
    account_label: Mapped[str] = mapped_column(Text, nullable=False)

    mt5_login: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mt5_server: Mapped[str | None] = mapped_column(Text, nullable=True)

    credentials_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credentials_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credentials_key_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )

    leverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    balance_cached_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
