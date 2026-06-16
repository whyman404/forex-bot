"""Grid Bot (BTC/USDT, M15/H1).

Spec
----
- Center anchor: Daily VWAP OR EMA50 (configurable).
- 10 BUY levels below center, 10 SELL levels above. Spacing: 1.0% per level.
- Each filled level has TP = +1.0% (the next grid line).
- HARD STOP at center − 15% (longs) or center + 15% (shorts) — close ALL
  positions and stop bot. This is the non-negotiable rule.
- Re-anchor center daily (00:00 UTC).

WARNING
-------
- Grid bots feel safe because of high win rate (95%+). But the un-closed
  inventory in a strong trend can blow the account. The hard SL is what
  prevents the ticking bomb.
- This strategy module returns "grid intentions" — actual fill simulation
  belongs to the runner / paper broker. The signals() output is a sparse
  ladder describing where to place orders, not single entry signals.

Realistic expectations
----------------------
- 95% win rate per leg, BUT:
    * Expectancy positive only in mean-reverting regimes.
    * Single trend day can give losses larger than 1 month of grid profits.
- Use only on instruments + timeframes where you have evidence of mean
  reversion. NOT for trending altcoins.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from strategies.base import Strategy


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _daily_vwap(df: pd.DataFrame) -> pd.Series:
    """Rolling daily VWAP, recomputed each UTC day."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)
    day = df.index.normalize()
    num = (typical * vol).groupby(day).cumsum()
    den = vol.groupby(day).cumsum().replace(0, np.nan)
    return num / den


class GridBotStrategy(Strategy):
    name = "Grid Bot (BTC/USDT)"
    symbol = "BTCUSDT"
    asset_class = "crypto"

    default_params: dict[str, Any] = {
        "center_mode": "vwap",          # "vwap" or "ema50"
        "ema_period": 50,
        "n_levels": 10,                 # levels per side
        "spacing_pct": 0.01,            # 1.0%
        "tp_pct": 0.01,                 # 1.0%
        "hard_sl_pct": 0.15,            # 15% from center → kill switch
        "rebalance_hourly": False,
    }

    risk_per_trade_pct = 0.5  # per-leg; the *position* is many legs

    # ------------------------------------------------------------------
    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        p = self.params
        if p["center_mode"] == "ema50":
            df["center"] = _ema(df["close"], p["ema_period"])
        else:
            df["center"] = _daily_vwap(df)
        df["hard_sl_long"] = df["center"] * (1 - p["hard_sl_pct"])
        df["hard_sl_short"] = df["center"] * (1 + p["hard_sl_pct"])
        return df

    # ------------------------------------------------------------------
    def signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Emit per-bar grid ladders.

        Output schema differs slightly: each emitted row's `reason` field
        encodes the ladder as JSON-ish string the runner can parse. For
        simplicity here, we emit ONE row per session change (when the center
        re-anchors) with `direction=0` (it's not a single trade), and use
        `entry` to record the center price, `sl` to record the hard kill.

        The runner / paper broker is responsible for translating this into
        N buy-limit + N sell-limit orders.
        """
        df = self.prepare(data)
        out = self._empty_signals(df.index)
        p = self.params

        day = df.index.normalize()
        is_first_in_day = day != pd.Series(day, index=df.index).shift(1)

        for ts in df.index[is_first_in_day]:
            row = df.loc[ts]
            center = row["center"]
            if pd.isna(center):
                continue
            out.loc[ts, "direction"] = 0  # ladder, not directional
            out.loc[ts, "entry"] = center
            # Encode both kill switches into sl/tp.
            out.loc[ts, "sl"] = row["hard_sl_long"]
            out.loc[ts, "tp"] = row["hard_sl_short"]
            out.loc[ts, "reason"] = (
                f"grid_anchor:center={center:.2f},"
                f"levels={p['n_levels']},spacing={p['spacing_pct']:.4f},"
                f"tp={p['tp_pct']:.4f},hard_sl={p['hard_sl_pct']:.4f}"
            )

        return out

    # ------------------------------------------------------------------
    def grid_levels(self, center: float) -> dict[str, list[float]]:
        """Helper: compute the N buy + N sell levels from a center price."""
        p = self.params
        n = p["n_levels"]
        sp = p["spacing_pct"]
        buys = [center * (1 - sp * i) for i in range(1, n + 1)]
        sells = [center * (1 + sp * i) for i in range(1, n + 1)]
        return {"buys": buys, "sells": sells}
