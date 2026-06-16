"""seed tv_signal strategy + external-signal-provider columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-16

Mnemosyne Rin — small additive migration for the TradingView-driven
``tv_signal`` strategy (Kairos's round-4 addition).

What this migration does (idempotent, expand-only):
  1. Relax two CHECK constraints on ``strategies``:
       - ``code`` IN (...) gains ``'tv_signal'``
       - ``asset_class`` IN (...) gains ``'multi'``
     We keep the CHECK pattern (string + CHECK) rather than a real ENUM
     because (a) ENUM type changes are not online in Postgres < 16 without
     ``ALTER TYPE ... ADD VALUE`` ceremony, and (b) the catalog is small
     enough that string + CHECK is auditable from psql with a single query.
  2. Add ``strategies.requires_external_service`` BOOL DEFAULT FALSE.
     Documents which catalog rows depend on an outside dependency
     (TradingView in our case). The application layer reads this to
     gate UI enablement and to feed health-checks (Atlas's /readyz).
  3. Add ``strategy_instances.external_signal_provider`` VARCHAR NULL.
     Audit field — records WHO supplied the signal for a given live
     instance (e.g. ``'tradingview'``). Lets us answer compliance
     questions like "which trades were influenced by an external feed?"
  4. UPSERT the ``tv_signal`` row into ``strategies`` with
     ``ON CONFLICT (code) DO UPDATE`` so repeated runs converge to the
     pinned default_params.

Why a real expand-contract for the CHECK:
  ``DROP CONSTRAINT`` + ``ADD CONSTRAINT`` inside a single migration is
  safe here because (a) the table is small (single-digit rows), and
  (b) we hold an ACCESS EXCLUSIVE lock for milliseconds. If this ever
  becomes a hot table, the right approach is NOT VALID + VALIDATE
  CONSTRAINT split across two migrations.

Downgrade fully reverses:
  - removes the tv_signal row;
  - restores the original 6-code / 2-asset CHECK constraints;
  - drops the two added columns.
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# tv_signal default parameters — mirrors Kairos's strategies.yaml block.
# Pinned to this migration revision. To change defaults, ship a NEW
# migration; do not mutate this dict in place (auditability).
# ---------------------------------------------------------------------------
TV_SIGNAL_DEFAULT_PARAMS: dict = {
    # Which TV symbols this instance is allowed to follow. Empty list = ALL
    # symbols supported by tradingview/symbols.py (curated list).
    "symbols": [],

    # Multi-timeframe consensus — TV returns a Recommendation per interval;
    # we combine them via tradingview.scorer.combine_recommendations.
    # Default = 1h + 4h + 1d (mid-frequency swing).
    "intervals": ["1h", "4h", "1d"],

    # Score thresholds (after combine_recommendations normalization, range
    # [-1.0, +1.0]). >= long_threshold => long; <= short_threshold => short.
    "long_threshold": 0.5,
    "short_threshold": -0.5,

    # ATR-based risk sizing — same convention as ema_adx.
    "atr_period": 14,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 3.0,

    # Cool-down (minutes) between signals on the same symbol; prevents
    # whipsawing when TV flips on the boundary of long_threshold.
    "cool_down_min": 60,

    # Standard risk knobs.
    "risk_per_trade_pct": 1.0,
    "max_trades_per_day": 6,        # across all symbols combined
    "spread_filter_pts": 30,        # forex/gold; ignored for crypto

    # Operational kill-switch — set False to silently stop generating
    # signals without deleting the instance (useful while debugging).
    "enabled": True,
}


# Idempotent UPSERT — re-running the migration converges to the pinned
# default_params + display_name. We do NOT bump version on conflict; the
# version column tracks SCHEMA of params (consumer-visible breaking
# changes), and re-applying the same revision is not a breaking change.
UPSERT_SQL = sa.text(
    """
    INSERT INTO strategies
        (code, display_name, asset_class, default_params, description,
         risk_rating, is_enabled, version, requires_external_service)
    VALUES
        ('tv_signal',
         'TradingView Signal Follow',
         'multi',
         CAST(:default_params AS jsonb),
         'Multi-timeframe TradingView recommendation following with ATR-based risk management.',
         'medium',
         TRUE,
         1,
         TRUE)
    ON CONFLICT (code) DO UPDATE
       SET display_name              = EXCLUDED.display_name,
           asset_class               = EXCLUDED.asset_class,
           default_params            = EXCLUDED.default_params,
           description               = EXCLUDED.description,
           risk_rating               = EXCLUDED.risk_rating,
           requires_external_service = EXCLUDED.requires_external_service,
           updated_at                = NOW();
    """
)


# ---------------------------------------------------------------------------
# UPGRADE
# ---------------------------------------------------------------------------
UPGRADE_DDL = r"""
-- =========================================================================
-- 1. Expand CHECK constraints on `strategies` to admit tv_signal + multi.
--    We drop-then-add (small table, ms-level ACCESS EXCLUSIVE).
-- =========================================================================

