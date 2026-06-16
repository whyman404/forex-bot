"""Health endpoint smoke tests."""

from __future__ import annotations

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_healthz_returns_ok(client) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.unit
@pytest.mark.asyncio
async def test_healthz_echoes_request_id(client) -> None:
    given = "test-request-id-123"
    resp = await client.get("/healthz", headers={"X-Request-Id": given})
    assert resp.status_code == 200
    assert resp.headers["X-Request-Id"] == given


@pytest.mark.unit
@pytest.mark.asyncio
async def test_healthz_mints_request_id_when_missing(client) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    # UUID4 string ≈ 36 chars
    assert len(resp.headers["X-Request-Id"]) >= 8
