"""RQ-compatible backtest worker.

`run_backtest_job(...)` is the single entrypoint. It:
1. Resolves the strategy class by code.
2. Loads OHLCV (sample CSV in dev; real source in prod).
3. Slices to [start, end].
4. Runs the backtest.
5. Writes equity curve JSON to disk.
6. Updates the `backtests` Postgres row (if DATABASE_URL is set).
7. Returns a dict the caller (server.py or RQ) can use.

Same function runs in both the in-process FastAPI path and RQ workers.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EQUITY_DIR = Path(os.getenv("EQUITY_CURVE_DIR", "/var/data/equity-curves"))
DATABASE_URL = os.getenv("DATABASE_URL")


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------
def _strategy_registry() -> dict[str, type]:
    """Map strategy_code -> Strategy subclass. Lazy import to avoid heavy
    deps on server boot."""
    from strategies.donchian_breakout import DonchianBreakoutStrategy
    from strategies.ema_adx_trend import EmaAdxTrendStrategy
    from strategies.ema_rsi_swing import EmaRsiSwingStrategy
    from strategies.grid_bot import GridBotStrategy
    from strategies.london_breakout import LondonBreakoutStrategy
    from strategies.ny_killzone import NYKillzoneReversalStrategy
    from strategies.tv_signal import TVSignalStrategy

    return {
        "london_breakout": LondonBreakoutStrategy,
        "ny_killzone": NYKillzoneReversalStrategy,
        "ema_adx_trend": EmaAdxTrendStrategy,
        "ema_rsi_swing": EmaRsiSwingStrategy,
        "donchian_breakout": DonchianBreakoutStrategy,
        "grid_bot": GridBotStrategy,
        "tv_signal": TVSignalStrategy,
    }


def _resolve_equity_dir() -> Path:
    target = EQUITY_DIR
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except PermissionError:
        fallback = Path.home() / ".forex-bot" / "equity-curves"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


# ---------------------------------------------------------------------------
# Optional DB update
# ---------------------------------------------------------------------------
def _normalize_dsn(url: str) -> str:
    """psycopg expects a libpq DSN, not the SQLAlchemy-flavored async URL.

    DATABASE_URL is shared with the backend, where it is `postgresql+asyncpg://...`.
    Strip the `+asyncpg` driver tag so psycopg can connect.
    """
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _update_backtest_row(
    backtest_id: str,
    status: str,
    summary: dict[str, Any] | None = None,
    equity_curve_url: str | None = None,
    error: str | None = None,
) -> None:
    """UPDATE backtests SET status=..., metrics columns=..., equity_curve_url=... WHERE id=...

    Writes to the canonical columns from docs/database/schema.sql §4.7 — there is
    no JSON `metrics` column. Unknown summary keys are ignored. No-op if
    DATABASE_URL is unset or psycopg is missing (pure-dev path).
    """
    if not DATABASE_URL:
        logger.info(
            "skip_db_update", extra={"backtest_id": backtest_id, "reason": "DATABASE_URL not set"}
        )
        return
    try:
        import psycopg  # type: ignore
    except ImportError:
        logger.warning("psycopg not installed; skipping DB update")
        return

    summary = summary or {}

    # Allowed canonical columns + their summary key + Postgres type cast.
    metric_keys = [
        ("total_return_pct", "total_return_pct", "numeric"),
        ("max_drawdown_pct", "max_drawdown_pct", "numeric"),
        ("sharpe", "sharpe", "numeric"),
        ("sortino", "sortino", "numeric"),
        ("profit_factor", "profit_factor", "numeric"),
        ("win_rate_pct", "win_rate_pct", "numeric"),
        ("total_trades", "total_trades", "int"),
        ("trades_count", "trades_count", "int"),
    ]

    set_clauses = ["status = %s"]
    params: list[Any] = [status]

    # Equity curve URL
    if equity_curve_url is not None:
        set_clauses.append("equity_curve_url = %s")
        params.append(equity_curve_url)

    # Error message
    if error is not None:
        set_clauses.append("error_message = %s")
        params.append(error)

    # Lifecycle timestamps
    if status == "running":
        set_clauses.append("started_at = COALESCE(started_at, NOW())")
    if status in ("completed", "failed"):
        set_clauses.append("completed_at = NOW()")

    # Metric columns from summary
    for col, key, _ in metric_keys:
        if key in summary and summary[key] is not None:
            set_clauses.append(f"{col} = %s")
            params.append(summary[key])

    params.append(backtest_id)
    sql = f"UPDATE backtests SET {', '.join(set_clauses)} WHERE id = %s"

    try:
        with psycopg.connect(_normalize_dsn(DATABASE_URL), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
    except Exception as e:  # broad: don't kill the worker on DB hiccup
        logger.exception("db_update_failed: %s", e)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _load_data(asset: str, timeframe: str, start: str, end: str):
    """Load OHLCV, slice [start, end]. Falls back to sample if real source missing."""
    import pandas as pd

    from data.loader import load_sample

    df = load_sample(asset, timeframe)
    try:
        start_ts = pd.to_datetime(start, utc=True)
        end_ts = pd.to_datetime(end, utc=True)
        # Inclusive end → add 1 day so an end of "2025-06-05" includes that day.
        end_ts = end_ts + pd.Timedelta(days=1)
        sliced = df.loc[(df.index >= start_ts) & (df.index < end_ts)]
        if len(sliced) >= 50:
            return sliced
    except Exception as e:  # log and use full sample
        logger.warning("date_slice_failed; using full sample: %s", e)
    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run_backtest_job(
    backtest_id: str,
    strategy_code: str,
    asset: str,
    timeframe: str,
    start: str,
    end: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a backtest and persist its results.

    Returns:
        {
            "backtest_id": str,
            "status": "completed" | "failed",
            "summary": {...},               # metrics
            "equity_curve_url": "file://..."  # path to JSON artifact
        }
    """
    logger.info(
        "run_backtest_job start",
        extra={
            "backtest_id": backtest_id,
            "strategy_code": strategy_code,
            "asset": asset,
            "timeframe": timeframe,
        },
    )
    _update_backtest_row(backtest_id, status="running")

    try:
        registry = _strategy_registry()
        if strategy_code not in registry:
            raise ValueError(
                f"unknown strategy_code={strategy_code!r}; known: {list(registry)}"
            )
        StrategyCls = registry[strategy_code]
        strat = StrategyCls(params=params or {})

        data = _load_data(asset, timeframe, start, end)
        if data is None or len(data) < 50:
            raise ValueError(
                f"insufficient data for {asset} {timeframe} {start}..{end} "
                f"(got {0 if data is None else len(data)} bars; need >= 50)"
            )

        from backtest.runner import run_backtest

        result = run_backtest(strat, data)
        summary = result["summary"]
        equity = result["equity_curve"]

        # Persist equity curve to disk.
        out_dir = _resolve_equity_dir()
        artifact = out_dir / f"{backtest_id}.json"
        payload = {
            "backtest_id": backtest_id,
            "strategy_code": strategy_code,
            "asset": asset,
            "timeframe": timeframe,
            "summary": summary,
            "equity_curve": [
                {"timestamp": str(idx), "equity": float(val)}
                for idx, val in equity.items()
            ],
        }
        with artifact.open("w") as f:
            json.dump(payload, f, default=str)

        equity_curve_url = f"file://{artifact}"
        _update_backtest_row(
            backtest_id,
            status="completed",
            summary=summary,
            equity_curve_url=equity_curve_url,
        )

        return {
            "backtest_id": backtest_id,
            "status": "completed",
            "summary": summary,
            "equity_curve_url": equity_curve_url,
        }

    except Exception as e:
        logger.exception("run_backtest_job failed: %s", e)
        _update_backtest_row(backtest_id, status="failed", error=str(e))
        return {
            "backtest_id": backtest_id,
            "status": "failed",
            "error": str(e),
        }
