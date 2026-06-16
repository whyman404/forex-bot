"""mt5-supervisor.py — runs on the Windows VPS.

Responsibilities
----------------
1. Manage the MT5 terminal process lifecycle (boot if down, watchdog).
2. Maintain a WSS connection to the backend.
3. Heartbeat every N seconds (backend uses this for the kill switch).
4. Accept order intents from backend, route to MT5, return fills.
5. Stream account state (positions, equity, balance) to backend.
6. Expose Prometheus metrics on :9101.

Design notes
------------
* Single-process, async. asyncio + websockets, blocking MT5 calls run in
  a thread pool so they never block the event loop.
* Idempotency: every order intent carries a client_order_id. Duplicate
  intents return the previous result instead of double-firing.
* Graceful degradation: if the broker connection drops, we still reply
  with structured errors so the backend can surface them; we do not
  silently swallow.
* mTLS / shared secret: WSS connection authenticates with HMAC over a
  challenge from the backend. Secret is rotated quarterly.

This file is the only thing Hestia hand-edits on the Windows host. Keep
it boring.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
import websockets
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    import MetaTrader5 as mt5  # type: ignore[import-untyped]
except ImportError:
    # Allow the file to be imported on non-Windows for syntax checks; the
    # actual `main()` will hard-fail outside Windows.
    mt5 = None  # type: ignore[assignment]


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
class Settings(BaseSettings):
    backend_wss_url: str = "wss://api.forex-bot.app/ws/mt5-supervisor"
    supervisor_id: str = "mt5-vps-01"
    supervisor_shared_secret: str = Field(default=..., description="HMAC secret")
    mt5_login: int = Field(default=..., description="Broker login")
    mt5_password: str = Field(default=..., description="Broker password")
    mt5_server: str = "Exness-MT5Real8"
    mt5_terminal_path: str = r"C:\forex-bot\mt5\terminal64.exe"

    heartbeat_interval: int = 10
    reconnect_backoff_max: int = 60
    prometheus_port: int = 9101
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level)
        ),
    )


log = structlog.get_logger("mt5-supervisor")


# ----------------------------------------------------------------------------
# Prometheus
# ----------------------------------------------------------------------------
M_HEARTBEAT = Gauge(
    "mt5_supervisor_last_heartbeat_timestamp_seconds",
    "Unix timestamp of the most recent heartbeat acked by backend.",
)
M_BROKER_CONNECTED = Gauge(
    "mt5_broker_connected",
    "1 if MT5 terminal reports connection to broker, else 0.",
)
M_ORDERS_TOTAL = Counter(
    "mt5_orders_total",
    "Order intents routed to MT5 by result.",
    ["result"],  # accepted, rejected, error
)
M_ORDER_LATENCY = Histogram(
    "mt5_order_latency_seconds",
    "Wall-clock between intent received and fill returned.",
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
)
M_WSS_RECONNECTS = Counter(
    "mt5_supervisor_wss_reconnects_total",
    "Number of WSS reconnect attempts.",
)
M_MT5_RESTARTS = Counter(
    "mt5_supervisor_mt5_restarts_total",
    "Number of times we restarted the MT5 terminal.",
)


# ----------------------------------------------------------------------------
# State
# ----------------------------------------------------------------------------
@dataclass
class SupervisorState:
    settings: Settings
    executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=4)
    )
    # client_order_id → response payload (idempotency cache)
    order_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)


# ----------------------------------------------------------------------------
# MT5 helpers (blocking — run in executor)
# ----------------------------------------------------------------------------
def mt5_initialize(settings: Settings) -> bool:
    assert mt5 is not None, "MetaTrader5 only runs on Windows"
    if not mt5.initialize(
        path=settings.mt5_terminal_path,
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    ):
        err = mt5.last_error()
        log.error("mt5.initialize failed", error=err)
        return False
    return True


def mt5_is_connected() -> bool:
    assert mt5 is not None
    info = mt5.terminal_info()
    if info is None:
        return False
    return bool(info.connected)


def mt5_account_snapshot() -> dict[str, Any]:
    assert mt5 is not None
    info = mt5.account_info()
    if info is None:
        return {}
    return {
        "login": info.login,
        "balance": info.balance,
        "equity": info.equity,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "currency": info.currency,
    }


def mt5_positions() -> list[dict[str, Any]]:
    assert mt5 is not None
    poss = mt5.positions_get() or []
    return [
        {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": p.type,
            "volume": p.volume,
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "profit": p.profit,
        }
        for p in poss
    ]


def mt5_send_order(intent: dict[str, Any]) -> dict[str, Any]:
    """Translate an order intent into MT5's order_send schema."""
    assert mt5 is not None
    symbol = intent["symbol"]
    if not mt5.symbol_select(symbol, True):
        return {"ok": False, "error": f"symbol_select failed for {symbol}"}

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(intent["volume"]),
        "type": mt5.ORDER_TYPE_BUY if intent["side"] == "buy" else mt5.ORDER_TYPE_SELL,
        "deviation": int(intent.get("deviation", 20)),
        "magic": int(intent.get("magic", 20260614)),
        "comment": intent.get("comment", "forex-bot"),
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    if "stop_loss" in intent:
        request["sl"] = float(intent["stop_loss"])
    if "take_profit" in intent:
        request["tp"] = float(intent["take_profit"])

    result = mt5.order_send(request)
    if result is None:
        return {"ok": False, "error": "order_send returned None", "last_error": mt5.last_error()}
    return {
        "ok": result.retcode == mt5.TRADE_RETCODE_DONE,
        "retcode": result.retcode,
        "deal": result.deal,
        "order": result.order,
        "price": result.price,
        "volume": result.volume,
        "comment": result.comment,
    }


