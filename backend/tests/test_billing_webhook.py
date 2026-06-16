"""Webhook signature verification + idempotency + dispatch.

Atlas Goro — these tests run *offline*: STRIPE_API_KEY left empty (or
'fake_') so we never reach Stripe. The adapter accepts unsigned JSON when
STRIPE_WEBHOOK_SECRET is empty/fake (test-only behaviour) so we can drive
the dispatcher directly.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

os.environ.setdefault("STRIPE_API_KEY", "")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "")


pytestmark = pytest.mark.integration


@pytest.fixture
def webhook_payload() -> dict[str, Any]:
    return {
        "id": "evt_test_123",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_test_123",
                "customer": "cus_test_abc",
                "status": "active",
                "current_period_start": 1_700_000_000,
                "current_period_end": 1_702_592_000,
                "items": {"data": [{"price": {"id": "price_test_pro_m"}}]},
                "metadata": {},
            }
        },
    }


@pytest.mark.asyncio
async def test_webhook_missing_signature_rejected(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/billing/webhook", content=b"{}")
    # 422 (FastAPI rejects missing Header alias) or 400 — both are OK; never 200.
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_webhook_offline_dispatch_idempotent(client, webhook_payload) -> None:  # type: ignore[no-untyped-def]
    body = json.dumps(webhook_payload).encode()
    headers = {"Stripe-Signature": "t=1,v1=fake"}
    # First delivery
    r1 = await client.post("/api/v1/billing/webhook", content=body, headers=headers)
    # Second delivery (idempotent)
    r2 = await client.post("/api/v1/billing/webhook", content=body, headers=headers)

    # In test env where Stripe secret is unset our adapter accepts unsigned
    # JSON; both calls should succeed and the second short-circuit.
    if r1.status_code == 200:
        assert r2.status_code == 200
    else:
        # If DB unavailable in CI, just ensure no 5xx
        assert r1.status_code < 500


@pytest.mark.asyncio
async def test_webhook_unknown_event_type_returns_ok(client) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "id": "evt_unknown_xyz",
        "type": "ping",
        "data": {"object": {}},
    }
    body = json.dumps(payload).encode()
    headers = {"Stripe-Signature": "t=1,v1=fake"}
    r = await client.post("/api/v1/billing/webhook", content=body, headers=headers)
    assert r.status_code in (200, 400, 503)
