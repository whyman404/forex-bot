"""Email queue producer + worker drain.

Atlas Goro — verifies:
  - EmailService.send() enqueues to Redis (or falls back to sync send).
  - render_and_send_now() routes to the configured provider.
  - ConsoleProvider always succeeds (default).
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-at-least-32-bytes-long!!")
os.environ.setdefault("ENCRYPTION_KEK_BASE64", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("EMAIL_PROVIDER", "console")


pytestmark = pytest.mark.unit


class _FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def lpush(self, key: str, value: Any) -> None:
        self.calls.append((key, value))

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_email_send_enqueues_when_redis_available() -> None:
    from app.services.email_service import EmailService

    fake = _FakeRedis()
    svc = EmailService()
    await svc.send(
        to="user@example.com",
        template="verify_email",
        context={"token": "abc", "display_name": "User"},
        redis=fake,
    )
    assert len(fake.calls) == 1
    key, raw = fake.calls[0]
    assert key == "email_queue"
    job = json.loads(raw)
    assert job["to"] == "user@example.com"
    assert job["template"] == "verify_email"
    assert job["context"]["token"] == "abc"


@pytest.mark.asyncio
async def test_console_provider_render_and_send() -> None:
    from app.services.email_service import render_and_send_now

    # Should not raise — console provider logs only.
    await render_and_send_now(
        to="user@example.com",
        template="welcome",
        context={"display_name": "User"},
    )


@pytest.mark.asyncio
async def test_unknown_template_falls_back_to_context_subject() -> None:
    from app.services.email_service import _template

    subject, text, html = _template(
        "no_such_template", {"subject": "Custom", "body": "Hello"}
    )
    assert subject == "Custom"
    assert "Hello" in text
