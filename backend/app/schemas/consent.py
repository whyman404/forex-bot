"""User consent schemas — TOS / privacy / marketing (PDPA/GDPR)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ConsentKind = Literal["tos", "privacy", "marketing", "data_processing"]


class ConsentRequest(BaseModel):
    kind: ConsentKind
    version: str = Field(min_length=1, max_length=16)
    accepted: bool


class ConsentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: ConsentKind
    version: str
    accepted: bool
    created_at: datetime
