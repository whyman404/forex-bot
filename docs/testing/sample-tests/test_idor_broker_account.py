"""
test_idor_broker_account.py

Cross-tenant IDOR coverage on broker_accounts endpoints.

Why this test exists
--------------------
A broker_account contains credentials that can drain a user's brokerage account.
If user A can READ, MODIFY, DELETE, or POKE TEST-CONNECTION on user B's broker
account, we have a P0 security defect: real money exposure plus regulator-level
data-leak event.

The expected behavior is 404 (not 403) — we do NOT confirm existence of the
resource to an unauthorized caller, to prevent enumeration of broker_account ids
and user counts.

Owner: Themis Saori (in coordination with Argus Hayato)
"""
from __future__ import annotations

import re
from typing import Dict

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures: build two distinct authenticated users and one broker account per user.
#
# Assumes a conftest.py that exposes:
#   - `client: AsyncClient` bound to the FastAPI app
#   - `user_factory(...)` -> returns (user_dict, access_token)
# ---------------------------------------------------------------------------

async def _create_broker_account(client: AsyncClient, token: str) -> Dict:
    body = {
        "broker": "exness_mt5",
        "label": "primary",
        "credentials": {
            "account": "12345678",
            "server": "ExnessKE-MT5Real6",
            # sentinel value — we will assert it never echoes back
            "password": "TOP-SECRET-SENTINEL-DO-NOT-LEAK",
        },
    }
    res = await client.post(
        "/api/broker-accounts",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    # Sanity: response must not echo the credentials
    flat = res.text
    assert "TOP-SECRET-SENTINEL-DO-NOT-LEAK" not in flat, (
        "Broker password leaked in CREATE response. P0 secret exposure."
    )
    assert "credentials" not in data, "credentials field must not be returned on read"
    return data


@pytest.fixture
async def two_users(client: AsyncClient, user_factory):
    user_a, token_a = await user_factory(email="a@test.local", tier="pro", verified=True)
    user_b, token_b = await user_factory(email="b@test.local", tier="pro", verified=True)
    return {
        "a": {"user": user_a, "token": token_a},
        "b": {"user": user_b, "token": token_b},
    }


@pytest.fixture
async def broker_of_b(client: AsyncClient, two_users) -> Dict:
    return await _create_broker_account(client, two_users["b"]["token"])


# ---------------------------------------------------------------------------
# IDOR cases
# ---------------------------------------------------------------------------

class TestIDORBrokerAccount:
    """User A must never act on user B's broker_account."""

    async def test_owner_can_read(self, client, two_users, broker_of_b):
        """Sanity baseline: B can read B's own account."""
        res = await client.get(
            f"/api/broker-accounts/{broker_of_b['id']}",
            headers={"Authorization": f"Bearer {two_users['b']['token']}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == broker_of_b["id"]
        assert "credentials" not in body

    async def test_other_user_GET_returns_404_not_403(self, client, two_users, broker_of_b):
        res = await client.get(
            f"/api/broker-accounts/{broker_of_b['id']}",
            headers={"Authorization": f"Bearer {two_users['a']['token']}"},
        )
        assert res.status_code == 404, (
            f"Cross-tenant GET must be 404 to avoid existence enumeration; got {res.status_code}"
        )
        # Response must not echo any of B's data
        assert broker_of_b["id"] not in res.text or res.json().get("code", "") == "not_found"

    async def test_other_user_PATCH_returns_404(self, client, two_users, broker_of_b):
        res = await client.patch(
            f"/api/broker-accounts/{broker_of_b['id']}",
            json={"label": "hijacked"},
            headers={"Authorization": f"Bearer {two_users['a']['token']}"},
        )
        assert res.status_code == 404

        # Verify the row was untouched
        owner_view = await client.get(
            f"/api/broker-accounts/{broker_of_b['id']}",
            headers={"Authorization": f"Bearer {two_users['b']['token']}"},
        )
        assert owner_view.json()["label"] == "primary"

    async def test_other_user_DELETE_returns_404(self, client, two_users, broker_of_b):
        res = await client.delete(
            f"/api/broker-accounts/{broker_of_b['id']}",
            headers={"Authorization": f"Bearer {two_users['a']['token']}"},
        )
        assert res.status_code == 404

        # Row still exists for B
        owner_view = await client.get(
            f"/api/broker-accounts/{broker_of_b['id']}",
            headers={"Authorization": f"Bearer {two_users['b']['token']}"},
        )
        assert owner_view.status_code == 200

    async def test_other_user_test_connection_returns_404(self, client, two_users, broker_of_b):
        res = await client.post(
            f"/api/broker-accounts/{broker_of_b['id']}/test-connection",
            headers={"Authorization": f"Bearer {two_users['a']['token']}"},
        )
        assert res.status_code == 404, (
            "test-connection on someone else's account must NOT execute. Even leaking "
            "'connection failed' would tell the attacker the account exists."
        )

    async def test_other_user_list_does_not_include_foreign(self, client, two_users, broker_of_b):
        res = await client.get(
            "/api/broker-accounts",
            headers={"Authorization": f"Bearer {two_users['a']['token']}"},
        )
        assert res.status_code == 200
        ids = [a["id"] for a in res.json().get("items", [])]
        assert broker_of_b["id"] not in ids

    async def test_unauthenticated_returns_401_not_404(self, client, broker_of_b):
        res = await client.get(f"/api/broker-accounts/{broker_of_b['id']}")
        assert res.status_code == 401, (
            "Anonymous access must be 401 — we still hide existence behind auth."
        )

    @pytest.mark.parametrize("bad_id", [
        "not-a-uuid",
        "../../etc/passwd",
        "00000000-0000-0000-0000-000000000000",  # well-formed but does not exist
        "' OR 1=1 --",
    ])
    async def test_malformed_or_missing_id_does_not_500(self, client, two_users, bad_id):
        res = await client.get(
            f"/api/broker-accounts/{bad_id}",
            headers={"Authorization": f"Bearer {two_users['a']['token']}"},
        )
        assert res.status_code in (400, 404, 422), (
            f"Bad id must not cause 5xx; got {res.status_code}: {res.text}"
        )

    async def test_broker_credentials_never_appear_in_any_response(
        self, client, two_users, broker_of_b, caplog
    ):
        """
        Side check: across read/update endpoints accessible to the owner,
        the broker password sentinel must never round-trip out.
        """
        sentinel = "TOP-SECRET-SENTINEL-DO-NOT-LEAK"
        endpoints = [
            ("GET", f"/api/broker-accounts/{broker_of_b['id']}", None),
            ("GET", "/api/broker-accounts", None),
            ("POST", f"/api/broker-accounts/{broker_of_b['id']}/test-connection", {}),
            ("PATCH", f"/api/broker-accounts/{broker_of_b['id']}", {"label": "new-label"}),
        ]
        for method, url, body in endpoints:
            res = await client.request(
                method, url,
                json=body,
                headers={"Authorization": f"Bearer {two_users['b']['token']}"},
            )
            assert sentinel not in res.text, (
                f"Broker password leaked in response of {method} {url}"
            )
        # And never logged
        for rec in caplog.records:
            assert sentinel not in rec.getMessage(), (
                f"Broker password leaked into logs at {rec.levelname}: {rec.getMessage()}"
            )

    async def test_idor_via_user_id_query_param_is_ignored(self, client, two_users, broker_of_b):
        """A common mistake: endpoint accepts ?user_id= and trusts it.

        We verify any such parameter cannot expand access.
        """
        res = await client.get(
            f"/api/broker-accounts?user_id={two_users['b']['user']['id']}",
            headers={"Authorization": f"Bearer {two_users['a']['token']}"},
        )
        assert res.status_code in (200, 400, 422)
        if res.status_code == 200:
            ids = [a["id"] for a in res.json().get("items", [])]
            assert broker_of_b["id"] not in ids, (
                "user_id query param was honored without auth check — IDOR."
            )
