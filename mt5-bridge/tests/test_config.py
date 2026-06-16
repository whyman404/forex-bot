"""Config tests — env-driven, redaction, validation."""
from __future__ import annotations

import pytest

from mt5_bridge.config import BridgeConfig


def test_from_env_requires_token(monkeypatch):
    monkeypatch.delenv("BRIDGE_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="BRIDGE_TOKEN is not set"):
        BridgeConfig.from_env()


def test_from_env_rejects_short_token(monkeypatch):
    monkeypatch.setenv("BRIDGE_TOKEN", "short")
    with pytest.raises(RuntimeError, match="too short"):
        BridgeConfig.from_env()


def test_from_env_parses_csv_lists(monkeypatch):
    monkeypatch.setenv("BRIDGE_TOKEN", "a" * 48)
    monkeypatch.setenv("BRIDGE_SYMBOL_ALLOWLIST", "XAUUSD, BTCUSD ,EURUSD")
    cfg = BridgeConfig.from_env()
    assert cfg.symbol_allowlist == ["XAUUSD", "BTCUSD", "EURUSD"]


def test_redact_masks_token():
    cfg = BridgeConfig(bind="0.0.0.0:8500", token="abcdefghij" * 5)
    r = cfg.redact()
    assert r["token"].startswith("abcd")
    assert r["token"].endswith("ij")
    assert "…" in r["token"]
    # Original token must not appear verbatim
    assert "abcdefghij" * 5 not in r["token"]


def test_host_port_parsing():
    cfg = BridgeConfig(bind="0.0.0.0:8500", token="a" * 48)
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8500
