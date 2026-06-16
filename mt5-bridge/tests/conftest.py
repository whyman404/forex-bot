"""Shared fixtures — mock MetaTrader5 so tests run on Mac/Linux too."""
from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_mt5(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Install a fake `MetaTrader5` module in sys.modules and re-patch the
    client's lazy importer."""
    fake = types.ModuleType("MetaTrader5")

    # Constants the bridge uses
    fake.TRADE_ACTION_DEAL = 1
    fake.TRADE_ACTION_PENDING = 5
    fake.TRADE_ACTION_SLTP = 6
    fake.TRADE_ACTION_REMOVE = 8
    fake.ORDER_TYPE_BUY = 0
    fake.ORDER_TYPE_SELL = 1
    fake.ORDER_TYPE_BUY_LIMIT = 2
    fake.ORDER_TYPE_SELL_LIMIT = 3
    fake.ORDER_TYPE_BUY_STOP = 4
    fake.ORDER_TYPE_SELL_STOP = 5
    fake.ORDER_TIME_GTC = 0
    fake.ORDER_FILLING_IOC = 2
    fake.TRADE_RETCODE_DONE = 10009

    # Behaviour stubs — override per-test as needed
    fake.initialize = MagicMock(return_value=True)
    fake.login = MagicMock(return_value=True)
    fake.shutdown = MagicMock(return_value=None)
    fake.last_error = MagicMock(return_value=(0, "ok"))
    fake.symbol_select = MagicMock(return_value=True)

    sys.modules["MetaTrader5"] = fake

    # Reset the bridge client's import cache so it picks up our fake.
    import mt5_bridge.mt5_client as mt5c

    monkeypatch.setattr(mt5c, "_mt5", fake)
    monkeypatch.setattr(mt5c, "_IMPORT_ERROR", None)
    return fake


@pytest.fixture
def bridge_config(monkeypatch: pytest.MonkeyPatch):
    """Minimal valid BridgeConfig — 48-char token, allowlist on XAUUSD."""
    from mt5_bridge.config import BridgeConfig

    cfg = BridgeConfig(
        bind="127.0.0.1:8500",
        token="a" * 48,
        mt5_path=None,
        max_lot=0.5,
        symbol_allowlist=["XAUUSD", "BTCUSD"],
        require_sl=True,
    )
    return cfg
