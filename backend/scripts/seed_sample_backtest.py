"""Seed one completed backtest so the dashboard renders non-empty.

Usage:
    python -m scripts.seed_sample_backtest

Behavior:
- Looks for admin@local user + the `donchian` strategy.
- Inserts ONE completed backtest with a synthetic equity curve URL.
- Idempotent: uses a fixed UUID + ON CONFLICT DO NOTHING.

Mnemosyne Rin — this is dev-only. Never run against production data.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Final

from sqlalchemy import text

from app.db.session import SessionLocal


# Deterministic UUID so re-runs are no-ops.
SAMPLE_BACKTEST_ID: Final[uuid.UUID] = uuid.UUID("00000000-0000-7000-8000-000000000001")

INSERT_SQL = text(
    """
    WITH src AS (
        SELECT
            u.id AS user_id,
            s.id AS strategy_id
        FROM users u
        CROSS JOIN strategies s
        WHERE u.email = :admin_email
          AND u.deleted_at IS NULL
          AND s.code = :strategy_code
        LIMIT 1
    )
    INSERT INTO backtests
        (id, user_id, strategy_id, asset_symbol, timeframe, params,
         start_date, end_date, status,
         total_return_pct, max_drawdown_pct, sharpe, sortino, profit_factor,
         win_rate_pct, total_trades, equity_curve_url, trades_count,
         started_at, completed_at)
    SELECT
        :backtest_id,
        src.user_id,
        src.strategy_id,
        'BTCUSDT', 'H1', '{}'::jsonb,
        DATE '2024-01-01', DATE '2024-12-31',
        'completed',
        24.5000,   -- total_return_pct
        8.1000,    -- max_drawdown_pct
        1.4500,    -- sharpe
        1.9800,    -- sortino
        1.6700,    -- profit_factor
        54.20,     -- win_rate_pct
        128,       -- total_trades
        '/static/sample_equity_curve.json',
        128,
        now() - interval '5 minutes',
        now()
    FROM src
    ON CONFLICT (id) DO NOTHING
    RETURNING id;
    """
)


async def seed_sample_backtest(
    admin_email: str = "admin@local",
    strategy_code: str = "donchian",
) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            INSERT_SQL,
            {
                "backtest_id": str(SAMPLE_BACKTEST_ID),
                "admin_email": admin_email,
                "strategy_code": strategy_code,
            },
        )
        row = result.first()
        await session.commit()

    if row is None:
        sys.stdout.write(
            "seed_sample_backtest: nothing inserted (already present or "
            "missing admin/strategy).\n"
        )
        return

    sys.stdout.write(f"Sample backtest seeded: {row.id}\n")


def main() -> None:
    asyncio.run(seed_sample_backtest())


if __name__ == "__main__":
    main()
