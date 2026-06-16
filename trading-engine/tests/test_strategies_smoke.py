"""Smoke tests for every strategy.

Goal: verify imports + that `signals(data)` returns a well-formed DataFrame
on a tiny synthetic OHLCV input. NOT a performance test.

We deliberately use only 10 candles — strategies that need long warm-up
(EMA50, ADX14, Donchian20) won't generate signals on this, and that's OK.
We just check the schema + that no exception is raised.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.runner import COST_MODELS, run_backtest
from strategies.base import Strategy
from strategies.donchian_breakout import DonchianBreakoutStrategy
from strategies.ema_adx_trend import EMA50ADXTrendStrategy
from strategies.ema_rsi_swing import EMARSISwingStrategy
from strategies.grid_bot import GridBotStrategy
from strategies.london_breakout import LondonBreakoutStrategy
from strategies.ny_killzone import NYKillzoneReversalStrategy


def _synthetic_ohlcv(n: int = 60, freq: str = "5min", start_price: float = 2000.0) -> pd.DataFrame:
    """Build a tiny but valid OHLCV frame. Slight random walk."""
    rng = np.random.default_rng(seed=42)
    idx = pd.date_range("2026-01-01 00:00:00", periods=n, freq=freq, tz="UTC")
    rets = rng.normal(0, 0.002, size=n)
    close = start_price * np.exp(np.cumsum(rets))
    high = close * (1 + rng.uniform(0.0001, 0.001, size=n))
    low = close * (1 - rng.uniform(0.0001, 0.001, size=n))
    open_ = np.concatenate([[start_price], close[:-1]])
    vol = rng.uniform(100, 1000, size=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


STRATEGIES: list[type[Strategy]] = [
    LondonBreakoutStrategy,
    NYKillzoneReversalStrategy,
    EMA50ADXTrendStrategy,
    EMARSISwingStrategy,
    DonchianBreakoutStrategy,
    GridBotStrategy,
]


@pytest.mark.parametrize("strat_cls", STRATEGIES)
def test_strategy_imports_and_signals_schema(strat_cls: type[Strategy]) -> None:
    """Every strategy must construct + produce a schema-conforming DataFrame."""
    df = _synthetic_ohlcv(n=60)
    strat = strat_cls()
    sigs = strat.signals(df)
    assert isinstance(sigs, pd.DataFrame)
    for col in ("direction", "entry", "sl", "tp", "reason"):
        assert col in sigs.columns, f"{strat_cls.__name__} missing column {col!r}"
    assert len(sigs) == len(df), (
        f"{strat_cls.__name__} signals length {len(sigs)} != data length {len(df)}"
    )
    # direction must be in {-1, 0, +1}
    assert sigs["direction"].isin([-1, 0, 1]).all(), (
        f"{strat_cls.__name__} produced direction values outside {{-1,0,1}}"
    )


@pytest.mark.parametrize("strat_cls", STRATEGIES)
def test_strategy_describe(strat_cls: type[Strategy]) -> None:
    """`describe()` should return JSON-serialisable metadata."""
    s = strat_cls()
    meta = s.describe()
    assert "name" in meta
    assert "params" in meta
    assert "risk_per_trade_pct" in meta


def test_runner_with_synthetic() -> None:
    """Runner should produce a metrics dict — even if zero trades fire."""
    df = _synthetic_ohlcv(n=120, freq="1h")
    strat = EMA50ADXTrendStrategy()
    res = run_backtest(strat, df, cost_model="zero")
    assert "summary" in res
    assert "trades" in res
    assert "equity_curve" in res
    assert isinstance(res["summary"]["total_trades"], int)


def test_cost_models_present() -> None:
    assert "exness_gold" in COST_MODELS
    assert "binance_crypto" in COST_MODELS
    assert COST_MODELS["exness_gold"].spread_price > 0
    assert COST_MODELS["binance_crypto"].commission_pct > 0


def test_grid_levels_helper() -> None:
    g = GridBotStrategy()
    levels = g.grid_levels(center=100.0)
    assert len(levels["buys"]) == 10
    assert len(levels["sells"]) == 10
    # Buys descend, sells ascend.
    assert levels["buys"][0] > levels["buys"][-1]
    assert levels["sells"][0] < levels["sells"][-1]


def test_risk_manager_circuit_breaker() -> None:
    """Equity drop of 15% from peak should trip the circuit breaker."""
    from risk.manager import RiskManager

    rm = RiskManager(initial_equity=10_000.0)
    rm.on_equity_update(10_000.0)
    rm.on_equity_update(8_400.0)  # -16% DD
    snap = rm.snapshot()
    assert snap["bot_disabled"] is True


def test_position_sizing_caps_at_zero_on_bad_inputs() -> None:
    from risk.position_sizing import (
        fixed_fractional,
        kelly_fractional,
        volatility_target,
    )

    assert fixed_fractional(0, 1, 1) == 0
    assert fixed_fractional(10_000, 0, 1) == 0
    assert fixed_fractional(10_000, 1, 0) == 0
    assert kelly_fractional(0.5, 0, 0) == 0
    assert volatility_target(10_000, 15, 0, 100) == 0
