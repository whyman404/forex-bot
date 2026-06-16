"""Backtest runner.

Consumes a `Strategy` + OHLCV `DataFrame` and returns a metrics dict.

Design notes
------------
- We prefer vectorbt for speed, but we also support a pure-pandas fallback so
  unit tests pass even when vectorbt isn't installed.
- Costs (spread + commission + slippage) are first-class. A backtest without
  costs is a lie. Defaults per asset class are in `COST_MODELS`.
- We compute industry-standard metrics: profit factor, Sharpe (annualized),
  Sortino, max drawdown, expectancy, win rate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategies.base import Strategy

# Try vectorbt — degrade gracefully on machines without it.
try:
    import vectorbt as vbt  # noqa: F401  (presence detection only)

    _VBT_AVAILABLE = True
except Exception:  # pragma: no cover
    _VBT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Cost models
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CostModel:
    """Per round-trip cost model."""

    # All in PRICE terms (not pips, not pct), applied symmetrically.
    spread_price: float = 0.0
    slippage_price: float = 0.0
    # Commission as a fraction of notional (taker fee).
    commission_pct: float = 0.0


# These are realistic Exness Gold / Binance VIP-0 numbers as of mid-2026.
COST_MODELS: dict[str, CostModel] = {
    "exness_gold": CostModel(
        spread_price=0.20,       # 20 pts ≈ $0.20 on XAUUSD
        slippage_price=0.05,     # 0.5 pip avg slippage
        commission_pct=0.0,
    ),
    "binance_crypto": CostModel(
        spread_price=0.0,        # included in fee
        slippage_price=0.0,
        commission_pct=0.0005,   # 0.05% taker
    ),
    "zero": CostModel(),         # for unit tests
}


def cost_model_for(strategy: Strategy) -> CostModel:
    """Pick a sensible default based on the strategy's asset_class."""
    if strategy.asset_class in ("gold", "forex"):
        return COST_MODELS["exness_gold"]
    if strategy.asset_class == "crypto":
        return COST_MODELS["binance_crypto"]
    return COST_MODELS["zero"]


