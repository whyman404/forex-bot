"""SQLAlchemy declarative base + naming convention.

Naming convention so Alembic autogenerate produces deterministic constraint names —
critical for diffable migrations and rollbacks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# PostgreSQL identifier max is 63 chars — keep our keys shorter than that.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = metadata_obj

    # Keep type_annotation_map consistent across the codebase.
    type_annotation_map: dict[Any, Any] = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """Standard `created_at` + `updated_at` for every aggregate root.

    `server_default=now()` and `server_onupdate` rely on the DB triggers
    Mnemosyne installs (set_updated_at trigger). We mirror with onupdate=now()
    too so behavior is consistent if the trigger is absent (e.g. SQLite in tests).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        server_onupdate=text("now()"),
        nullable=False,
    )
