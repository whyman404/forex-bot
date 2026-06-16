"""TradingView signal schemas.

Atlas Goro — Round 5.

These are the public-facing Pydantic models the backend exposes to the frontend
for the `tv_signal` strategy. They mirror the wire format produced by
`trading-engine/tradingview/` (Kairos) but are decoupled — if the engine
adds an internal field, we don't propagate it accidentally.

Contract is intentionally minimal:
  - `TVRecommendation` is a fixed enum (TradingView's own taxonomy).
  - `TVTimeframeAnalysis` is one row of the analysis grid (per-interval).
  - `TVPreview` is the multi-timeframe rollup the UI renders.
  - `TVSymbol` is one row of the supported-symbol catalog.

Validation rules:
  - `score` is normalized to [-100, +100] (-100 = strong sell, +100 = strong buy).
  - `confidence` is [0.0, 1.0]; the engine computes it from agreement across TFs.
  - `intervals` accepted in preview = subset of `SUPPORTED_TV_INTERVALS`.

References:
  - tradingview-ta library — Recommendation enum (STRONG_BUY/BUY/NEUTRAL/SELL/STRONG_SELL).
  - Kairos R5 — `trading-engine/tradingview/scorer.py` for combining rule.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# TradingView's "Recommendation" string is one of these five values.
# We keep them as a Literal alias so downstream Pydantic models inherit it.
TVRecommendation = Literal["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"]

# Intervals the TV screener supports for the multi-timeframe rollup.
# Matches `Interval` enum in `tradingview_ta` (kept as the *backend's* allowlist
# so we can reject unknown intervals at the API edge — never trust caller input).
SUPPORTED_TV_INTERVALS: frozenset[str] = frozenset(
    {
        "1m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "1d",
        "1W",
        "1M",
    }
)


class TVTimeframeAnalysis(BaseModel):
    """Per-interval analysis row from TradingView's screener."""

    model_config = ConfigDict(frozen=True)

    interval: str = Field(description="Timeframe label, e.g. '15m', '1h', '1d'.")
    recommendation: TVRecommendation
    buy_count: int = Field(ge=0, description="Number of buy-leaning indicators.")
    sell_count: int = Field(ge=0, description="Number of sell-leaning indicators.")
    neutral_count: int = Field(ge=0, description="Number of neutral indicators.")


class TVPreview(BaseModel):
    """Rolled-up multi-timeframe analysis snapshot for a single symbol.

    The score is a deterministic projection of the per-TF rows; the engine is
    the source of truth for the combining rule. We pass it through unchanged so
    if Kairos tweaks the weights we don't have to ship a backend release.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="TV ticker (e.g. 'XAUUSD', 'BTCUSDT').")
    exchange: str = Field(description="TV exchange (e.g. 'OANDA', 'BINANCE').")
    score: float = Field(
        ge=-100.0,
        le=100.0,
        description="Normalized signal score in [-100, +100].",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in [0.0, 1.0] based on cross-TF agreement.",
    )
    timeframes: list[TVTimeframeAnalysis] = Field(
        description="Per-interval breakdown, in caller-requested order.",
    )
    generated_at: datetime = Field(
        description="When the engine produced this preview (UTC).",
    )


class TVSymbol(BaseModel):
    """One supported instrument in the TV catalog."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(description="Internal symbol code (e.g. 'XAUUSD').")
    tv_symbol: str = Field(description="TV ticker (may differ for indices).")
    tv_exchange: str = Field(description="TV exchange code.")
    asset_class: Literal["gold", "forex", "crypto", "index"]
    display_name: str = Field(
        default="",
        description="Human-readable label for the UI.",
    )


class TVHealth(BaseModel):
    """Health probe of the TV integration end-to-end."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded", "down"]
    trading_engine_reachable: bool
    upstream_tv_reachable: bool | None = Field(
        default=None,
        description=(
            "Whether the engine could reach TradingView itself. "
            "None = engine did not report (older engine version)."
        ),
    )
    reason: str | None = Field(
        default=None,
        description="If not 'ok', short human-readable reason.",
    )
    checked_at: datetime


class TVPreviewRequest(BaseModel):
    """Body for POST /tv/preview."""

    symbol: str = Field(min_length=1, max_length=32)
    exchange: str | None = Field(default=None, max_length=16)
    intervals: list[str] = Field(
        default_factory=lambda: ["15m", "1h", "4h"],
        min_length=1,
        max_length=8,
        description="Subset of SUPPORTED_TV_INTERVALS.",
    )


__all__ = [
    "TVRecommendation",
    "TVTimeframeAnalysis",
    "TVPreview",
    "TVSymbol",
    "TVHealth",
    "TVPreviewRequest",
    "SUPPORTED_TV_INTERVALS",
]
