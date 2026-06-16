"""API tests for server.py.

We use FastAPI's TestClient. The in-process backtest runs in a daemon thread,
so we wait (with a generous timeout) on /backtest/{id}/equity-curve.

Coverage
--------
- GET  /healthz
- POST /run-backtest happy-path → 202 + eventually completes with positive
  total_trades (sample data is deliberately constructed to trigger at least
  one trade for every strategy).
- POST /test-mt5-connection on non-Windows returns mock=True success.
- GET  /backtest/{id}/equity-curve on unknown id → 404.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def _wait_for_completion(backtest_id: str, timeout_sec: float = 60.0) -> dict:
    """Poll the equity-curve endpoint until status != running/queued, or fail."""
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        r = client.get(f"/backtest/{backtest_id}/equity-curve")
        last = r.json()
        status = last.get("status")
        if status in ("completed", "failed"):
            return last
        time.sleep(0.5)
    pytest.fail(f"Backtest {backtest_id} did not finish in {timeout_sec}s; last={last}")


# ---------------------------------------------------------------------------
def test_healthz_ok():
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "trading-engine"


# ---------------------------------------------------------------------------
def test_run_backtest_returns_202():
    payload = {
        "strategy_code": "donchian_breakout",
        "asset": "BTCUSDT",
        "timeframe": "H1",
        "start_date": "2025-05-05",
        "end_date": "2025-06-04",
        "params": {},
    }
    r = client.post("/run-backtest", json=payload)
    assert r.status_code == 202, r.text
    body = r.json()
    assert "backtest_id" in body
    assert body["status"] == "accepted"


# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "strategy_code, asset, timeframe",
    [
        ("london_breakout", "XAUUSD", "M5"),
        ("ny_killzone", "XAUUSD", "M5"),
        ("ema_adx_trend", "XAUUSD", "H1"),
        ("ema_rsi_swing", "BTCUSDT", "H4"),
        ("donchian_breakout", "BTCUSDT", "H1"),
        ("grid_bot", "BTCUSDT", "H1"),
    ],
)
def test_backtest_produces_trades(strategy_code, asset, timeframe):
    """Every strategy must fire at least 1 trade on the seeded sample data.

    If a strategy returns zero trades, either (a) the sample is too tame
    for it — fix `data/samples/generate.py`, or (b) the strategy has a bug.
    """
    payload = {
        "strategy_code": strategy_code,
        "asset": asset,
        "timeframe": timeframe,
        "start_date": "2025-01-01",  # wide window → use full sample
        "end_date": "2026-01-01",
        "params": {},
    }
    r = client.post("/run-backtest", json=payload)
    assert r.status_code == 202, r.text
    backtest_id = r.json()["backtest_id"]

    final = _wait_for_completion(backtest_id, timeout_sec=120.0)
    assert final.get("status") == "completed", f"final={final}"
    summary = final.get("summary", {})
    assert summary.get("total_trades", 0) >= 1, (
        f"{strategy_code} produced 0 trades on sample data; summary={summary}"
    )


# ---------------------------------------------------------------------------
def test_test_mt5_mock_on_non_windows():
    """On Mac/Linux dev the endpoint must return mock=True success."""
    import platform

    payload = {
        "server": "Exness-MT5Real8",
        "login": 1234567,
        "password": "test-pass",
        "broker_account_id": None,
    }
    r = client.post("/test-mt5-connection", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    if platform.system() != "Windows":
        assert body["mock"] is True
        assert body["success"] is True


# ---------------------------------------------------------------------------
def test_equity_curve_unknown_id_404():
    r = client.get("/backtest/this-id-does-not-exist/equity-curve")
    assert r.status_code == 404