# ----------------------------------------------------------------------------
# WSS client + main loop
# ----------------------------------------------------------------------------
def _sign(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def _do_handshake(ws: websockets.WebSocketClientProtocol, state: SupervisorState) -> None:
    """Server sends a challenge; we reply with HMAC + supervisor_id."""
    raw = await ws.recv()
    challenge = json.loads(raw)["challenge"]
    sig = _sign(state.settings.supervisor_shared_secret, challenge.encode())
    await ws.send(json.dumps({
        "type": "auth",
        "supervisor_id": state.settings.supervisor_id,
        "signature": sig,
    }))
    ack = json.loads(await ws.recv())
    if ack.get("type") != "auth_ok":
        raise RuntimeError(f"auth rejected: {ack}")
    log.info("authenticated", supervisor_id=state.settings.supervisor_id)


async def _heartbeat_loop(ws: websockets.WebSocketClientProtocol, state: SupervisorState) -> None:
    loop = asyncio.get_running_loop()
    while not state.stop_event.is_set():
        try:
            connected = await loop.run_in_executor(state.executor, mt5_is_connected)
            M_BROKER_CONNECTED.set(1 if connected else 0)
            account = await loop.run_in_executor(state.executor, mt5_account_snapshot)
            payload = {
                "type": "heartbeat",
                "ts": time.time(),
                "broker_connected": connected,
                "account": account,
                "supervisor_id": state.settings.supervisor_id,
            }
            await ws.send(json.dumps(payload))
            M_HEARTBEAT.set(time.time())
        except (websockets.ConnectionClosed, RuntimeError):
            raise
        except Exception as e:  # never let heartbeat die on a transient error
            log.warning("heartbeat error", error=str(e))
        await asyncio.sleep(state.settings.heartbeat_interval)


async def _command_loop(ws: websockets.WebSocketClientProtocol, state: SupervisorState) -> None:
    loop = asyncio.get_running_loop()
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("non-json frame", raw=raw[:200])
            continue
        kind = msg.get("type")

        if kind == "order_intent":
            client_order_id = msg["client_order_id"]
            if client_order_id in state.order_cache:
                response = state.order_cache[client_order_id]
                log.info("idempotent replay", client_order_id=client_order_id)
            else:
                start = time.perf_counter()
                response = await loop.run_in_executor(
                    state.executor, mt5_send_order, msg["intent"]
                )
                M_ORDER_LATENCY.observe(time.perf_counter() - start)
                M_ORDERS_TOTAL.labels(
                    result="accepted" if response.get("ok") else "rejected"
                ).inc()
                state.order_cache[client_order_id] = response
            await ws.send(json.dumps({
                "type": "order_result",
                "client_order_id": client_order_id,
                "result": response,
            }))

        elif kind == "positions_request":
            positions = await loop.run_in_executor(state.executor, mt5_positions)
            await ws.send(json.dumps({
                "type": "positions_snapshot",
                "request_id": msg.get("request_id"),
                "positions": positions,
            }))

        elif kind == "ping":
            await ws.send(json.dumps({"type": "pong", "ts": time.time()}))

        else:
            log.warning("unknown message type", type=kind)


async def _run_once(state: SupervisorState) -> None:
    url = state.settings.backend_wss_url
    log.info("connecting", url=url)
    async with websockets.connect(
        url,
        ping_interval=20,
        ping_timeout=20,
        max_size=2**20,
    ) as ws:
        await _do_handshake(ws, state)
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_heartbeat_loop(ws, state))
            tg.create_task(_command_loop(ws, state))


async def run(state: SupervisorState) -> None:
    """Outer loop: keep MT5 + WSS alive forever (until stop_event)."""
    loop = asyncio.get_running_loop()
    # First, make sure MT5 is up.
    if not await loop.run_in_executor(state.executor, mt5_initialize, state.settings):
        log.error("initial mt5.initialize failed — exiting; service manager will retry")
        sys.exit(2)

    backoff = 1
    while not state.stop_event.is_set():
        try:
            await _run_once(state)
            backoff = 1
        except (websockets.ConnectionClosed, OSError, RuntimeError) as e:
            M_WSS_RECONNECTS.inc()
            log.warning("wss connection lost", error=str(e), backoff=backoff)
            try:
                await asyncio.wait_for(state.stop_event.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, state.settings.reconnect_backoff_max)
            # Double check MT5 is still connected; if not, try to restart.
            if not await loop.run_in_executor(state.executor, mt5_is_connected):
                log.warning("mt5 disconnected — re-initialising")
                M_MT5_RESTARTS.inc()
                await loop.run_in_executor(state.executor, mt5_initialize, state.settings)


def _install_signal_handlers(state: SupervisorState) -> None:
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        log.info("shutdown signal received")
        state.stop_event.set()

    # SIGINT works on Windows for Ctrl+C. NSSM sends SIGTERM-equivalent.
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            # Windows asyncio loop doesn't always support add_signal_handler.
            signal.signal(sig, lambda *_a: _stop())


async def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level)
    if mt5 is None:
        log.error("MetaTrader5 package not importable — this script must run on Windows")
        sys.exit(1)
    start_http_server(settings.prometheus_port)
    log.info("prometheus exporter started", port=settings.prometheus_port)
    state = SupervisorState(settings=settings)
    _install_signal_handlers(state)
    try:
        await run(state)
    finally:
        log.info("shutting down")
        assert mt5 is not None
        mt5.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
