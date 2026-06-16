"""Auth failure paths — missing token, invalid token, wrong scheme."""

from __future__ import annotations

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_protected_endpoint_requires_bearer(client) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"].startswith("AUTH_")
    assert body["error"]["traceId"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_protected_endpoint_rejects_garbage_token(client) -> None:
    resp = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"].startswith("AUTH_")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_protected_endpoint_rejects_wrong_scheme(client) -> None:
    resp = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Basic dXNlcjpwYXNz"}
    )
    assert resp.status_code == 401


@pytest.mark.unit
@pytest.mark.asyncio
async def test_404_returns_error_contract(client) -> None:
    resp = await client.get("/api/v1/this-does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    # We want our error envelope, not FastAPI's default {"detail": "..."}
    assert "error" in body
    assert body["error"]["code"].startswith("HTTP_")
