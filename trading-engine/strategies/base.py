"""Strategy base class.

Every strategy is a subclass that implements:
    - `prepare(data)`: optional pre-computation (indicators) → DataFrame
    - `signals(data)`: returns a `pd.DataFrame` with columns
        ['direction', 'entry', 'sl', 'tp', 'reason']
      where `direction` is +1 (long), -1 (short), 0 (flat / no signal).

The runner consumes `signals()` and computes equity, drawdown, etc.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class SignalRow:
    """One row of the signals DataFrame, for type clarity."""

    direction: int  # +1 long, -1 short, 0 flat
    entry: float
    sl: float
    tp: float
    reason: str = ""


class Strategy(ABC):
    """Abstract base for all trading strategies.

    Subclasses MUST override:
        - `name`
        - `default_params`
        - `signals(data)`

    Optional overrides:
        - `prepare(data)` — pre-compute indicators
        - `risk_per_trade_pct` — default 1.0% of equity
    """

    #: Human-readable name (e.g. "London Breakout (XAU/USD)").
    name: str = "Strategy"

    #: Default parameter values. Subclasses override.
    default_params: dict[str, Any] = {}

    #: Default per-trade risk in percent of account equity.
    risk_per_trade_pct: float = 1.0

    #: Asset class hint — "forex" / "gold" / "crypto". Used by cost model.
    asset_class: str = "forex"

    #: Symbol this strategy is tuned for (e.g. "XAUUSD", "BTCUSDT").
    symbol: str = ""

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        merged = dict(self.default_params)
        if params:
            merged.update(params)
        self.params: dict[str, Any] = merged

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        """Pre-compute indicators. Override if needed.

        Default implementation returns the data unchanged.
        """
        return data

    @abstractmethod
    def signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Return signals DataFrame indexed by `data.index`.

        Required columns: ['direction', 'entry', 'sl', 'tp', 'reason'].
        - direction: int in {-1, 0, +1}.
        - entry/sl/tp: prices (float). 0 / NaN when direction==0.
        - reason: human-readable label for the trade.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Helpers shared by subclasses
    # ------------------------------------------------------------------
    @staticmethod
    def _empty_signals(index: pd.Index) -> pd.DataFrame:
        """Build a flat-everywhere signals frame with the right schema."""
        return pd.DataFrame(
            {
                "direction": 0,
                "entry": 0.0,
                "sl": 0.0,
                "tp": 0.0,
                "reason": "",
            },
            index=index,
        )

    def describe(self) -> dict[str, Any]:
        """Return strategy metadata for the runner / UI."""
        return {
            "name": self.name,
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "params": self.params,
            "risk_per_trade_pct": self.risk_per_trade_pct,
        }
