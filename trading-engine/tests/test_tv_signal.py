"""Tests for TradingView signal integration.

No real network calls — every TV interaction is mocked via stubbing
`tradingview_ta.TA_Handler` directly OR by injecting fake clients into
the strategy. This keeps CI deterministic + offline.

What we cover:
1. `tradingview/symbols.py` mapping (XAUUSD → OANDA, BTCUSDT → BINANCE, fallback).
2. `tradingview/scorer.py` — all-BUY → +100, mixed → middling, all-NEUTRAL → 0.
3. `TVSignalStrategy` — live mode emits long on strong score + agreement.
4. `TVSignalStrategy` — cool-down prevents back-to-back entries.
5. `TVSignalStrategy` — backtest mode degrades to proxy without TV client.
6. `TVSignalStrategy` — agreement threshold respected (rejects if disagreement).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pytest

from strategies.tv_signal import TVSignalStrategy
from tradingview.client import TVAnalysis
from tradingview.scorer import Scorer, combine_recommendations
from tradingview.symbols import SUPPORTED_SYMBOLS, list_supported, resolve_symbol


# ---------------------------------------------------------------------------
# Symbol mapping
# ---------------------------------------------------------------------------
def test_symbols_xauusd_maps_to_oanda() -> None:
    s = resolve_symbol("XAUUSD")
    assert s.symbol == "XAUUSD"
    assert s.exchange == "OANDA"
    assert s.asset_class == "gold"


def test_symbols_btcusdt_maps_to_binance() -> None:
    s = resolve_symbol("BTCUSDT")
    assert s.symbol == "BTCUSDT"
    assert s.exchange == "BINANCE"
    assert s.asset_class == "crypto"


def test_symbols_unknown_falls_back_to_fx_idc() -> None:
    s = resolve_symbol("ZZZUSD")
    assert s.symbol == "ZZZUSD"
    assert s.exchange == "FX_IDC"  # documented fallback


def test_symbols_override_exchange() -> None:
    s = resolve_symbol("XAUUSD", exchange="FXOPEN")
    assert s.exchange == "FXOPEN"
    assert s.asset_class == "gold"


def test_list_supported_includes_core_pairs() -> None:
    rows = list_supported()
    internal_syms = {r["internal_symbol"] for r in rows}
    assert "XAUUSD" in internal_syms
    assert "BTCUSDT" in internal_syms
    assert "EURUSD" in internal_syms
    assert all(
        {"internal_symbol", "tv_symbol", "tv_exchange", "asset_class", "display_name"} <= r.keys()
        for r in rows
    )


def test_supported_symbols_dict_not_empty() -> None:
    assert len(SUPPORTED_SYMBOLS) >= 10


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------
def _mk_analysis(interval: str, rec: str, buy: int = 0, sell: int = 0, neutral: int = 0) -> TVAnalysis:
    return TVAnalysis(
        symbol="XAUUSD",
        exchange="OANDA",
        interval=interval,
        recommendation=rec,
        buy_signals=buy,
        sell_signals=sell,
        neutral_signals=neutral,
        price=2000.0,
    )


def test_scorer_all_strong_buy_returns_plus_100() -> None:
    analyses = [
        _mk_analysis("15m", "STRONG_BUY"),
        _mk_analysis("1h", "STRONG_BUY"),
        _mk_analysis("4h", "STRONG_BUY"),
    ]
    s = combine_recommendations(analyses)
    assert s.score == pytest.approx(100.0, abs=0.01)
    assert s.direction == "BUY"
    assert s.agreement_pct == pytest.approx(1.0)


def test_scorer_all_strong_sell_returns_minus_100() -> None:
    analyses = [
        _mk_analysis("15m", "STRONG_SELL"),
        _mk_analysis("1h", "STRONG_SELL"),
        _mk_analysis("4h", "STRONG_SELL"),
    ]
    s = combine_recommendations(analyses)
    assert s.score == pytest.approx(-100.0, abs=0.01)
    assert s.direction == "SELL"


def test_scorer_mixed_is_middling() -> None:
    analyses = [
        _mk_analysis("15m", "STRONG_BUY"),
        _mk_analysis("1h", "NEUTRAL"),
        _mk_analysis("4h", "SELL"),
    ]
    s = combine_recommendations(analyses)
    # Should be a small absolute value, not at the extreme.
    assert -50.0 < s.score < 50.0


def test_scorer_higher_tf_weighted_more() -> None:
    # 15m bullish, 1d bearish → 1d outweighs (weight 2.0 vs 0.6)
    analyses = [
        _mk_analysis("15m", "STRONG_BUY"),
        _mk_analysis("1d", "STRONG_SELL"),
    ]
    s = combine_recommendations(analyses)
    assert s.score < 0  # bearish dominates


def test_scorer_empty_input_is_neutral() -> None:
    s = combine_recommendations([])
    assert s.score == 0.0
    assert s.direction == "NEUTRAL"
    assert s.confidence == 0.0


def test_scorer_confidence_reflects_agreement_and_strength() -> None:
    all_strong = [_mk_analysis("1h", "STRONG_BUY") for _ in range(3)]
    one_strong_two_neutral = [
        _mk_analysis("1h", "STRONG_BUY"),
        _mk_analysis("4h", "NEUTRAL"),
        _mk_analysis("1d", "NEUTRAL"),
    ]
    c1 = combine_recommendations(all_strong).confidence
    c2 = combine_recommendations(one_strong_two_neutral).confidence
    assert c1 > c2


# ---------------------------------------------------------------------------
# Fake TV client + scorer for strategy tests
# ---------------------------------------------------------------------------
@dataclass
class FakeTVClient:
    """Stub — returns canned analyses per interval, no network."""

    canned: dict[str, str]  # interval -> recommendation
    calls: int = 0

    def get_analysis(self, symbol: str, exchange: str, interval: str, *, screener: str = "forex") -> TVAnalysis:
        self.calls += 1
        rec = self.canned.get(interval, "NEUTRAL")
        return _mk_analysis(interval, rec)


def _ohlcv(n: int = 60, start: float = 2000.0) -> pd.DataFrame:
    """Synthetic OHLCV — slight upward drift, deterministic."""
    rng = np.random.default_rng(seed=7)
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    rets = rng.normal(0.0005, 0.002, size=n)
    close = start * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0.0005, 0.0005, n)))
    low = close * (1 - np.abs(rng.normal(0.0005, 0.0005, n)))
    open_ = np.concatenate([[start], close[:-1]])
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 100.0},
        index=idx,
    )


# ---------------------------------------------------------------------------
# Strategy — live mode (with injected TV client)
# ---------------------------------------------------------------------------
def test_strategy_live_emits_long_on_strong_buy_consensus() -> None:
    strat = TVSignalStrategy(params={"intervals": ["15m", "1h", "4h"]})
    strat.symbol = "XAUUSD"
    fake = FakeTVClient(
        canned={"15m": "STRONG_BUY", "1h": "STRONG_BUY", "4h": "STRONG_BUY"}
    )
    strat.set_tv_client(fake, Scorer())

    df = _ohlcv(n=60)
    sigs = strat.signals(df)
    # Only the last bar should carry the signal (live path).
    last = sigs.iloc[-1]
    assert int(last["direction"]) == 1, "expected long signal on all-STRONG_BUY"
    assert last["entry"] > 0
    assert last["sl"] < last["entry"] < last["tp"]
    assert "tv_long" in last["reason"]
    assert fake.calls == 3, "should fetch one analysis per interval"


def test_strategy_live_emits_short_on_strong_sell_consensus() -> None:
    strat = TVSignalStrategy(params={"intervals": ["15m", "1h", "4h"]})
    strat.symbol = "XAUUSD"
    fake = FakeTVClient(
        canned={"15m": "STRONG_SELL", "1h": "STRONG_SELL", "4h": "STRONG_SELL"}
    )
    strat.set_tv_client(fake, Scorer())

    df = _ohlcv(n=60)
    sigs = strat.signals(df)
    last = sigs.iloc[-1]
    assert int(last["direction"]) == -1
    assert last["sl"] > last["entry"] > last["tp"]


def test_strategy_live_rejects_when_disagreement() -> None:
    # 3 TFs, only 1 bullish → agreement = 1/3 < default 0.6
    strat = TVSignalStrategy(params={"intervals": ["15m", "1h", "4h"]})
    strat.symbol = "XAUUSD"
    fake = FakeTVClient(
        canned={"15m": "STRONG_BUY", "1h": "NEUTRAL", "4h": "NEUTRAL"}
    )
    strat.set_tv_client(fake, Scorer())

    df = _ohlcv(n=60)
    sigs = strat.signals(df)
    assert int(sigs.iloc[-1]["direction"]) == 0


def test_strategy_live_cool_down_blocks_entry() -> None:
    strat = TVSignalStrategy(
        params={"intervals": ["15m", "1h", "4h"], "cool_down_min": 60}
    )
    strat.symbol = "XAUUSD"
    fake = FakeTVClient(
        canned={"15m": "STRONG_BUY", "1h": "STRONG_BUY", "4h": "STRONG_BUY"}
    )
    strat.set_tv_client(fake, Scorer())

    df = _ohlcv(n=60)
    # Mark an exit 10 minutes before the last bar.
    strat.mark_exit(df.index[-1] - pd.Timedelta(minutes=10))
    sigs = strat.signals(df)
    assert int(sigs.iloc[-1]["direction"]) == 0, "cool-down should block re-entry"


def test_strategy_live_cool_down_expires() -> None:
    strat = TVSignalStrategy(
        params={"intervals": ["15m", "1h", "4h"], "cool_down_min": 60}
    )
    strat.symbol = "XAUUSD"
    fake = FakeTVClient(
        canned={"15m": "STRONG_BUY", "1h": "STRONG_BUY", "4h": "STRONG_BUY"}
    )
    strat.set_tv_client(fake, Scorer())

    df = _ohlcv(n=60)
    # Exit 2 hours ago → cool-down expired.
    strat.mark_exit(df.index[-1] - pd.Timedelta(minutes=120))
    sigs = strat.signals(df)
    assert int(sigs.iloc[-1]["direction"]) == 1


def test_strategy_live_handles_tv_fetch_failure_gracefully() -> None:
    class BadClient:
        def get_analysis(self, *a: Any, **k: Any) -> TVAnalysis:
            raise RuntimeError("network down")

    strat = TVSignalStrategy(params={"intervals": ["15m", "1h"]})
    strat.symbol = "XAUUSD"
    strat.set_tv_client(BadClient(), Scorer())

    df = _ohlcv(n=60)
    sigs = strat.signals(df)
    # No crash; just no signal.
    assert int(sigs.iloc[-1]["direction"]) == 0


# ---------------------------------------------------------------------------
# Strategy — backtest proxy mode (no TV client)
# ---------------------------------------------------------------------------
def test_strategy_backtest_proxy_runs_without_tv() -> None:
    strat = TVSignalStrategy(
        params={"entry_score_threshold": 30.0, "atr_period": 7}
    )
    strat.symbol = "XAUUSD"
    assert strat._tv_client is None  # no live client

    df = _ohlcv(n=120)
    sigs = strat.signals(df)
    # Must produce a schema-conforming frame.
    assert {"direction", "entry", "sl", "tp", "reason"} <= set(sigs.columns)
    assert len(sigs) == len(df)
    assert sigs["direction"].isin([-1, 0, 1]).all()


def test_strategy_describe_includes_backtest_caveat() -> None:
    strat = TVSignalStrategy()
    d = strat.describe()
    assert "backtest_caveat" in d
    assert "proxy" in d["backtest_caveat"].lower()
    assert d["mode_hint"] == "backtest_proxy"


def test_strategy_describe_live_mode_when_client_set() -> None:
    strat = TVSignalStrategy()
    strat.set_tv_client(FakeTVClient(canned={}), Scorer())
    assert strat.describe()["mode_hint"] == "live"


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------
def test_strategy_registered_in_worker() -> None:
    from workers.backtest_worker import _strategy_registry

    reg = _strategy_registry()
    assert "tv_signal" in reg
    assert reg["tv_signal"] is TVSignalStrategy
