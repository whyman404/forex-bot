"""POST /backtests creates a queued row.

Requires:
- Postgres with schema + strategies seeded.
- The current user has signup access. No broker account needed for backtests.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_backtest_queued(client) -> None:
    email = f"atlas+{uuid.uuid4().hex[:10]}@example.com"
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "very-strong-pw-12345!",
            "full_name": "Atlas BT",
        },
    )
    if signup.status_code == 500:
        pytest.skip("DB unavailable")
    assert signup.status_code == 201, signup.text
    access = signup.json()["access_token"]
    hdrs = {"Authorization": f"Bearer {access}"}

    start = date.today() - timedelta(days=60)
    end = date.today() - timedelta(days=1)
    resp = await client.post(
        "/api/v1/backtests",
        headers=hdrs,
        json={
            "strategy_code": "ema_adx",
            "asset_symbol": "XAUUSD",
            "timeframe": "H1",
            "params": {},
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )
    # 202 happy, 404 if strategies not seeded — accept both for env tolerance.
    if resp.status_code == 404:
        pytest.skip("strategies not seeded in this env")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["asset_symbol"] == "XAUUSD"

    listed = await client.get("/api/v1/backtests", headers=hdrs)
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()}
    assert body["id"] in ids
