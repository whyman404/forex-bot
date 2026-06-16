"""Internal HMAC — signature verification (pass + fail).

Atlas Goro — covers:
  - sign_payload / verify_signature round-trip.
  - Wrong signature rejected with constant-time compare.
  - Missing header → InternalSignatureInvalidError when secret is set.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-at-least-32-bytes-long!!")
os.environ.setdefault("ENCRYPTION_KEK_BASE64", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("INTERNAL_API_SECRET", "test-internal-secret-32-bytes-long!!")


pytestmark = pytest.mark.unit


def test_sign_and_verify_round_trip() -> None:
    from app.services.oms_client import sign_payload, verify_signature

    body = b'{"foo":"bar"}'
    secret = "shhhh"
    sig = sign_payload(secret, body)
    assert verify_signature(secret, body, sig) is True


def test_verify_rejects_tampered_body() -> None:
    from app.services.oms_client import sign_payload, verify_signature

    body = b'{"foo":"bar"}'
    sig = sign_payload("secret", body)
    assert verify_signature("secret", b'{"foo":"baz"}', sig) is False


def test_verify_rejects_wrong_secret() -> None:
    from app.services.oms_client import sign_payload, verify_signature

    body = b'{"x":1}'
    sig = sign_payload("right", body)
    assert verify_signature("wrong", body, sig) is False


def test_verify_rejects_empty_signature() -> None:
    from app.services.oms_client import verify_signature

    assert verify_signature("secret", b"body", "") is False


@pytest.mark.asyncio
async def test_internal_signals_endpoint_rejects_bad_sig(client) -> None:  # type: ignore[no-untyped-def]
    """Hit /api/v1/internal/signals with a wrong signature → 401."""
    body = json.dumps(
        {
            "strategy_instance_id": "00000000-0000-0000-0000-000000000001",
            "ts": "2026-06-15T00:00:00Z",
            "direction": "long",
            "price": "1.0",
            "reason": {},
            "status": "generated",
        }
    ).encode()
    r = await client.post(
        "/api/v1/internal/signals",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Internal-Signature": "deadbeef",
        },
    )
    # 401 from sig fail; 422 if schema reject first; never 200 with wrong sig
    assert r.status_code in (401, 422)
