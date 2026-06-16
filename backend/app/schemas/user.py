"""User schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field


class UserPublic(BaseModel):
    """Returned for /users/me. Never include password_hash or totp_secret.

    `from_attributes=True` lets us validate directly against the ORM `User`
    object. `is_email_verified`, `totp_enabled`, `is_admin`, `display_name`
    are read from the matching ORM @property methods (also derived computed
    fields, so they survive a `model_validate(dict)` path too).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    country: str
    role: str
    is_email_verified: bool
    totp_enabled: bool
    created_at: datetime

    # ---- Computed fields are SERIALIZED (unlike plain @property). ----
    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_name(self) -> str:
        return self.full_name

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
