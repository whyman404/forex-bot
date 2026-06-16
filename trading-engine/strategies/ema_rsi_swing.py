"""EMA12 / EMA26 Crossover + RSI14 (BTC/USDT, H4).

Spec
----
- Long  if EMA12 crosses ABOVE EMA26  AND  RSI14 > 50
- Short if EMA12 crosses BELOW EMA26  AND  RSI14 < 50
- SL: swing low/high over last 10 candles, OR fixed 3% — whichever closer.
- TP: trail with EMA26 (close on cross-back), OR fixed 6% — whichever first.

Realistic expectations
----------------------
- Classic momentum strat on H4 crypto. Win rate ~38–48%.
- 2021-2022 bear market gave many false longs; we add the RSI50 filter.
- Edge decays in low-vol regimes (e.g. summer 2025-style). Monitor.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.base import Strategy


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, 1e-12)
    return 100 - (100 / (1 + rs))


class EMARSISwingStrategy(Strategy):
    name = "EMA12/26 + RSI14 Swing (BTC/USDT H4)"
    symbol = "BTCUSDT"
    asset_class = "crypto"

    default_params: dict[str, Any] = {
        "ema_fast": 12,
        "ema_slow": 26,
        "rsi_period": 14,
        "rsi_threshold": 50.0,
        "swing_lookback": 10,
        "sl_pct_cap": 0.03,    # 3%
        "tp_pct_cap": 0.06,    # 6%
        "use_trailing_ema": True,
    }

    risk_per_trade_pct = 1.0

    # ------------------------------------------------------------------
    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        p = self.params
        df["ema_fast"] = _ema(df["close"], p["ema_fast"])
        df["ema_slow"] = _ema(df["close"], p["ema_slow"])
        df["rsi"] = _rsi(df["close"], p["rsi_period"])
        df["swing_low"] = df["low"].rolling(p["swing_lookback"]).min()
        df["swing_high"] = df["high"].rolling(p["swing_lookback"]).max()
        return df

    # ------------------------------------------------------------------
    def signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = self.prepare(data)
        out = self._empty_signals(df.index)
        p = self.params

        cross_up = (df["ema_fast"] > df["ema_slow"]) & (
            df["ema_fast"].shift(1) <= df["ema_slow"].shift(1)
        )
        cross_down = (df["ema_fast"] < df["ema_slow"]) & (
            df["ema_fast"].shift(1) >= df["ema_slow"].shift(1)
        )

        long_entry = cross_up & (df["rsi"] > p["rsi_threshold"])
        short_entry = cross_down & (df["rsi"] < p["rsi_threshold"])

        # Long
        entries = df.loc[long_entry]
        for ts, row in entries.iterrows():
            entry = row["close"]
            swing_sl = row["swing_low"]
            pct_sl = entry * (1 - p["sl_pct_cap"])
            sl = max(swing_sl, pct_sl) if not pd.isna(swing_sl) else pct_sl
            tp = entry * (1 + p["tp_pct_cap"])
            out.loc[ts] = {
                "direction": 1,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "reason": "ema_cross_up_rsi_gt50",
            }

        # Short
        entries = df.loc[short_entry]
        for ts, row in entries.iterrows():
            entry = row["close"]
            swing_sl = row["swing_high"]
            pct_sl = entry * (1 + p["sl_pct_cap"])
            sl = min(swing_sl, pct_sl) if not pd.isna(swing_sl) else pct_sl
            tp = entry * (1 - p["tp_pct_cap"])
            out.loc[ts] = {
                "direction": -1,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "reason": "ema_cross_down_rsi_lt50",
            }

        return out
