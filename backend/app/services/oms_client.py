"""OMS client — backend → trading-engine (Kairos).

Atlas Goro — every call to trading-engine is wrapped with:
  - hard timeout (5s connect, 10s total)
  - signed HMAC header for symmetry with inbound /internal/*
  - structured error → caller handles via try/except.

Offline-safe: if TRADING_ENGINE_URL is empty or stub, call is a no-op log.

HMAC contract (matches `trading-engine/live/internal_client.py`):

    canonical = f"{method}\n{path}\n{ts}\n{nonce}\n{body_sha256}"
    sig       = hmac_sha256(secret, canonical).hex()

    headers:
        X-Internal-Ts:    <unix-seconds>
        X-Internal-Nonce: <uuid4-hex>
        X-Internal-Sig:   <hex digest>

Older single-header form (`X-Internal-Signature` over raw body) is *also*
verified for backward-compat with the R2 stub. Once the engine is fully
on the new scheme we can drop the fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def sign_payload(secret: str, body: bytes) -> str:
    """[legacy] Canonical HMAC-SHA256 over raw body bytes → hex digest.

    Retained for back-compat. New code should use `sign_canonical`.
    """
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def sign_canonical(
    secret: str, method: str, path: str, body: bytes, *, ts: str | None = None, nonce: str | None = None
) -> tuple[str, str, str]:
    """Return (ts, nonce, sig_hex) for the canonical scheme used by Kairos."""
    ts = ts or str(int(time.time()))
    nonce = nonce or uuid.uuid4().hex
    body_sha = hashlib.sha256(body).hexdigest()
    canonical = f"{method}\n{path}\n{ts}\n{nonce}\n{body_sha}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return ts, nonce, sig


def verify_canonical(
    secret: str,
    method: str,
    path: str,
    body: bytes,
    ts: str,
    nonce: str,
    presented_sig: str,
    *,
    max_skew_sec: int = 60,
) -> bool:
    """Canonical verifier (constant-time). Rejects requests > max_skew_sec old."""
    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - ts_int) > max_skew_sec:
        return False
    body_sha = hashlib.sha256(body).hexdigest()
    canonical = f"{method}\n{path}\n{ts}\n{nonce}\n{body_sha}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (presented_sig or "").lower())


def verify_signature(secret: str, body: bytes, sig_hex: str) -> bool:
    """[legacy] Raw-body HMAC compare (back-compat with R2 stub).

    New callers should use `verify_canonical`.
    """
    expected = sign_payload(secret, body)
    return hmac.compare_digest(expected.lower(), (sig_hex or "").lower())


class OMSClient:
    def __init__(self) -> None:
        s = get_settings()
        self.base_url = s.trading_engine_url.rstrip("/")
        self.secret = s.internal_api_secret
        self.timeout = httpx.Timeout(10.0, connect=5.0)
        self.offline = not self.base_url or self.base_url.endswith("trading-engine:8200")

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.offline:
            logger.info("oms_offline_skip", path=path)
            return {"accepted": True, "offline": True}
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        headers = {"Content-Type": "application/json"}
        if self.secret:
            ts, nonce, sig = sign_canonical(self.secret, "POST", path, body)
            headers.update(
                {
                    "X-Internal-Ts": ts,
                    "X-Internal-Nonce": nonce,
                    "X-Internal-Sig": sig,
                }
            )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                r = await client.post(f"{self.base_url}{path}", content=body, headers=headers)
            except httpx.HTTPError as exc:
                logger.warning("oms_call_failed", path=path, err=str(exc))
                raise
            if r.status_code >= 400:
                logger.warning("oms_call_status", path=path, status=r.status_code)
                raise RuntimeError(f"OMS {path} → {r.status_code}: {r.text[:200]}")
            try:
                return r.json()
            except Exception:  # noqa: BLE001
                return {"ok": True}

    async def start_live(
        self,
        *,
        strategy_instance_id: UUID,
        broker_account_id: UUID,
        params: dict[str, Any],
        risk_limits: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._post(
            "/live/start",
            {
                "strategy_instance_id": str(strategy_instance_id),
                "broker_account_id": str(broker_account_id),
                "params": params,
                "risk_limits": risk_limits,
            },
        )

    async def stop_live(
        self, *, strategy_instance_id: UUID, close_positions: bool = True
    ) -> dict[str, Any]:
        return await self._post(
            "/live/stop",
            {
                "strategy_instance_id": str(strategy_instance_id),
                "close_positions": close_positions,
            },
        )

    async def close_open_positions(
        self, *, strategy_instance_id: UUID
    ) -> dict[str, Any]:
        return await self._post(
            "/live/close_positions",
            {"strategy_instance_id": str(strategy_instance_id)},
        )
