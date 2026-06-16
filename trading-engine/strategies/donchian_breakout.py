"""Donchian Channel Breakout (BTC/USDT, H1) — Turtle-style.

Spec
----
- Entry: close > Donchian(20).upper → LONG; close < Donchian(20).lower → SHORT.
- Exit: close crosses Donchian(10) opposite (10-period exit channel).
- SL: opposite side of Donchian(10) (Turtle rule).
- Risk: 2% per trade (we let the runner / risk manager size).

Realistic expectations
----------------------
- Trend-following — wins big, loses small. Win rate 30–40%. Sharpe 0.6–1.0
  depending on regime. Heavy 2024-2025 BTC trends were kind to this.
- Worst regime: prolonged range. Expect 6+ consecutive losers. Do not
  abandon during DD without retesting.

Reference: Curtis Faith — Way of the Turtle.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.base import Strategy


class DonchianBreakoutStrategy(Strategy):
    name = "Donchian Breakout (BTC/USDT H1)"
    symbol = "BTCUSDT"
    asset_class = "crypto"

    default_params: dict[str, Any] = {
        "entry_period": 20,
        "exit_period": 10,
        "risk_per_trade_pct": 2.0,
    }

    @property
    def risk_per_trade_pct(self) -> float:  # type: ignore[override]
        return self.params["risk_per_trade_pct"]

    @risk_per_trade_pct.setter
    def risk_per_trade_pct(self, value: float) -> None:
        self.params["risk_per_trade_pct"] = value

    # ------------------------------------------------------------------
    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        p = self.params
        # Donchian computed on PREVIOUS bars only (avoid look-ahead).
        df["donc_up"] = df["high"].shift(1).rolling(p["entry_period"]).max()
        df["donc_lo"] = df["low"].shift(1).rolling(p["entry_period"]).min()
        df["exit_up"] = df["high"].shift(1).rolling(p["exit_period"]).max()
        df["exit_lo"] = df["low"].shift(1).rolling(p["exit_period"]).min()
        return df

    # ------------------------------------------------------------------
    def signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = self.prepare(data)
        out = self._empty_signals(df.index)

        long_break = df["close"] > df["donc_up"]
        short_break = df["close"] < df["donc_lo"]

        # Edge-trigger: only on the bar that just broke.
        long_entry = long_break & ~long_break.shift(1).fillna(False)
        short_entry = short_break & ~short_break.shift(1).fillna(False)

        # SL = opposite Donchian(exit) at entry time.
        out.loc[long_entry, "direction"] = 1
        out.loc[long_entry, "entry"] = df.loc[long_entry, "close"]
        out.loc[long_entry, "sl"] = df.loc[long_entry, "exit_lo"]
        # No fixed TP — trailing handled by runner via exit channel.
        # We pre-fill a generous TP just so DataFrame schema is consistent.
        out.loc[long_entry, "tp"] = df.loc[long_entry, "close"] * 1.50
        out.loc[long_entry, "reason"] = "donchian_break_up"

        out.loc[short_entry, "direction"] = -1
        out.loc[short_entry, "entry"] = df.loc[short_entry, "close"]
        out.loc[short_entry, "sl"] = df.loc[short_entry, "exit_up"]
        out.loc[short_entry, "tp"] = df.loc[short_entry, "close"] * 0.50
        out.loc[short_entry, "reason"] = "donchian_break_down"

        return out