# ---------------------------------------------------------------------------
# Trade simulation (event-driven over signals)
# ---------------------------------------------------------------------------
def _simulate_trades(
    data: pd.DataFrame,
    sigs: pd.DataFrame,
    cost: CostModel,
) -> pd.DataFrame:
    """Walk the bars; for each non-zero signal, open a position, exit on SL/TP/end.

    Returns a per-trade DataFrame with columns
        ['entry_ts', 'exit_ts', 'direction', 'entry', 'exit', 'pnl', 'r_multiple']

    Simplified assumptions:
      - We do NOT pyramid. If a new signal fires while in a trade, we ignore it.
      - Exits checked intra-bar via high/low; if both SL and TP touched in same
        bar, assume SL hits first (pessimistic).
      - Position size = 1 unit; PnL in price terms, scaled later by sizing.
    """
    trades: list[dict[str, Any]] = []
    in_trade = False
    entry_price = 0.0
    sl = 0.0
    tp = 0.0
    direction = 0
    entry_ts: pd.Timestamp | None = None

    for ts, bar in data.iterrows():
        if in_trade:
            high = bar["high"]
            low = bar["low"]
            exit_price: float | None = None
            if direction > 0:
                if low <= sl:
                    exit_price = sl - cost.slippage_price
                elif high >= tp:
                    exit_price = tp - cost.slippage_price
            else:
                if high >= sl:
                    exit_price = sl + cost.slippage_price
                elif low <= tp:
                    exit_price = tp + cost.slippage_price

            if exit_price is not None:
                gross = (exit_price - entry_price) * direction
                cost_total = cost.spread_price + cost.commission_pct * (
                    entry_price + exit_price
                )
                pnl = gross - cost_total
                r = abs(entry_price - sl)  # initial risk
                r_multiple = pnl / r if r > 0 else 0.0
                trades.append(
                    {
                        "entry_ts": entry_ts,
                        "exit_ts": ts,
                        "direction": direction,
                        "entry": entry_price,
                        "exit": exit_price,
                        "pnl": pnl,
                        "r_multiple": r_multiple,
                    }
                )
                in_trade = False
                continue

        if not in_trade:
            sig = sigs.loc[ts] if ts in sigs.index else None
            if sig is None:
                continue
            d = int(sig["direction"])
            if d == 0:
                continue
            direction = d
            entry_price = float(sig["entry"]) + cost.slippage_price * (1 if d > 0 else -1)
            sl = float(sig["sl"])
            tp = float(sig["tp"])
            entry_ts = ts
            in_trade = True

    return pd.DataFrame(
        trades,
        columns=["entry_ts", "exit_ts", "direction", "entry", "exit", "pnl", "r_multiple"],
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _annualization_factor(index: pd.DatetimeIndex) -> float:
    """Approximate bars-per-year for the given index spacing."""
    if len(index) < 2:
        return 252.0
    delta = (index[-1] - index[0]).total_seconds()
    if delta <= 0:
        return 252.0
    bars_per_sec = (len(index) - 1) / delta
    seconds_per_year = 365.25 * 24 * 3600
    return bars_per_sec * seconds_per_year


def _equity_curve(trades: pd.DataFrame, index: pd.DatetimeIndex, start_eq: float = 10_000.0) -> pd.Series:
    eq = pd.Series(start_eq, index=index, dtype=float)
    for _, t in trades.iterrows():
        eq.loc[t["exit_ts"]:] += t["pnl"]
    return eq


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(dd.min()) if len(dd) else 0.0


def _compute_metrics(trades: pd.DataFrame, equity: pd.Series) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy_r": 0.0,
            "total_return_pct": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown_pct": 0.0,
        }

    wins = trades[trades["pnl"] > 0]["pnl"]
    losses = trades[trades["pnl"] <= 0]["pnl"]
    gross_win = wins.sum()
    gross_loss = -losses.sum()

    win_rate = len(wins) / n
    pf = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")
    expectancy_r = float(trades["r_multiple"].mean())

    returns = equity.pct_change().fillna(0.0)
    ann = _annualization_factor(equity.index)
    sharpe = (
        float(returns.mean() / returns.std() * np.sqrt(ann))
        if returns.std() > 0
        else 0.0
    )
    downside = returns[returns < 0]
    sortino = (
        float(returns.mean() / downside.std() * np.sqrt(ann))
        if len(downside) > 0 and downside.std() > 0
        else 0.0
    )

    return {
        "total_trades": int(n),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(pf, 4),
        "expectancy_r": round(expectancy_r, 4),
        "total_return_pct": round((equity.iloc[-1] / equity.iloc[0] - 1) * 100, 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "max_drawdown_pct": round(_max_drawdown(equity) * 100, 4),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_backtest(
    strategy: Strategy,
    data: pd.DataFrame,
    cost_model: str | CostModel | None = None,
    initial_equity: float = 10_000.0,
) -> dict[str, Any]:
    """Run a backtest of `strategy` on `data`.

    Args:
        strategy: instance of a Strategy subclass.
        data: OHLCV DataFrame indexed by tz-aware DatetimeIndex.
        cost_model: a key into COST_MODELS, a CostModel instance, or None
            (auto-pick based on strategy.asset_class).
        initial_equity: starting balance.

    Returns:
        dict with keys:
            - 'summary': dict of metrics
            - 'trades': trades DataFrame
            - 'equity_curve': equity Series
            - 'signals': raw signals DataFrame
            - 'meta': strategy.describe()
    """
    if not isinstance(data.index, pd.DatetimeIndex):
        data = data.copy()
        data.index = pd.to_datetime(data.index, utc=True)

    if cost_model is None:
        cost = cost_model_for(strategy)
    elif isinstance(cost_model, str):
        cost = COST_MODELS[cost_model]
    else:
        cost = cost_model

    sigs = strategy.signals(data)
    trades = _simulate_trades(data, sigs, cost)
    equity = _equity_curve(trades, data.index, initial_equity)
    metrics = _compute_metrics(trades, equity)

    return {
        "summary": metrics,
        "trades": trades,
        "equity_curve": equity,
        "signals": sigs,
        "meta": strategy.describe(),
    }
