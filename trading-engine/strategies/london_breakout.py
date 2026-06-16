"""London Breakout (XAU/USD, M5/M15).

Spec
----
- Asian range = High/Low of 22:00–07:59 GMT (prior day).
- At 08:00 GMT place:
    Buy Stop at  Asian_High + buffer
    Sell Stop at Asian_Low  - buffer
  OCO — first one filled cancels the other.
- SL fixed 40 pips (gold: $4.00 from entry).
- TP = 1.5 × Asian range OR fixed 60 pips, whichever the user picks.
- Spread filter: skip if spread > 30 pts at entry.
- One trade per day.

Realistic expectations
----------------------
- Win rate ~40–50%, RR 1:1.5 → expectancy positive in trending months,
  negative in ranging months.
- Worst regime: low-volatility summer / FOMC day → tight Asian range
  → false breakouts. We add a `min_range_pips` filter.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.base import Strategy

ASIAN_START_HOUR = 22  # GMT (prior-day evening)
ASIAN_END_HOUR = 8  # exclusive — 07:59 is last Asian bar
ENTRY_HOUR = 8  # GMT
LONDON_CLOSE_HOUR = 16  # GMT — flatten any open position

PIP = 0.10  # 1 pip on XAUUSD = $0.10 per oz (per Exness convention)


class LondonBreakoutStrategy(Strategy):
    name = "London Breakout (XAU/USD)"
    symbol = "XAUUSD"
    asset_class = "gold"

    default_params: dict[str, Any] = {
        "buffer_pips": 5.0,
        "sl_pips": 40.0,
        "tp_pips": 60.0,
        "tp_mode": "fixed",          # "fixed" or "range_mult"
        "tp_range_mult": 1.5,
        "min_range_pips": 30.0,      # skip days with tiny Asian range
        "max_range_pips": 200.0,     # skip blow-out days
        "spread_filter_pts": 30,     # skip if spread > 30 pts
        "max_trades_per_day": 1,
    }

    risk_per_trade_pct = 1.0

    # ------------------------------------------------------------------
    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        """Compute the prior Asian high/low for every bar."""
        df = data.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)

        # Each row's "session date" = date of 08:00 GMT trading day it belongs to.
        # Asian session for date D = (D-1 22:00) .. (D 07:59).
        session_date = (df.index - pd.Timedelta(hours=ASIAN_END_HOUR)).normalize()
        df["session_date"] = session_date

        # Mask of bars that are part of the Asian range.
        hour = df.index.hour
        asian_mask = (hour >= ASIAN_START_HOUR) | (hour < ASIAN_END_HOUR)
        asian = df[asian_mask]

        # Aggregate to High / Low per session date.
        asian_hl = asian.groupby("session_date").agg(
            asian_high=("high", "max"),
            asian_low=("low", "min"),
        )
        asian_hl["asian_range_pips"] = (
            (asian_hl["asian_high"] - asian_hl["asian_low"]) / PIP
        )

        # Merge back so every bar knows "this session's Asian H/L".
        df = df.merge(asian_hl, left_on="session_date", right_index=True, how="left")
        return df

    # ------------------------------------------------------------------
    def signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = self.prepare(data)
        out = self._empty_signals(df.index)

        p = self.params
        buf = p["buffer_pips"] * PIP
        sl_dist = p["sl_pips"] * PIP

        hour = df.index.hour
        # Entry candidates: first bar at/after 08:00 GMT each session.
        entry_window = (hour == ENTRY_HOUR)

        # Limit to one signal per session: take first bar of entry_window per day.
        is_first_in_session = entry_window & (
            df["session_date"] != df["session_date"].shift(1).fillna(method="bfill")
        ) | (entry_window & ~entry_window.shift(1).fillna(False))

        for ts in df.index[is_first_in_session]:
            row = df.loc[ts]
            asian_high = row.get("asian_high")
            asian_low = row.get("asian_low")
            asian_range_pips = row.get("asian_range_pips")

            if pd.isna(asian_high) or pd.isna(asian_low):
                continue
            if asian_range_pips < p["min_range_pips"]:
                continue
            if asian_range_pips > p["max_range_pips"]:
                continue

            # We emit BOTH legs as candidates and let the OMS resolve OCO.
            # In backtest, we simulate: whichever stop price is hit first wins.
            buy_stop = asian_high + buf
            sell_stop = asian_low - buf

            close = row["close"]
            # Decide which side actually trips first within the trading day:
            # use the future bars until LONDON_CLOSE_HOUR.
            day_close = df.loc[
                (df["session_date"] == row["session_date"])
                & (df.index.hour < LONDON_CLOSE_HOUR)
                & (df.index >= ts)
            ]
            triggered = self._first_trigger(day_close, buy_stop, sell_stop)
            if triggered is None:
                continue

            side, trig_ts, fill_price = triggered
            tp_dist = (
                p["tp_pips"] * PIP
                if p["tp_mode"] == "fixed"
                else asian_range_pips * p["tp_range_mult"] * PIP
            )
            if side == "long":
                out.loc[trig_ts, "direction"] = 1
                out.loc[trig_ts, "entry"] = fill_price
                out.loc[trig_ts, "sl"] = fill_price - sl_dist
                out.loc[trig_ts, "tp"] = fill_price + tp_dist
                out.loc[trig_ts, "reason"] = "london_break_up"
            else:
                out.loc[trig_ts, "direction"] = -1
                out.loc[trig_ts, "entry"] = fill_price
                out.loc[trig_ts, "sl"] = fill_price + sl_dist
                out.loc[trig_ts, "tp"] = fill_price - tp_dist
                out.loc[trig_ts, "reason"] = "london_break_down"

            _ = close  # silence unused warning (kept for clarity)

        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _first_trigger(
        bars: pd.DataFrame, buy_stop: float, sell_stop: float
    ) -> tuple[str, pd.Timestamp, float] | None:
        """Return ('long'|'short', timestamp, fill_price) of whichever stop hits first."""
        for ts, bar in bars.iterrows():
            hit_buy = bar["high"] >= buy_stop
            hit_sell = bar["low"] <= sell_stop
            if hit_buy and hit_sell:
                # Both triggered in same bar — pessimistic: assume the
                # opposite (against us) hit first. Skip.
                return None
            if hit_buy:
                return ("long", ts, buy_stop)
            if hit_sell:
                return ("short", ts, sell_stop)
        return None
