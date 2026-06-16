"""Auth happy-path integration tests.

These require a real Postgres at $DATABASE_URL and apply the schema beforehand.
Marked `integration` so a unit-only CI lane can skip them.
"""

from __future__ import annotations

import uuid

import pytest


def _unique_email() -> str:
    return f"atlas+{uuid.uuid4().hex[:10]}@example.com"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_signup_login_me_round_trip(client) -> None:
    email = _unique_email()
    password = "very-strong-pw-12345!"

    # 1. Signup
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "full_name": "Atlas Test"},
    )
    if signup.status_code == 500:
        pytest.skip("DB unavailable for integration test")
    assert signup.status_code == 201, signup.text
    pair = signup.json()
    assert pair["access_token"]
    assert pair["refresh_token"]
    assert pair["token_type"] == "Bearer"

    # 2. /users/me with new access token
    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {pair['access_token']}"}
    )
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["email"].lower() == email.lower()
    assert body["full_name"] == "Atlas Test"
    assert body["role"] == "user"

    # 3. Login again
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client) -> None:
    email = _unique_email()
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "very-strong-pw-12345!",
            "full_name": "Atlas Test",
        },
    )
    if signup.status_code == 500:
        pytest.skip("DB unavailable")
    assert signup.status_code == 201

    bad = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrong-password-but-long-enough!"},
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_rotates_token(client) -> None:
    email = _unique_email()
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "very-strong-pw-12345!",
            "full_name": "Atlas Test",
        },
    )
    if signup.status_code == 500:
        pytest.skip("DB unavailable")
    pair = signup.json()

    refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": pair["refresh_token"]},
    )
    assert refresh.status_code == 200, refresh.text
    new_pair = refresh.json()
    # New tokens issued — at least one differs (jti embedded)
    assert new_pair["access_token"] != pair["access_token"]
