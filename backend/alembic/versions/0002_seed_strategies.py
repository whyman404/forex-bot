"""seed strategies catalog — 6 default strategies

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15

Mnemosyne Rin — data migration. Idempotent via ON CONFLICT (code) DO NOTHING.
Parameters embedded inline from trading-engine/configs/strategies.yaml so the
migration container does NOT need to read the yaml at runtime — the values
are pinned to this migration's revision (auditable).
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Pinned strategy parameter snapshots (mirror of trading-engine/configs/strategies.yaml
# as of 2026-06-15). If the trading engine config drifts, create a new migration —
# DO NOT mutate this dict.
STRATEGIES: list[dict] = [
    {
        "code": "london_breakout",
        "display_name": "Gold London Breakout",
        "asset_class": "gold",
        "risk_rating": "medium",
        "description": (
            "Breakout of the Asian-session range during London open on XAUUSD M15. "
            "Buffer/SL/TP in pips; fixed or range-mult TP."
        ),
        "default_params": {
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "buffer_pips": 5.0,
            "sl_pips": 40.0,
            "tp_pips": 60.0,
            "tp_mode": "fixed",
            "tp_range_mult": 1.5,
            "min_range_pips": 30.0,
            "max_range_pips": 200.0,
            "spread_filter_pts": 30,
            "max_trades_per_day": 1,
            "risk_per_trade_pct": 1.0,
        },
    },
    {
        "code": "ny_killzone",
        "display_name": "Gold NY Killzone Reversal",
        "asset_class": "gold",
        "risk_rating": "high",
        "description": (
            "NY open killzone reversal scalping on XAUUSD M5 — narrow SL, single "
            "trade per session."
        ),
        "default_params": {
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "sl_pips": 30.0,
            "tp_pips": 60.0,
            "max_trades_per_day": 1,
            "spread_filter_pts": 30,
            "risk_per_trade_pct": 1.0,
        },
    },
    {
        "code": "ema_adx",
        "display_name": "Gold EMA+ADX Trend",
        "asset_class": "gold",
        "risk_rating": "low",
        "description": (
            "Trend-following on XAUUSD H1 using EMA50 with ADX>25 filter, "
            "ATR-based SL/TP."
        ),
        "default_params": {
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "ema_period": 50,
            "adx_period": 14,
            "adx_threshold": 25.0,
            "atr_period": 14,
            "sl_atr_mult": 1.5,
            "tp_atr_mult": 3.0,
            "use_trailing_atr": False,
            "trail_atr_mult": 2.0,
            "risk_per_trade_pct": 1.0,
        },
    },
    {
        "code": "ema_rsi",
        "display_name": "BTC EMA Cross + RSI",
        "asset_class": "btc",
        "risk_rating": "medium",
        "description": (
            "Swing trade BTCUSDT H4: EMA12/26 cross confirmed by RSI>50, "
            "percent-of-price SL/TP, EMA trail."
        ),
        "default_params": {
            "symbol": "BTCUSDT",
            "timeframe": "H4",
            "ema_fast": 12,
            "ema_slow": 26,
            "rsi_period": 14,
            "rsi_threshold": 50.0,
            "swing_lookback": 10,
            "sl_pct_cap": 0.03,
            "tp_pct_cap": 0.06,
            "use_trailing_ema": True,
            "risk_per_trade_pct": 1.0,
        },
    },
    {
        "code": "donchian",
        "display_name": "BTC Donchian Breakout",
        "asset_class": "btc",
        "risk_rating": "medium",
        "description": (
            "Donchian channel breakout on BTCUSDT H1, exit on opposite-side "
            "shorter Donchian."
        ),
        "default_params": {
            "symbol": "BTCUSDT",
            "timeframe": "H1",
            "entry_period": 20,
            "exit_period": 10,
            "risk_per_trade_pct": 2.0,
        },
    },
    {
        "code": "grid",
        "display_name": "BTC Grid Bot",
        "asset_class": "btc",
        "risk_rating": "high",
        "description": (
            "Grid around VWAP/EMA50 center, 10 levels, hard SL at -15% to "
            "prevent runaway loss in trending regime."
        ),
        "default_params": {
            "symbol": "BTCUSDT",
            "timeframe": "M15",
            "center_mode": "vwap",
            "ema_period": 50,
            "n_levels": 10,
            "spacing_pct": 0.01,
            "tp_pct": 0.01,
            "hard_sl_pct": 0.15,
            "rebalance_hourly": False,
            "risk_per_trade_pct": 0.5,
        },
    },
]


# ON CONFLICT DO NOTHING → idempotent re-runs.
INSERT_SQL = sa.text(
    """
    INSERT INTO strategies
        (code, display_name, asset_class, default_params, description,
         risk_rating, is_enabled, version)
    VALUES
        (:code, :display_name, :asset_class, CAST(:default_params AS jsonb),
         :description, :risk_rating, true, 1)
    ON CONFLICT (code) DO NOTHING;
    """
)


def upgrade() -> None:
    conn = op.get_bind()
    for strat in STRATEGIES:
        conn.execute(
            INSERT_SQL,
            {
                "code": strat["code"],
                "display_name": strat["display_name"],
                "asset_class": strat["asset_class"],
                "default_params": json.dumps(strat["default_params"]),
                "description": strat["description"],
                "risk_rating": strat["risk_rating"],
            },
        )


def downgrade() -> None:
    codes = [s["code"] for s in STRATEGIES]
    op.execute(
        sa.text("DELETE FROM strategies WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes, type_=sa.ARRAY(sa.String()))
        )
    )
