"""FastAPI bridge service.

Endpoints (all require Bearer auth except /healthz):

    POST /connect            { server, login, password }
    POST /disconnect
    GET  /account
    GET  /symbols
    GET  /quote/{symbol}
    GET  /positions          ?symbol=...
    POST /order              { symbol, side, lot, sl, tp, comment, magic }
    POST /order/pending      { symbol, side, kind, lot, price, sl, tp, comment, magic }
    POST /position/close     { ticket }
    POST /position/modify    { ticket, sl, tp }
    GET  /history            ?from=<ts>&to=<ts>
    GET  /healthz            (no auth)
    WS   /stream             (Bearer subprotocol) — pushes ticks + position diffs

Boot
----
    uvicorn mt5_bridge.server:app --host 0.0.0.0 --port 8500

`run()` is the entrypoint used by NSSM / install.bat — it reads
BridgeConfig from env and starts uvicorn programmatically.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field

from mt5_bridge.auth import make_token_dependency
from mt5_bridge.config import BridgeConfig
from mt5_bridge.mt5_client import MT5Client
from mt5_bridge.safety import OrderIntent, SafetyChecker, SafetyViolation

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class ConnectRequest(BaseModel):
    server: str
    login: int
    password: str = Field(..., description="MT5 investor or trader password")


class OrderRequest(BaseModel):
    symbol: str
    side: str  # buy | sell
    lot: float = Field(..., gt=0)
    sl: float | None = None
    tp: float | None = None
    comment: str = ""
    magic: int = 0
    # Reference price used only for SL/TP-side consistency check. Optional.
    reference_price: float | None = None


class PendingOrderRequest(OrderRequest):
    kind: str  # "limit" | "stop"
    price: float = Field(..., gt=0)


class CloseRequest(BaseModel):
    ticket: int


class ModifyRequest(BaseModel):
    ticket: int
    sl: float | None = None
    tp: float | None = None


# ---------------------------------------------------------------------------
# WebSocket broker for streaming ticks / position updates
# ---------------------------------------------------------------------------
class StreamHub:
    """Fan-out hub for /stream subscribers."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        # Snapshot to avoid mutation during iteration.
        async with self._lock:
            targets = list(self._clients)
        text = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app(config: BridgeConfig | None = None) -> FastAPI:
    """Build the FastAPI app. Config is loaded from env when omitted."""
    config = config or BridgeConfig.from_env()
    client = MT5Client(mt5_path=config.mt5_path)
    safety = SafetyChecker(config)
    require_token = make_token_dependency(config)
    hub = StreamHub()

    app = FastAPI(
        title="MT5 Bridge",
        version="0.1.0",
        description="Windows-side bridge to MetaTrader 5 (Exness).",
    )
    app.state.config = config
    app.state.client = client
    app.state.safety = safety
    app.state.hub = hub

    logger.info("bridge.boot", **config.redact())

    # ------------------------------------------------------------------
    # Health (no auth — used by ops + Tailscale healthchecks)
    # ------------------------------------------------------------------
    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "mt5-bridge",
            "version": app.version,
            "mt5_connected": client.connected,
            "account_login": client.account_login,
            "last_tick_at": client.last_tick_at,
            "last_order_at": client.last_order_at,
            "subscribers": len(hub._clients),  # type: ignore[attr-defined]
        }

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    @app.post("/connect", dependencies=[Depends(require_token)])
    def connect(req: ConnectRequest) -> dict[str, Any]:
        try:
            snap = client.connect(req.server, req.login, req.password)
        except Exception as e:
            # We deliberately do not echo the password back even in errors.
            logger.error("bridge.connect_failed", login=req.login, server=req.server, error=str(e))
            raise HTTPException(status_code=502, detail=str(e))
        return {"success": True, "account": snap.__dict__}

    @app.post("/disconnect", dependencies=[Depends(require_token)])
    def disconnect() -> dict[str, Any]:
        client.disconnect()
        return {"success": True}

    @app.get("/account", dependencies=[Depends(require_token)])
    def account() -> dict[str, Any]:
        if not client.connected:
            raise HTTPException(status_code=409, detail="not connected; POST /connect first")
        return client.account_info().__dict__

    @app.get("/symbols", dependencies=[Depends(require_token)])
    def symbols() -> dict[str, Any]:
        if not client.connected:
            raise HTTPException(status_code=409, detail="not connected")
        return {"symbols": client.symbols()}

    @app.get("/quote/{symbol}", dependencies=[Depends(require_token)])
    def quote(symbol: str) -> dict[str, Any]:
        if not client.connected:
            raise HTTPException(status_code=409, detail="not connected")
        tick = client.tick(symbol)
        if tick is None:
            raise HTTPException(status_code=404, detail=f"no tick for {symbol}")
        return tick.__dict__

    @app.get("/positions", dependencies=[Depends(require_token)])
    def positions(symbol: str | None = Query(default=None)) -> dict[str, Any]:
        if not client.connected:
            raise HTTPException(status_code=409, detail="not connected")
        return {"positions": [p.__dict__ for p in client.positions(symbol)]}

    @app.get("/history", dependencies=[Depends(require_token)])
    def history(
        from_ts: float = Query(..., alias="from"),
        to_ts: float = Query(..., alias="to"),
    ) -> dict[str, Any]:
        if not client.connected:
            raise HTTPException(status_code=409, detail="not connected")
        if to_ts < from_ts:
            raise HTTPException(status_code=400, detail="to < from")
        return {"deals": client.history_deals(from_ts, to_ts)}

    # ------------------------------------------------------------------
    # Orders (all run through safety first)
    # ------------------------------------------------------------------
    @app.post("/order", dependencies=[Depends(require_token)])
    async def place_order(req: OrderRequest) -> dict[str, Any]:
        if not client.connected:
            raise HTTPException(status_code=409, detail="not connected")
        intent = OrderIntent(
            symbol=req.symbol,
            side=req.side,
            lot=req.lot,
            sl=req.sl,
            tp=req.tp,
            comment=req.comment,
            magic=req.magic,
        )
        try:
            safety.check_order(intent)
            if req.reference_price is not None:
                safety.check_sl_consistency(req.side, req.reference_price, req.sl, req.tp)
        except SafetyViolation as e:
            raise HTTPException(status_code=400, detail=f"safety: {e}")

        result = client.place_market(
            symbol=req.symbol,
            side=req.side,
            lot=req.lot,
            sl=req.sl,
            tp=req.tp,
            comment=req.comment,
            magic=req.magic,
        )
        # Fire-and-forget broadcast of fill events.
        if result.get("success"):
            await hub.broadcast({"type": "order_filled", "result": result})
        return result

    @app.post("/order/pending", dependencies=[Depends(require_token)])
    async def place_pending(req: PendingOrderRequest) -> dict[str, Any]:
        if not client.connected:
            raise HTTPException(status_code=409, detail="not connected")
        intent = OrderIntent(
            symbol=req.symbol,
            side=req.side,
            lot=req.lot,
            sl=req.sl,
            tp=req.tp,
            comment=req.comment,
            magic=req.magic,
        )
        try:
            safety.check_order(intent)
            safety.check_sl_consistency(req.side, req.price, req.sl, req.tp)
        except SafetyViolation as e:
            raise HTTPException(status_code=400, detail=f"safety: {e}")
        result = client.place_pending(
            symbol=req.symbol,
            side=req.side,
            order_kind=req.kind,
            lot=req.lot,
            price=req.price,
            sl=req.sl,
            tp=req.tp,
            comment=req.comment,
            magic=req.magic,
        )
        return result

    @app.post("/position/close", dependencies=[Depends(require_token)])
    async def close_position(req: CloseRequest) -> dict[str, Any]:
        if not client.connected:
            raise HTTPException(status_code=409, detail="not connected")
        result = client.close_position(req.ticket)
        if result.get("success"):
            await hub.broadcast({"type": "position_closed", "ticket": req.ticket})
        return result

    @app.post("/position/modify", dependencies=[Depends(require_token)])
    def modify_position(req: ModifyRequest) -> dict[str, Any]:
        if not client.connected:
            raise HTTPException(status_code=409, detail="not connected")
        return client.modify_position(req.ticket, req.sl, req.tp)

    # ------------------------------------------------------------------
    # WebSocket /stream — token via query string OR subprotocol.
    # We accept ?token=... (simple) and also Authorization-via-subprotocol.
    # ------------------------------------------------------------------
    @app.websocket("/stream")
    async def stream(ws: WebSocket) -> None:
        token = ws.query_params.get("token", "")
        if token != config.token:
            # Constant-time check
            import hmac
            if not hmac.compare_digest(token.encode("utf-8"), config.token.encode("utf-8")):
                await ws.close(code=status.WS_1008_POLICY_VIOLATION)
                return
        await ws.accept()
        await hub.add(ws)
        try:
            # Keep connection alive; client sends pings or subscription updates.
            while True:
                msg = await ws.receive_text()
                # Bridge mostly pushes — but accept inbound subscribe messages
                # so the engine can request specific symbols.
                try:
                    payload = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "subscribe":
                    sym = payload.get("symbol")
                    if sym:
                        # Touch symbol so MT5 starts streaming ticks.
                        if client.connected:
                            client.tick(sym)
                            await ws.send_text(
                                json.dumps({"type": "subscribed", "symbol": sym})
                            )
                elif payload.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong", "t": time.time()}))
        except WebSocketDisconnect:
            pass
        finally:
            await hub.remove(ws)

    # ------------------------------------------------------------------
    # Background tick poller — pushes /quote updates to subscribers.
    # MT5's Python API doesn't push, so we poll. 250ms is a reasonable
    # default that doesn't overload the terminal.
    # ------------------------------------------------------------------
    poller_state: dict[str, Any] = {"symbols": set(), "task": None}
    app.state.poller_state = poller_state

    async def tick_poller() -> None:
        while True:
            try:
                if client.connected:
                    for sym in list(poller_state["symbols"]):
                        tick = client.tick(sym)
                        if tick is None:
                            continue
                        await hub.broadcast(
                            {
                                "type": "tick",
                                "symbol": tick.symbol,
                                "bid": tick.bid,
                                "ask": tick.ask,
                                "time": tick.time,
                            }
                        )
            except Exception as e:
                logger.warning("tick_poller_error", error=str(e))
            await asyncio.sleep(0.25)

    @app.on_event("startup")
    async def _on_startup() -> None:
        poller_state["task"] = asyncio.create_task(tick_poller())

    @app.on_event("shutdown")
    async def _on_shutdown() -> None:
        task = poller_state.get("task")
        if task:
            task.cancel()
        client.disconnect()

    return app


# Boot helpers ---------------------------------------------------------------
app: FastAPI | None = None


def get_app() -> FastAPI:
    """Lazy-built singleton for `uvicorn mt5_bridge.server:app`."""
    global app
    if app is None:
        app = create_app()
    return app


# Module-level for uvicorn: `mt5_bridge.server:app` — this triggers
# BridgeConfig.from_env() so the process fails fast if BRIDGE_TOKEN missing.
try:
    app = create_app()
except Exception as exc:  # pragma: no cover
    # Don't die at import time when used as a library (tests, install scripts).
    logger.error("bridge.import_skipped", error=str(exc))
    app = None


def run() -> None:
    """Programmatic entry — used by install.bat / NSSM."""
    import uvicorn

    cfg = BridgeConfig.from_env()
    uvicorn.run(
        "mt5_bridge.server:get_app",
        host=cfg.host,
        port=cfg.port,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    run()
