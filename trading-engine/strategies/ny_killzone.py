"""NY Killzone Reversal (XAU/USD, M5).

Spec
----
- Trade window: 13:30–16:00 GMT (NY open + first 2.5h).
- Setup: price sweeps Asian session High OR Low (defined as 22:00–07:59 GMT
  prior session), then an M5 candle CLOSES back inside the Asian range
  → enter in the opposite direction (reversal).
- SL: 30 pips beyond the swept extreme.
- TP: 60 pips (1:2 RR).

Realistic expectations
----------------------
- Lower frequency than London (some days no sweep happens).
- Win rate 45–55%, expectancy positive if filters are honored.
- Failure mode: news-driven trend day → sweep keeps going.
  Disable on FOMC / NFP days (handled by external calendar filter).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.base import Strategy

ASIAN_START_HOUR = 22
ASIAN_END_HOUR = 8
NY_WINDOW_START_HOUR = 13
NY_WINDOW_START_MIN = 30
NY_WINDOW_END_HOUR = 16

PIP = 0.10  # XAUUSD


class NYKillzoneReversalStrategy(Strategy):
    name = "NY Killzone Reversal (XAU/USD)"
    symbol = "XAUUSD"
    asset_class = "gold"

    default_params: dict[str, Any] = {
        "sl_pips": 30.0,
        "tp_pips": 60.0,
        "max_trades_per_day": 1,
        "spread_filter_pts": 30,
    }

    risk_per_trade_pct = 1.0

    # ------------------------------------------------------------------
    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)

        session_date = (df.index - pd.Timedelta(hours=ASIAN_END_HOUR)).normalize()
        df["session_date"] = session_date

        hour = df.index.hour
        asian_mask = (hour >= ASIAN_START_HOUR) | (hour < ASIAN_END_HOUR)
        asian = df[asian_mask]
        asian_hl = asian.groupby("session_date").agg(
            asian_high=("high", "max"),
            asian_low=("low", "min"),
        )
        df = df.merge(asian_hl, left_on="session_date", right_index=True, how="left")

        # In-NY-window flag.
        in_ny = (
            (
                (df.index.hour == NY_WINDOW_START_HOUR)
                & (df.index.minute >= NY_WINDOW_START_MIN)
            )
            | ((df.index.hour > NY_WINDOW_START_HOUR) & (df.index.hour < NY_WINDOW_END_HOUR))
        )
        df["in_ny_window"] = in_ny
        return df

    # ------------------------------------------------------------------
    def signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = self.prepare(data)
        out = self._empty_signals(df.index)

        p = self.params
        sl_dist = p["sl_pips"] * PIP
        tp_dist = p["tp_pips"] * PIP

        # Track which session already had a trade.
        traded_sessions: set[pd.Timestamp] = set()

        for ts, row in df.iterrows():
            if not row.get("in_ny_window", False):
                continue
            sess = row["session_date"]
            if sess in traded_sessions:
                continue

            asian_high = row.get("asian_high")
            asian_low = row.get("asian_low")
            if pd.isna(asian_high) or pd.isna(asian_low):
                continue

            high, low, close = row["high"], row["low"], row["close"]

            # Sweep high → close back below: SHORT.
            if high > asian_high and close < asian_high:
                out.loc[ts, "direction"] = -1
                out.loc[ts, "entry"] = close
                out.loc[ts, "sl"] = high + sl_dist
                out.loc[ts, "tp"] = close - tp_dist
                out.loc[ts, "reason"] = "ny_sweep_high_reversal"
                traded_sessions.add(sess)
                continue

            # Sweep low → close back above: LONG.
            if low < asian_low and close > asian_low:
                out.loc[ts, "direction"] = 1
                out.loc[ts, "entry"] = close
                out.loc[ts, "sl"] = low - sl_dist
                out.loc[ts, "tp"] = close + tp_dist
                out.loc[ts, "reason"] = "ny_sweep_low_reversal"
                traded_sessions.add(sess)

        return out
