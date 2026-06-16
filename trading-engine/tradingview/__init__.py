"""TradingView signal-source integration.

We import the `tradingview-ta` PyPI library directly (NOT the MCP server)
and wrap it with:
    - retry (3 attempts, exponential backoff)
    - in-process TTL cache (60s)
    - concurrency throttle (max 4 concurrent, 0.8s spacing)
    - graceful disable if the library is not installed

Rationale (Kairos's note)
-------------------------
The upstream `tradingview-mcp` repo (atilaahmettaner/tradingview-mcp) is
analysis-only — it does NOT execute trades. We treat TV's "Recommendation"
as an external SIGNAL SOURCE, not an oracle. Trades are still gated by
our RiskManager + CircuitBreaker + the MT5 bridge's safety layer.

We deliberately surface TV scores to the user as informational — the
user accepts that "TradingView signals are not financial advice" before
enabling any tv_signal instance (UI gate).

Public re-exports
-----------------
- `TVAnalysis`, `TVClient` from `tradingview.client`
- `Scorer`, `combine_recommendations` from `tradingview.scorer`
- `resolve_symbol`, `SUPPORTED_SYMBOLS` from `tradingview.symbols`
"""
from __future__ import annotations

from tradingview.client import TVAnalysis, TVClient, tv_enabled
from tradingview.scorer import Scorer, combine_recommendations
from tradingview.symbols import SUPPORTED_SYMBOLS, resolve_symbol

__all__ = [
    "TVAnalysis",
    "TVClient",
    "Scorer",
    "combine_recommendations",
    "resolve_symbol",
    "SUPPORTED_SYMBOLS",
    "tv_enabled",
]
