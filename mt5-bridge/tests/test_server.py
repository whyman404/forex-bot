"""End-to-end FastAPI tests with a mocked MetaTrader5 module."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _make_client(bridge_config, mock_mt5) -> TestClient:
    """Build a TestClient against an app wired to the mocked MT5 + config."""
    from mt5_bridge.server import create_app

    app = create_app(bridge_config)
    # TestClient triggers startup/shutdown via context manager.
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_healthz_no_auth_required(bridge_config, mock_mt5):
    with _make_client(bridge_config, mock_mt5) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["service"] == "mt5-bridge"
        assert body["mt5_connected"] is False


def test_connect_and_account(bridge_config, mock_mt5):
    """POST /connect should call mt5.initialize + login, then /account works."""
    mock_mt5.account_info = MagicMock(
        return_value=SimpleNamespace(
            login=12345,
            server="Exness-Test",
            balance=10000.0,
            equity=10000.0,
            margin=0.0,
            margin_free=10000.0,
            margin_level=0.0,
            currency="USD",
            leverage=500,
        )
    )
    with _make_client(bridge_config, mock_mt5) as client:
        r = client.post(
            "/connect",
            headers=_auth(bridge_config.token),
            json={"server": "Exness-Test", "login": 12345, "password": "secret"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["success"] is True
        assert r.json()["account"]["balance"] == 10000.0

        r2 = client.get("/account", headers=_auth(bridge_config.token))
        assert r2.status_code == 200
        assert r2.json()["balance"] == 10000.0


def test_connect_requires_auth(bridge_config, mock_mt5):
    with _make_client(bridge_config, mock_mt5) as client:
        r = client.post("/connect", json={"server": "x", "login": 1, "password": "p"})
        assert r.status_code == 401


def test_account_409_when_not_connected(bridge_config, mock_mt5):
    with _make_client(bridge_config, mock_mt5) as client:
        r = client.get("/account", headers=_auth(bridge_config.token))
        assert r.status_code == 409


def test_order_400_when_safety_violation(bridge_config, mock_mt5):
    """An order with lot above MAX_LOT should be rejected by safety before MT5."""
    mock_mt5.account_info = MagicMock(
        return_value=SimpleNamespace(
            login=1, server="x", balance=1, equity=1, margin=0, margin_free=1,
            margin_level=0, currency="USD", leverage=500,
        )
    )
    with _make_client(bridge_config, mock_mt5) as client:
        client.post(
            "/connect",
            headers=_auth(bridge_config.token),
            json={"server": "x", "login": 1, "password": "p"},
        )
        r = client.post(
            "/order",
            headers=_auth(bridge_config.token),
            json={
                "symbol": "XAUUSD",
                "side": "buy",
                "lot": 5.0,  # > max_lot=0.5
                "sl": 1900.0,
                "tp": 2000.0,
            },
        )
        assert r.status_code == 400
        assert "exceeds MAX_LOT" in r.json()["detail"]


def test_order_happy_path(bridge_config, mock_mt5):
    """A clean order goes safety -> client -> mt5.order_send and returns success."""
    mock_mt5.account_info = MagicMock(
        return_value=SimpleNamespace(
            login=1, server="x", balance=1, equity=1, margin=0, margin_free=1,
            margin_level=0, currency="USD", leverage=500,
        )
    )
    mock_mt5.symbol_info_tick = MagicMock(
        return_value=SimpleNamespace(bid=1950.0, ask=1950.2, time=0)
    )
    mock_mt5.order_send = MagicMock(
        return_value=SimpleNamespace(
            retcode=mock_mt5.TRADE_RETCODE_DONE,
            order=999,
            price=1950.2,
            volume=0.1,
            comment="ok",
        )
    )
    with _make_client(bridge_config, mock_mt5) as client:
        client.post(
            "/connect",
            headers=_auth(bridge_config.token),
            json={"server": "x", "login": 1, "password": "p"},
        )
        r = client.post(
            "/order",
            headers=_auth(bridge_config.token),
            json={
                "symbol": "XAUUSD",
                "side": "buy",
                "lot": 0.1,
                "sl": 1900.0,
                "tp": 2000.0,
                "reference_price": 1950.0,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["ticket"] == 999
        assert body["fill_price"] == 1950.2
