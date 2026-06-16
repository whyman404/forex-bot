"""Walk-forward analysis.

Splits the OHLCV history into rolling (in-sample, out-of-sample) windows,
runs the strategy on each, and reports the per-window metrics plus a
"parameter stability" summary (mean / std of each metric).

This is one of the most important sanity checks against overfitting.
Backtests that look great in-sample but degrade in out-of-sample are a
red flag we will not ignore.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from backtest.runner import run_backtest
from strategies.base import Strategy


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def _build_windows(
    index: pd.DatetimeIndex, n_splits: int, train_ratio: float
) -> list[WalkForwardWindow]:
    """Build rolling windows that cover the whole index."""
    total = len(index)
    if total < n_splits * 10:
        # Not enough data; return one window.
        return [
            WalkForwardWindow(index[0], index[-1], index[0], index[-1]),
        ]

    step = total // n_splits
    train_len = int(step * train_ratio)
    test_len = step - train_len
    windows: list[WalkForwardWindow] = []
    for i in range(n_splits):
        start = i * step
        train_s = index[start]
        train_e_idx = min(start + train_len - 1, total - 1)
        test_s_idx = train_e_idx + 1
        test_e_idx = min(test_s_idx + test_len - 1, total - 1)
        if test_s_idx >= total:
            break
        windows.append(
            WalkForwardWindow(
                train_start=train_s,
                train_end=index[train_e_idx],
                test_start=index[test_s_idx],
                test_end=index[test_e_idx],
            )
        )
    return windows


def walk_forward(
    strategy: Strategy,
    data: pd.DataFrame,
    n_splits: int = 5,
    train_ratio: float = 0.7,
    cost_model: str | None = None,
) -> dict[str, Any]:
    """Run a walk-forward analysis.

    Note: this implementation does NOT re-fit parameters between windows
    (the strategies here are non-parametric / use fixed conventions like
    EMA50, RSI14). It evaluates stability of out-of-sample performance.
    For parameter-search WF, plug in an optimizer per train window.

    Returns:
        dict with:
            - 'windows':   list of WalkForwardWindow
            - 'per_window': DataFrame, one row per window with test metrics
            - 'in_sample':  DataFrame, one row per window with train metrics
            - 'parameter_stability': dict of (metric → {mean, std}) across windows
    """
    if not isinstance(data.index, pd.DatetimeIndex):
        data = data.copy()
        data.index = pd.to_datetime(data.index, utc=True)

    windows = _build_windows(data.index, n_splits, train_ratio)
    rows_test: list[dict[str, Any]] = []
    rows_train: list[dict[str, Any]] = []

    for w in windows:
        train_df = data.loc[w.train_start : w.train_end]
        test_df = data.loc[w.test_start : w.test_end]
        if len(train_df) < 30 or len(test_df) < 10:
            continue

        train_res = run_backtest(strategy, train_df, cost_model=cost_model)
        test_res = run_backtest(strategy, test_df, cost_model=cost_model)

        rows_train.append({
            "window_start": w.train_start,
            "window_end": w.train_end,
            **train_res["summary"],
        })
        rows_test.append({
            "window_start": w.test_start,
            "window_end": w.test_end,
            **test_res["summary"],
        })

    test_df = pd.DataFrame(rows_test)
    train_df_out = pd.DataFrame(rows_train)

    # Stability across out-of-sample windows.
    numeric_cols = [
        "win_rate",
        "profit_factor",
        "expectancy_r",
        "total_return_pct",
        "sharpe",
        "sortino",
        "max_drawdown_pct",
    ]
    stability: dict[str, dict[str, float]] = {}
    for c in numeric_cols:
        if c in test_df.columns and len(test_df) > 0:
            vals = test_df[c].replace([np.inf, -np.inf], np.nan).dropna()
            if len(vals) == 0:
                stability[c] = {"mean": 0.0, "std": 0.0}
            else:
                stability[c] = {
                    "mean": float(vals.mean()),
                    "std": float(vals.std()) if len(vals) > 1 else 0.0,
                }

    return {
        "windows": windows,
        "per_window": test_df,
        "in_sample": train_df_out,
        "parameter_stability": stability,
    }
