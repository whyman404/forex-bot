"""Symbol metadata.

Used by sizing + cost-model to translate "lots" ↔ "USD risk".
Values are tuned for **Exness** (gold) and **Binance** (BTC) as of 2026-06.
Re-verify if you change broker.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolMeta:
    """Per-symbol contract spec + cost baseline."""

    symbol: str
    description: str
    pip_size: float                    # price increment per 1 pip
    contract_size: float               # units per 1 lot
    pip_value_per_lot: float           # USD profit per pip per 1 lot
    min_lot: float
    lot_step: float
    baseline_spread_pts: float         # broker avg spread, in points (10 pts = 1 pip)
    asset_class: str = "forex"


# Reference: Exness lot sizes & Binance contracts.
#   XAUUSD: 1 lot = 100 oz; pip = 0.01 USD; pip value per 1 lot = $1.00
#                                          (but Exness common quote 0.10 / pip — both consistent w/ 2 dp)
#   BTCUSDT (Binance spot): contract = 1 BTC; pip == $1.
SYMBOLS: dict[str, SymbolMeta] = {
    "XAUUSD": SymbolMeta(
        symbol="XAUUSD",
        description="Gold vs USD (Exness)",
        pip_size=0.10,
        contract_size=100.0,
        pip_value_per_lot=10.0,  # $10 / pip / lot on standard contract (100 oz × $0.10/pip)
        min_lot=0.01,
        lot_step=0.01,
        baseline_spread_pts=20.0,
        asset_class="gold",
    ),
    "BTCUSDT": SymbolMeta(
        symbol="BTCUSDT",
        description="Bitcoin vs USDT (Binance spot)",
        pip_size=1.0,
        contract_size=1.0,
        pip_value_per_lot=1.0,
        min_lot=0.001,
        lot_step=0.001,
        baseline_spread_pts=0.0,  # spread embedded in 0.05% taker fee
        asset_class="crypto",
    ),
}


def get(symbol: str) -> SymbolMeta:
    """Look up symbol metadata, case-insensitive."""
    key = symbol.upper()
    if key not in SYMBOLS:
        raise KeyError(f"Unknown symbol: {symbol}. Known: {sorted(SYMBOLS)}")
    return SYMBOLS[key]
