"""
mt5-bridge-stub server
======================

Canned MT5 responses for local development. Mimics the real MT5 bridge HTTP
API (which runs on a Windows VPS in production) so frontend + backend can
exercise the trading flow without needing a Windows machine.

Endpoints (subset of real bridge contract):
  GET  /healthz                          → {"ok": true}
  GET  /account                          → mock account
  GET  /symbols                          → list of supported symbols
  GET  /quote?symbol=XAUUSD              → bid/ask
  POST /order                            → simulated order ack
  GET  /positions                        → list of open positions
  POST /position/close                   → close ack
  GET  /history?from=...&to=...          → history closed trades

Env:
  BRIDGE_PORT (default 8500)
  STUB_MODE   canned | random  (default canned)
  LOG_LEVEL   INFO | DEBUG     (default INFO)

This file MUST stay zero-dependency (stdlib only) so the image is tiny and
fast to start. Do NOT import requests / fastapi / etc.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

PORT = int(os.environ.get("BRIDGE_PORT", "8500"))
STUB_MODE = os.environ.get("STUB_MODE", "canned").lower()
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("mt5-bridge-stub")

# --------------------------------------------------------------------------- #
# Canned data
# --------------------------------------------------------------------------- #

ACCOUNT_CANNED: dict[str, Any] = {
    "login": 12345678,
    "name": "Stub Demo",
    "server": "ExnessKE-MT5Real8",
    "currency": "USD",
    "leverage": 200,
    "balance": 10000.00,
    "equity": 10025.50,
    "margin": 250.00,
    "margin_free": 9775.50,
    "margin_level": 4010.20,
}

SYMBOLS_CANNED: list[dict[str, Any]] = [
    {"symbol": "XAUUSD",  "digits": 2, "point": 0.01,    "min_lot": 0.01, "max_lot": 100, "step": 0.01},
    {"symbol": "BTCUSD",  "digits": 2, "point": 0.01,    "min_lot": 0.01, "max_lot": 100, "step": 0.01},
    {"symbol": "EURUSD",  "digits": 5, "point": 0.00001, "min_lot": 0.01, "max_lot": 100, "step": 0.01},
    {"symbol": "GBPUSD",  "digits": 5, "point": 0.00001, "min_lot": 0.01, "max_lot": 100, "step": 0.01},
    {"symbol": "USDJPY",  "digits": 3, "point": 0.001,   "min_lot": 0.01, "max_lot": 100, "step": 0.01},
]

QUOTE_BASE: dict[str, float] = {
    "XAUUSD": 2350.50,
    "BTCUSD": 68500.0,
    "EURUSD": 1.0875,
    "GBPUSD": 1.2640,
    "USDJPY": 156.20,
}

# Position store — in-memory, lifetime = container lifetime
POSITIONS: dict[int, dict[str, Any]] = {}
_TICKET_COUNTER = 100000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jitter(base: float, pct: float = 0.001) -> float:
    """Small random walk for `random` mode."""
    return round(base * (1 + random.uniform(-pct, pct)), 5)


def _next_ticket() -> int:
    global _TICKET_COUNTER
    _TICKET_COUNTER += 1
    return _TICKET_COUNTER


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #

class Handler(BaseHTTPRequestHandler):
    server_version = "mt5-bridge-stub/0.1"

    # ---- helpers ----

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Stub-Mode", STUB_MODE)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        log.info("%s - %s", self.address_string(), fmt % args)

    # ---- routes ----

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        route = parsed.path.rstrip("/") or "/"

        if route == "/healthz":
            return self._json(200, {"ok": True, "mode": STUB_MODE, "ts": _now_iso()})

        if route == "/account":
            return self._json(200, ACCOUNT_CANNED)

        if route == "/symbols":
            return self._json(200, {"symbols": SYMBOLS_CANNED})

        if route == "/quote":
            symbol = params.get("symbol", "XAUUSD").upper()
            base = QUOTE_BASE.get(symbol)
            if base is None:
                return self._json(404, {"error": f"unknown symbol: {symbol}"})
            spread = 0.20 if symbol == "XAUUSD" else 0.0002 * base
            bid = _jitter(base) if STUB_MODE == "random" else base
            ask = round(bid + spread, 5)
            return self._json(200, {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "time": _now_iso(),
            })

        if route == "/positions":
            return self._json(200, {"positions": list(POSITIONS.values())})

        if route == "/history":
            return self._json(200, {
                "history": [
                    {
                        "ticket": 99001,
                        "symbol": "XAUUSD",
                        "type": "buy",
                        "volume": 0.10,
                        "price_open": 2348.00,
                        "price_close": 2351.50,
                        "profit": 35.00,
                        "time_open": "2026-06-14T08:30:00+00:00",
                        "time_close": "2026-06-14T11:15:00+00:00",
                    },
                ],
            })

        return self._json(404, {"error": "not found", "path": route})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        body = self._read_json()

        if route == "/order":
            symbol = body.get("symbol", "XAUUSD").upper()
            side = body.get("side", "buy").lower()
            volume = float(body.get("volume", 0.01))
            sl = body.get("sl")
            tp = body.get("tp")
            base = QUOTE_BASE.get(symbol, 1.0)
            price = round(base + (0.10 if side == "buy" else -0.10), 5)
            ticket = _next_ticket()

            POSITIONS[ticket] = {
                "ticket": ticket,
                "symbol": symbol,
                "type": side,
                "volume": volume,
                "price_open": price,
                "sl": sl,
                "tp": tp,
                "swap": 0.0,
                "profit": 0.0,
                "time": _now_iso(),
                "comment": body.get("comment", "stub"),
            }
            return self._json(200, {
                "ok": True,
                "ticket": ticket,
                "order_id": str(uuid.uuid4()),
                "price": price,
                "retcode": 10009,  # TRADE_RETCODE_DONE
                "deal": ticket + 50000,
            })

        if route == "/position/close":
            ticket = int(body.get("ticket", 0))
            pos = POSITIONS.pop(ticket, None)
            if not pos:
                return self._json(404, {"error": "position not found", "ticket": ticket})
            return self._json(200, {
                "ok": True,
                "ticket": ticket,
                "close_price": pos["price_open"] + random.uniform(-1, 1),
                "profit": round(random.uniform(-20, 30), 2),
                "retcode": 10009,
            })

        if route == "/position/modify":
            ticket = int(body.get("ticket", 0))
            pos = POSITIONS.get(ticket)
            if not pos:
                return self._json(404, {"error": "position not found", "ticket": ticket})
            if "sl" in body:
                pos["sl"] = body["sl"]
            if "tp" in body:
                pos["tp"] = body["tp"]
            return self._json(200, {"ok": True, "ticket": ticket})

        return self._json(404, {"error": "not found", "path": route})


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    log.info(
        "mt5-bridge-stub starting on :%s (mode=%s) — canned MT5 responses for dev",
        PORT, STUB_MODE,
    )
    log.info("In production, swap this with the Windows VPS bridge — see docs/deployment/deployment-architecture.md")

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
