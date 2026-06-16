"""Signup happy-path + error path.

These hit the service layer which currently raises NotImplementedError —
test verifies the *error contract* shape, not the success path. Will be
flipped to the real assertions once `AuthService.signup` lands.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_signup_validation_rejects_short_password(client) -> None:
    """Pydantic should reject password shorter than 12 chars before service runs."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "user@example.com", "password": "short", "display_name": "U"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert "traceId" in body["error"]
    assert body["error"]["traceId"]  # non-empty


@pytest.mark.unit
@pytest.mark.asyncio
async def test_signup_validation_rejects_invalid_email(client) -> None:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "not-an-email", "password": "a-very-strong-pw-123!", "display_name": "U"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
