"""Safety tests — caps, allowlist, SL requirement, SL/TP side check."""
from __future__ import annotations

import pytest

from mt5_bridge.safety import OrderIntent, SafetyChecker, SafetyViolation


def test_reject_zero_lot(bridge_config):
    s = SafetyChecker(bridge_config)
    with pytest.raises(SafetyViolation, match="lot must be > 0"):
        s.check_order(
            OrderIntent(symbol="XAUUSD", side="buy", lot=0.0, sl=1900.0, tp=2000.0)
        )


def test_reject_lot_above_max(bridge_config):
    s = SafetyChecker(bridge_config)
    with pytest.raises(SafetyViolation, match="exceeds MAX_LOT"):
        s.check_order(
            OrderIntent(symbol="XAUUSD", side="buy", lot=2.0, sl=1900.0, tp=2000.0)
        )


def test_reject_symbol_not_in_allowlist(bridge_config):
    s = SafetyChecker(bridge_config)
    with pytest.raises(SafetyViolation, match="not in allowlist"):
        s.check_order(
            OrderIntent(symbol="EURUSD", side="buy", lot=0.1, sl=1.0, tp=1.2)
        )


def test_reject_missing_sl_when_required(bridge_config):
    s = SafetyChecker(bridge_config)
    with pytest.raises(SafetyViolation, match="SL is required"):
        s.check_order(
            OrderIntent(symbol="XAUUSD", side="buy", lot=0.1, sl=None, tp=2000.0)
        )


def test_invalid_side(bridge_config):
    s = SafetyChecker(bridge_config)
    with pytest.raises(SafetyViolation, match="invalid side"):
        s.check_order(
            OrderIntent(symbol="XAUUSD", side="hold", lot=0.1, sl=1900.0, tp=2000.0)
        )


def test_happy_path(bridge_config):
    s = SafetyChecker(bridge_config)
    s.check_order(
        OrderIntent(symbol="XAUUSD", side="buy", lot=0.1, sl=1900.0, tp=2000.0)
    )  # no raise


def test_sl_consistency_buy_correct(bridge_config):
    s = SafetyChecker(bridge_config)
    s.check_sl_consistency("buy", entry=1950.0, sl=1900.0, tp=2000.0)


def test_sl_consistency_buy_inverted_sl_raises(bridge_config):
    """A buy with SL above entry is an inverted-SL bug — unlimited risk."""
    s = SafetyChecker(bridge_config)
    with pytest.raises(SafetyViolation, match="buy SL must be below entry"):
        s.check_sl_consistency("buy", entry=1950.0, sl=2000.0, tp=2100.0)


def test_sl_consistency_sell_correct(bridge_config):
    s = SafetyChecker(bridge_config)
    s.check_sl_consistency("sell", entry=1950.0, sl=2000.0, tp=1900.0)


def test_sl_consistency_sell_inverted_sl_raises(bridge_config):
    s = SafetyChecker(bridge_config)
    with pytest.raises(SafetyViolation, match="sell SL must be above entry"):
        s.check_sl_consistency("sell", entry=1950.0, sl=1900.0, tp=1800.0)


def test_allowlist_empty_allows_any(monkeypatch):
    from mt5_bridge.config import BridgeConfig

    cfg = BridgeConfig(
        bind="127.0.0.1:0",
        token="a" * 48,
        symbol_allowlist=[],  # empty
        max_lot=10,
    )
    s = SafetyChecker(cfg)
    s.check_order(
        OrderIntent(symbol="WHATEVER", side="buy", lot=1.0, sl=1.0, tp=2.0)
    )  # no raise
