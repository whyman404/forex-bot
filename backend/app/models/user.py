"""User aggregate — auth identity + profile.

Schema source: docs/database/schema.sql §4.1 — users
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, LargeBinary, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user','admin')", name="role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    totp_secret: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default="TH")
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="user")

    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # ---- derived helpers (not in DB) ----

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def totp_enabled(self) -> bool:
        return self.totp_secret is not None

    @property
    def display_name(self) -> str | None:
        return self.full_name or None

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
