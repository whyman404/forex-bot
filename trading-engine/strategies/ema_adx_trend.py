"""EMA50 + ADX14 Trend (XAU/USD, H1).

Spec
----
- Long  if close > EMA50 AND ADX14 > 25 AND +DI > -DI
- Short if close < EMA50 AND ADX14 > 25 AND -DI > +DI
- SL = ATR14 × 1.5 from entry
- TP = ATR14 × 3.0 (1:2 RR) OR trailing at ATR × 2

Realistic expectations
----------------------
- Win rate 35–45% — classic trend follower. Profit comes from a few
  big winners. Expectancy positive in trending regimes (commodity
  bull-runs, geopolitical risk-on/off).
- Worst regime: choppy, range-bound markets → whipsaws. ADX > 25 helps.
- DO NOT optimize EMA period — overfit factory. 50 is convention; leave it.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from strategies.base import Strategy


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return _true_range(high, low, close).rolling(period).mean()


def _adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (ADX, +DI, -DI) all as percentages."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = _true_range(high, low, close)
    atr = tr.rolling(period).mean()

    plus_di = 100 * pd.Series(plus_dm, index=high.index).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=high.index).rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(period).mean()
    return adx, plus_di, minus_di


class EMA50ADXTrendStrategy(Strategy):
    name = "EMA50 + ADX14 Trend (XAU/USD H1)"
    symbol = "XAUUSD"
    asset_class = "gold"

    default_params: dict[str, Any] = {
        "ema_period": 50,
        "adx_period": 14,
        "adx_threshold": 25.0,
        "atr_period": 14,
        "sl_atr_mult": 1.5,
        "tp_atr_mult": 3.0,
        "use_trailing_atr": False,
        "trail_atr_mult": 2.0,
    }

    risk_per_trade_pct = 1.0

    # ------------------------------------------------------------------
    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        p = self.params
        df["ema"] = _ema(df["close"], p["ema_period"])
        df["atr"] = _atr(df["high"], df["low"], df["close"], p["atr_period"])
        adx, plus_di, minus_di = _adx(df["high"], df["low"], df["close"], p["adx_period"])
        df["adx"] = adx
        df["plus_di"] = plus_di
        df["minus_di"] = minus_di
        return df

    # ------------------------------------------------------------------
    def signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = self.prepare(data)
        out = self._empty_signals(df.index)
        p = self.params

        long_cond = (
            (df["close"] > df["ema"])
            & (df["adx"] > p["adx_threshold"])
            & (df["plus_di"] > df["minus_di"])
        )
        short_cond = (
            (df["close"] < df["ema"])
            & (df["adx"] > p["adx_threshold"])
            & (df["minus_di"] > df["plus_di"])
        )

        # Edge-triggered: enter only on the bar where the condition just
        # turned true (avoid stacking signals).
        long_entry = long_cond & ~long_cond.shift(1).fillna(False)
        short_entry = short_cond & ~short_cond.shift(1).fillna(False)

        sl_mult = p["sl_atr_mult"]
        tp_mult = p["tp_atr_mult"]

        out.loc[long_entry, "direction"] = 1
        out.loc[long_entry, "entry"] = df.loc[long_entry, "close"]
        out.loc[long_entry, "sl"] = (
            df.loc[long_entry, "close"] - sl_mult * df.loc[long_entry, "atr"]
        )
        out.loc[long_entry, "tp"] = (
            df.loc[long_entry, "close"] + tp_mult * df.loc[long_entry, "atr"]
        )
        out.loc[long_entry, "reason"] = "ema50_adx_long"

        out.loc[short_entry, "direction"] = -1
        out.loc[short_entry, "entry"] = df.loc[short_entry, "close"]
        out.loc[short_entry, "sl"] = (
            df.loc[short_entry, "close"] + sl_mult * df.loc[short_entry, "atr"]
        )
        out.loc[short_entry, "tp"] = (
            df.loc[short_entry, "close"] - tp_mult * df.loc[short_entry, "atr"]
        )
        out.loc[short_entry, "reason"] = "ema50_adx_short"

        return out
