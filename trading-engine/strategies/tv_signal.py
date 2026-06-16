"""TradingView Signal Follow strategy.

Mechanics
---------
Live mode (preferred):
    1. At every bar close, query TV multi-TF analysis (15m / 1h / 4h default).
    2. Combine into a single score [-100, +100] via `tradingview.scorer`.
    3. Enter long if score > entry_score_threshold AND ≥ min_agreement_pct TFs agree.
    4. Enter short if score < -entry_score_threshold AND ≥ min_agreement_pct TFs agree.
    5. SL/TP via ATR (default 1.5×/3×).
    6. Cool-down (default 60 min) prevents immediate re-entry after exit.

Backtest mode (proxy):
    `tradingview-ta` returns LIVE recommendations only — there is NO
    historical replay API. So when running offline (no TV client injected
    OR TV_ENABLED=false), we compute a PROXY recommendation from local
    indicators (RSI + EMA cross) on the historical bars.

    **The backtest is an APPROXIMATION — live signals WILL differ.**
    This is documented in `docs/strategies/tv-signal.md` and surfaced
    in the strategy `describe()` output so the UI can warn users.

Parameters
----------
- tv_symbol / tv_exchange : optional override; auto-resolved from `symbol`
- intervals               : list of TF strings, default ['15m','1h','4h']
- entry_score_threshold   : default 60  — score above this triggers entry
- exit_score_threshold    : default 20  — score below this triggers exit (looser)
- sl_atr_mult             : default 1.5
- tp_atr_mult             : default 3.0
- min_agreement_pct       : default 0.6
- cool_down_min           : default 60  — minutes between exits and next entry
- atr_period              : default 14
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from strategies.base import Strategy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Indicators (local)
# ---------------------------------------------------------------------------
def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return _true_range(high, low, close).rolling(period).mean()


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------
class TVSignalStrategy(Strategy):
    """Follow TradingView multi-timeframe recommendation with ATR risk.

    Use in LIVE mode by setting `tv_client` via `set_tv_client()` before the
    engine calls `signals()`. In backtest, leave `tv_client = None` — the
    strategy falls back to its local proxy (RSI + EMA cross).
    """

    name = "TradingView Signal Follow"
    symbol = "XAUUSD"               # overridden via params at instantiation
    asset_class = "multi"

    default_params: dict[str, Any] = {
        # Symbol overrides (auto-resolved if blank)
        "tv_symbol": "",
        "tv_exchange": "",
        # TF list — top-3 mid-frame default. UI may extend to 5.
        "intervals": ["15m", "1h", "4h"],
        # Score gating
        "entry_score_threshold": 60.0,
        "exit_score_threshold": 20.0,
        "min_agreement_pct": 0.6,
        # Risk
        "sl_atr_mult": 1.5,
        "tp_atr_mult": 3.0,
        "atr_period": 14,
        # Cool-down between trades (minutes)
        "cool_down_min": 60,
        # Screener — TV needs this to disambiguate (forex/crypto/america)
        "tv_screener": "forex",
    }

    risk_per_trade_pct = 1.0

    # ------------------------------------------------------------------
    def __init__(self, params: dict[str, Any] | None = None) -> None:
        super().__init__(params)
        self._tv_client: Any | None = None
        self._scorer: Any | None = None
        self._last_exit_ts: pd.Timestamp | None = None
        self._last_score: float | None = None
        self._last_per_tf: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Wiring (called by LiveEngine before each signal call)
    # ------------------------------------------------------------------
    def set_tv_client(self, client: Any, scorer: Any | None = None) -> None:
        """Inject a live TV client + scorer. Engine-only.

        Backtest leaves these None → proxy path is used.
        """
        self._tv_client = client
        if scorer is not None:
            self._scorer = scorer
        else:
            # Lazy import — keeps backtest path TV-free.
            from tradingview.scorer import Scorer

            self._scorer = Scorer()

    # ------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        d = super().describe()
        d.update(
            {
                "mode_hint": "live" if self._tv_client is not None else "backtest_proxy",
                "backtest_caveat": (
                    "Backtest uses a local RSI+EMA proxy because tradingview-ta "
                    "returns LIVE recommendations only. Live signals will differ."
                ),
            }
        )
        return d

    # ------------------------------------------------------------------
    # Backtest path: compute proxy from local indicators
    # ------------------------------------------------------------------
    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        p = self.params
        df["ema_fast"] = _ema(df["close"], 12)
        df["ema_slow"] = _ema(df["close"], 26)
        df["rsi"] = _rsi(df["close"], 14)
        df["atr"] = _atr(df["high"], df["low"], df["close"], int(p["atr_period"]))

        # Proxy "TV-like" score in [-100, +100].
        # Components: EMA cross sign, EMA slope, RSI distance from 50.
        ema_cross = np.sign(df["ema_fast"] - df["ema_slow"])           # -1/0/+1
        ema_slope = np.sign(df["ema_fast"].diff().fillna(0.0))         # -1/0/+1
        rsi_norm = (df["rsi"] - 50.0) / 50.0                            # [-1, +1]

        # Weighted blend → [-100, +100].
        proxy = (
            0.5 * ema_cross
            + 0.3 * ema_slope
            + 0.2 * rsi_norm
        ) * 100.0
        df["tv_score_proxy"] = proxy.clip(-100, 100)
        return df

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------
    def signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Return signals frame.

        Two code paths:
          - LIVE: only the LAST bar gets a signal (engine reacts per bar close).
            We fetch TV at this moment — the prior history is not relevant.
          - BACKTEST: every bar uses the proxy score.

        Schema is identical so the runner / engine don't branch.
        """
        df = self.prepare(data)
        out = self._empty_signals(df.index)
        if len(df) == 0:
            return out

        if self._tv_client is not None and self._scorer is not None:
            # ---- LIVE PATH ----
            try:
                self._fill_live_signal_last_row(df, out)
            except Exception as e:
                # Don't crash the engine — log and emit no signal.
                logger.warning("tv_signal.live_fetch_failed err=%s", str(e)[:200])
            return out

        # ---- BACKTEST PROXY PATH ----
        self._fill_proxy_signals(df, out)
        return out

    # ------------------------------------------------------------------
    def _resolve_symbol(self) -> tuple[str, str, str]:
        """Return (tv_symbol, tv_exchange, screener) — using overrides if set."""
        from tradingview.symbols import resolve_symbol

        p = self.params
        if p.get("tv_symbol"):
            tv_sym = p["tv_symbol"]
            tv_ex = p.get("tv_exchange") or "OANDA"
            screener = p.get("tv_screener") or "forex"
            return tv_sym, tv_ex, screener
        resolved = resolve_symbol(self.symbol)
        screener_map = {"forex": "forex", "gold": "forex", "crypto": "crypto"}
        return (
            resolved.symbol,
            resolved.exchange,
            screener_map.get(resolved.asset_class, "forex"),
        )

    # ------------------------------------------------------------------
    def _fill_live_signal_last_row(
        self, df: pd.DataFrame, out: pd.DataFrame
    ) -> None:
        p = self.params
        tv_sym, tv_ex, screener = self._resolve_symbol()

        analyses = []
        for iv in p["intervals"]:
            try:
                a = self._tv_client.get_analysis(
                    tv_sym, tv_ex, iv, screener=screener
                )
                analyses.append(a)
            except Exception as e:
                logger.info("tv_signal.tf_skip interval=%s err=%s", iv, str(e)[:120])

        if not analyses:
            return

        combined = self._scorer.score(analyses)
        score = float(combined.score)
        agreement = float(combined.agreement_pct)
        self._last_score = score
        self._last_per_tf = combined.per_tf

        # Cool-down check
        if self._in_cool_down(df.index[-1]):
            return

        bar = df.iloc[-1]
        entry = float(bar["close"])
        atr = float(bar["atr"]) if not pd.isna(bar["atr"]) else 0.0
        if atr <= 0.0:
            return

        threshold = float(p["entry_score_threshold"])
        min_agree = float(p["min_agreement_pct"])
        sl_mult = float(p["sl_atr_mult"])
        tp_mult = float(p["tp_atr_mult"])

        per_tf_summary = ",".join(
            f"{pt['interval']}:{pt['recommendation']}" for pt in combined.per_tf
        )

        if score >= threshold and agreement >= min_agree:
            out.iat[-1, out.columns.get_loc("direction")] = 1
            out.iat[-1, out.columns.get_loc("entry")] = entry
            out.iat[-1, out.columns.get_loc("sl")] = entry - sl_mult * atr
            out.iat[-1, out.columns.get_loc("tp")] = entry + tp_mult * atr
            out.iat[-1, out.columns.get_loc("reason")] = (
                f"tv_long score={score:.1f} agree={agreement:.2f} "
                f"tfs=[{per_tf_summary}]"
            )[:120]
        elif score <= -threshold and agreement >= min_agree:
            out.iat[-1, out.columns.get_loc("direction")] = -1
            out.iat[-1, out.columns.get_loc("entry")] = entry
            out.iat[-1, out.columns.get_loc("sl")] = entry + sl_mult * atr
            out.iat[-1, out.columns.get_loc("tp")] = entry - tp_mult * atr
            out.iat[-1, out.columns.get_loc("reason")] = (
                f"tv_short score={score:.1f} agree={agreement:.2f} "
                f"tfs=[{per_tf_summary}]"
            )[:120]

    # ------------------------------------------------------------------
    def _fill_proxy_signals(self, df: pd.DataFrame, out: pd.DataFrame) -> None:
        """Backtest-only — vectorized over the whole frame.

        Edge-triggered so we don't stack signals while score stays above
        threshold. SL/TP from ATR identical to the live path.
        """
        p = self.params
        threshold = float(p["entry_score_threshold"])
        sl_mult = float(p["sl_atr_mult"])
        tp_mult = float(p["tp_atr_mult"])

        score = df["tv_score_proxy"]
        long_cond = score >= threshold
        short_cond = score <= -threshold
        long_entry = long_cond & ~long_cond.shift(1).fillna(False)
        short_entry = short_cond & ~short_cond.shift(1).fillna(False)

        long_entry = long_entry & df["atr"].notna() & (df["atr"] > 0)
        short_entry = short_entry & df["atr"].notna() & (df["atr"] > 0)

        out.loc[long_entry, "direction"] = 1
        out.loc[long_entry, "entry"] = df.loc[long_entry, "close"]
        out.loc[long_entry, "sl"] = (
            df.loc[long_entry, "close"] - sl_mult * df.loc[long_entry, "atr"]
        )
        out.loc[long_entry, "tp"] = (
            df.loc[long_entry, "close"] + tp_mult * df.loc[long_entry, "atr"]
        )
        out.loc[long_entry, "reason"] = "tv_long_proxy"

        out.loc[short_entry, "direction"] = -1
        out.loc[short_entry, "entry"] = df.loc[short_entry, "close"]
        out.loc[short_entry, "sl"] = (
            df.loc[short_entry, "close"] + sl_mult * df.loc[short_entry, "atr"]
        )
        out.loc[short_entry, "tp"] = (
            df.loc[short_entry, "close"] - tp_mult * df.loc[short_entry, "atr"]
        )
        out.loc[short_entry, "reason"] = "tv_short_proxy"

    # ------------------------------------------------------------------
    def _in_cool_down(self, now: pd.Timestamp) -> bool:
        if self._last_exit_ts is None:
            return False
        try:
            elapsed_min = (now - self._last_exit_ts).total_seconds() / 60.0
            return elapsed_min < float(self.params["cool_down_min"])
        except Exception:
            return False

    def mark_exit(self, ts: pd.Timestamp) -> None:
        """Called by the engine when a position closes — starts cool-down."""
        self._last_exit_ts = ts

    # ------------------------------------------------------------------
    def last_diagnostics(self) -> dict[str, Any]:
        """Expose latest TV state for monitoring / debug."""
        return {
            "last_score": self._last_score,
            "last_per_tf": self._last_per_tf,
            "in_cool_down": self._in_cool_down(pd.Timestamp.utcnow()),
            "last_exit_ts": (
                self._last_exit_ts.isoformat() if self._last_exit_ts is not None else None
            ),
        }
