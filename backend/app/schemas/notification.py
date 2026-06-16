"""Notification schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationPublic(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str
    is_read: bool
    created_at: datetime
