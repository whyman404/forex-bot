"""FastAPI server for the trading engine (dev mode).

Endpoints
---------
- GET  /healthz                     — liveness
- POST /run-backtest                — kick off in-process backtest (202 + bg task)
- POST /test-mt5-connection         — call MT5 adapter; mock-success off-Windows
- GET  /backtest/{id}/equity-curve  — JSON time-series

Phase 2 will move /run-backtest to an RQ worker (workers/backtest_worker.py
already supports both paths). This server keeps an in-process path for
fast dev iteration.
"""
from __future__ import annotations

import json
import os
import platform
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Local imports — keep heavy deps lazy in handlers so /healthz is fast.

app = FastAPI(
    title="Forex-Bot Trading Engine",
    version="0.1.0",
    description="Internal API for backtests + broker integration. NOT public.",
)

# Phase 2 — live trading endpoints (/live/*). Register lazily so a missing
# httpx/psycopg dep (dev minimal install) doesn't break the backtest API.
try:
    from live.server_endpoints import register_live_routes

    register_live_routes(app)
except Exception as _live_exc:  # pragma: no cover — visible in container logs
    import logging as _logging

    _logging.getLogger(__name__).warning(
        "live routes not registered: %s", _live_exc
    )

# In-memory store: backtest_id -> {status, equity_curve, summary, error}.
# Persisted to disk for /backtest/{id}/equity-curve to survive process restart.
_BACKTEST_STATE: dict[str, dict[str, Any]] = {}

EQUITY_DIR = Path(os.getenv("EQUITY_CURVE_DIR", "/var/data/equity-curves"))


def _ensure_equity_dir() -> Path:
    """Resolve and ensure the equity-curve dir exists; fall back if /var/data not writable."""
    target = EQUITY_DIR
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except PermissionError:
        fallback = Path.home() / ".forex-bot" / "equity-curves"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RunBacktestRequest(BaseModel):
    strategy_code: str = Field(..., examples=["london_breakout"])
    asset: str = Field(..., examples=["XAUUSD"])
    timeframe: str = Field(..., examples=["M15"])
    start_date: str = Field(..., examples=["2025-05-05"])
    end_date: str = Field(..., examples=["2025-06-05"])
    params: dict[str, Any] = Field(default_factory=dict)
    backtest_id: str | None = Field(
        default=None,
        description="Optional client-provided UUID. Generated if absent.",
    )


class RunBacktestResponse(BaseModel):
    backtest_id: str
    status: str
    message: str


class TestMT5Request(BaseModel):
    server: str
    login: int
    password: str
    broker_account_id: str | None = None


class TestMT5Response(BaseModel):
    success: bool
    platform: str
    mock: bool
    message: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "trading-engine",
        "version": app.version,
        "platform": platform.system(),
    }


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
def _run_backtest_inproc(backtest_id: str, req: RunBacktestRequest) -> None:
    """Run backtest in a worker thread; write state to memory + disk."""
    _BACKTEST_STATE[backtest_id] = {"status": "running"}
    try:
        from workers.backtest_worker import run_backtest_job

        result = run_backtest_job(
            backtest_id=backtest_id,
            strategy_code=req.strategy_code,
            asset=req.asset,
            timeframe=req.timeframe,
            start=req.start_date,
            end=req.end_date,
            params=req.params,
        )
        _BACKTEST_STATE[backtest_id] = {
            "status": "completed",
            "summary": result.get("summary", {}),
            "equity_curve_url": result.get("equity_curve_url"),
        }
    except Exception as e:  # broad: dev-mode tracing
        _BACKTEST_STATE[backtest_id] = {
            "status": "failed",
            "error": str(e),
        }


@app.post(
    "/run-backtest",
    response_model=RunBacktestResponse,
    status_code=202,
)
def run_backtest(req: RunBacktestRequest) -> RunBacktestResponse:
    """Kick off backtest. Returns 202 immediately; status updated async.

    Dev-mode runs in a thread. Phase 2 will enqueue to RQ — request shape
    is identical, so frontend code does not change.
    """
    backtest_id = req.backtest_id or str(uuid.uuid4())
    if backtest_id in _BACKTEST_STATE and _BACKTEST_STATE[backtest_id].get(
        "status"
    ) == "running":
        raise HTTPException(409, f"Backtest {backtest_id} already running")
    _BACKTEST_STATE[backtest_id] = {"status": "queued"}
    thread = threading.Thread(
        target=_run_backtest_inproc,
        args=(backtest_id, req),
        daemon=True,
    )
    thread.start()
    return RunBacktestResponse(
        backtest_id=backtest_id,
        status="accepted",
        message="Backtest started; poll /backtest/{id}/equity-curve",
    )


@app.get("/backtest/{backtest_id}/equity-curve")
def get_equity_curve(backtest_id: str) -> JSONResponse:
    """Return the equity-curve time-series for a backtest.

    Looks in memory first; falls back to disk so the result survives a
    process restart.
    """
    state = _BACKTEST_STATE.get(backtest_id)

    # Try the on-disk artifact regardless of memory state.
    eq_path = _ensure_equity_dir() / f"{backtest_id}.json"
    if eq_path.exists():
        with eq_path.open() as f:
            payload = json.load(f)
        return JSONResponse(
            {
                "backtest_id": backtest_id,
                "status": (state or {}).get("status", "completed"),
                "summary": payload.get("summary", {}),
                "equity_curve": payload.get("equity_curve", []),
            }
        )

    if state is None:
        raise HTTPException(404, f"backtest_id={backtest_id} not found")
    if state["status"] != "completed":
        return JSONResponse(
            status_code=202,
            content={
                "backtest_id": backtest_id,
                "status": state["status"],
                "error": state.get("error"),
            },
        )
    return JSONResponse(
        {
            "backtest_id": backtest_id,
            "status": state["status"],
            "summary": state.get("summary", {}),
            "equity_curve": [],
        }
    )


# ---------------------------------------------------------------------------
# MT5 connection test
# ---------------------------------------------------------------------------
@app.post(
    "/test-mt5-connection",
    response_model=TestMT5Response,
)
def test_mt5_connection(req: TestMT5Request) -> TestMT5Response:
    """Test MT5 credentials by calling broker/mt5_adapter.MT5Broker.connect().

    Off-Windows (Mac/Linux dev), we return mock success so the frontend +
    backend integration can be exercised end-to-end without a Windows VPS.
    The `mock` flag in the response makes that explicit.
    """
    sys = platform.system()
    if sys != "Windows":
        return TestMT5Response(
            success=True,
            platform=sys,
            mock=True,
            message=(
                f"Mocked OK — MT5 only runs on Windows; current platform={sys}. "
                "In dev we accept credentials without verifying."
            ),
        )

    try:
        from broker.mt5_adapter import MT5Broker

        broker = MT5Broker(
            account=req.login,
            password=req.password,
            server=req.server,
        )
        broker.connect()
        broker.disconnect()
        return TestMT5Response(
            success=True,
            platform=sys,
            mock=False,
            message=f"Connected to {req.server} as account {req.login}",
        )
    except Exception as e:
        return TestMT5Response(
            success=False,
            platform=sys,
            mock=False,
            message="MT5 connect failed",
            error=str(e),
        )
