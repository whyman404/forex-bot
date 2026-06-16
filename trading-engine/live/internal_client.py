"""HMAC-signed client for backend /internal/* calls.

Why HMAC instead of a token?
- Replay protection — every request has a fresh timestamp + nonce.
- The backend can reject any request older than 60s.
- A token leak still requires the secret to forge new requests.

Signature scheme (matches Atlas's expectation):

    canonical = f"{method}\n{path}\n{ts}\n{nonce}\n{body_sha256}"
    sig       = hmac.new(secret, canonical.encode(), sha256).hexdigest()

Sent as headers:

    X-Internal-Ts:     1717000000
    X-Internal-Nonce:  uuid4-hex
    X-Internal-Sig:    <sig>
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class InternalClient:
    """Signed POSTer for `/internal/*` endpoints on the backend."""

    def __init__(
        self,
        base_url: str | None = None,
        secret: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("BACKEND_INTERNAL_URL", "http://backend:8000")).rstrip("/")
        self.secret = secret or os.getenv("INTERNAL_API_SECRET", "")
        if not self.secret:
            # We log but don't crash — engine should still start in dev mode.
            logger.warning("internal_client.no_secret")
        self.timeout = timeout
        self._http = httpx.Client(timeout=timeout)

    # ------------------------------------------------------------------
    def _sign(self, method: str, path: str, body: bytes) -> dict[str, str]:
        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        body_sha = hashlib.sha256(body).hexdigest()
        canonical = f"{method}\n{path}\n{ts}\n{nonce}\n{body_sha}".encode("utf-8")
        sig = hmac.new(self.secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        return {
            "X-Internal-Ts": ts,
            "X-Internal-Nonce": nonce,
            "X-Internal-Sig": sig,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict[str, Any]) -> bool:
        body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
        headers = self._sign("POST", path, body)
        try:
            r = self._http.post(self.base_url + path, content=body, headers=headers)
        except httpx.HTTPError as e:
            logger.warning("internal.post_failed", path=path, error=str(e))
            return False
        if r.status_code >= 400:
            logger.warning(
                "internal.post_rejected",
                path=path,
                status=r.status_code,
                body=r.text[:200],
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Public — what the LiveEngine calls
    # ------------------------------------------------------------------
    def emit_signal(
        self,
        strategy_instance_id: str,
        symbol: str,
        timeframe: str,
        direction: int,
        entry: float,
        sl: float,
        tp: float,
        reason: str,
        ts: float,
    ) -> bool:
        return self._post(
            "/internal/signals",
            {
                "strategy_instance_id": strategy_instance_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": direction,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "reason": reason,
                "ts": ts,
            },
        )

    def emit_trade(
        self,
        strategy_instance_id: str,
        broker_account_id: str,
        ticket: int,
        symbol: str,
        side: str,
        lot: float,
        fill_price: float,
        sl: float | None,
        tp: float | None,
        pnl: float | None,
        opened_at: float,
        closed_at: float | None,
        comment: str = "",
    ) -> bool:
        return self._post(
            "/internal/trades",
            {
                "strategy_instance_id": strategy_instance_id,
                "broker_account_id": broker_account_id,
                "ticket": ticket,
                "symbol": symbol,
                "side": side,
                "lot": lot,
                "fill_price": fill_price,
                "sl": sl,
                "tp": tp,
                "pnl": pnl,
                "opened_at": opened_at,
                "closed_at": closed_at,
                "comment": comment,
            },
        )

    def emit_health(
        self,
        strategy_instance_id: str,
        status: str,
        details: dict[str, Any],
    ) -> bool:
        return self._post(
            "/internal/health",
            {
                "strategy_instance_id": strategy_instance_id,
                "status": status,
                "details": details,
                "ts": time.time(),
            },
        )

    def close(self) -> None:
        self._http.close()


def verify_signature(
    method: str,
    path: str,
    body: bytes,
    ts: str,
    nonce: str,
    presented_sig: str,
    secret: str,
    max_skew_sec: int = 60,
) -> bool:
    """Server-side helper — used by tests + the backend's /internal/* receiver.

    Constant-time comparison. Rejects requests older than `max_skew_sec`.
    """
    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - ts_int) > max_skew_sec:
        return False
    body_sha = hashlib.sha256(body).hexdigest()
    canonical = f"{method}\n{path}\n{ts}\n{nonce}\n{body_sha}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, presented_sig)