-- The original constraints are named by Postgres as <table>_<col>_check.
-- Use generated names defensively in case a fresh DB initialized via
-- schema.sql has slightly different ordering — we look them up.
DO $$
DECLARE
    code_check_name text;
    asset_check_name text;
BEGIN
    SELECT con.conname
      INTO code_check_name
      FROM pg_constraint con
      JOIN pg_class cls ON cls.oid = con.conrelid
     WHERE cls.relname = 'strategies'
       AND con.contype = 'c'
       AND pg_get_constraintdef(con.oid) ILIKE '%code%IN%london_breakout%'
     LIMIT 1;

    IF code_check_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE strategies DROP CONSTRAINT %I', code_check_name);
    END IF;

    SELECT con.conname
      INTO asset_check_name
      FROM pg_constraint con
      JOIN pg_class cls ON cls.oid = con.conrelid
     WHERE cls.relname = 'strategies'
       AND con.contype = 'c'
       AND pg_get_constraintdef(con.oid) ILIKE '%asset_class%IN%gold%'
     LIMIT 1;

    IF asset_check_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE strategies DROP CONSTRAINT %I', asset_check_name);
    END IF;
END$$;

-- Add the relaxed CHECKs back with stable names so downgrade can find them.
ALTER TABLE strategies
    ADD CONSTRAINT strategies_code_check
    CHECK (code IN ('london_breakout','ny_killzone','ema_adx','ema_rsi',
                    'donchian','grid','tv_signal'));

ALTER TABLE strategies
    ADD CONSTRAINT strategies_asset_class_check
    CHECK (asset_class IN ('gold','btc','multi'));

-- =========================================================================
-- 2. Additive columns — both nullable / defaulted, safe under traffic.
-- =========================================================================

ALTER TABLE strategies
    ADD COLUMN IF NOT EXISTS requires_external_service BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE strategy_instances
    ADD COLUMN IF NOT EXISTS external_signal_provider VARCHAR(32) NULL;

-- Partial index — only rows that actually use an external provider.
-- Cheap (the catalog row count for tv_signal-derived instances is small).
CREATE INDEX IF NOT EXISTS strategy_instances_external_provider_idx
    ON strategy_instances (external_signal_provider)
    WHERE external_signal_provider IS NOT NULL;
"""


DOWNGRADE_DDL = r"""
-- =========================================================================
-- Reverse, in safe order: row -> indexes -> columns -> CHECKs.
-- =========================================================================

DELETE FROM strategies WHERE code = 'tv_signal';

DROP INDEX IF EXISTS strategy_instances_external_provider_idx;

ALTER TABLE strategy_instances
    DROP COLUMN IF EXISTS external_signal_provider;

ALTER TABLE strategies
    DROP COLUMN IF EXISTS requires_external_service;

-- Restore original CHECK constraints by name.
DO $$
DECLARE
    code_check_name text;
    asset_check_name text;
BEGIN
    SELECT con.conname INTO code_check_name
      FROM pg_constraint con
      JOIN pg_class cls ON cls.oid = con.conrelid
     WHERE cls.relname = 'strategies'
       AND con.contype = 'c'
       AND pg_get_constraintdef(con.oid) ILIKE '%code%IN%tv_signal%'
     LIMIT 1;

    IF code_check_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE strategies DROP CONSTRAINT %I', code_check_name);
    END IF;

    SELECT con.conname INTO asset_check_name
      FROM pg_constraint con
      JOIN pg_class cls ON cls.oid = con.conrelid
     WHERE cls.relname = 'strategies'
       AND con.contype = 'c'
       AND pg_get_constraintdef(con.oid) ILIKE '%asset_class%IN%multi%'
     LIMIT 1;

    IF asset_check_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE strategies DROP CONSTRAINT %I', asset_check_name);
    END IF;
END$$;

ALTER TABLE strategies
    ADD CONSTRAINT strategies_code_check
    CHECK (code IN ('london_breakout','ny_killzone','ema_adx','ema_rsi',
                    'donchian','grid'));

ALTER TABLE strategies
    ADD CONSTRAINT strategies_asset_class_check
    CHECK (asset_class IN ('gold','btc'));
"""


def upgrade() -> None:
    op.execute(sa.text(UPGRADE_DDL))
    conn = op.get_bind()
    conn.execute(
        UPSERT_SQL,
        {"default_params": json.dumps(TV_SIGNAL_DEFAULT_PARAMS)},
    )


def downgrade() -> None:
    op.execute(sa.text(DOWNGRADE_DDL))
