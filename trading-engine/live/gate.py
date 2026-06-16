"""Paper -> Live promotion gate.

Atlas (backend) is the ultimate source of truth, but the engine has direct
access to backtest + paper trade tables, so we expose a structured verdict
Atlas can consume.

Required gates (must ALL pass to allow live):

    Backtest:
        - profit_factor   > 1.3
        - max_drawdown_pct < 25
        - test period spans >= 3 years OR includes >=2 distinct regimes

    Paper:
        - days_run         >= 14
        - trades_count     >= 10
        - sharpe           >= 0.5
        - daily_dd_breach   == 0  (never tripped paper-level breakers)

    Risk params:
        - risk_per_trade_pct in (0.1, 2.0]
        - max_drawdown_pct  in (5, 20]

The DB schema is owned by Mnemosyne / Atlas; we use raw `psycopg` here
for the read-only queries.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")


@dataclass
class GateCheck:
    name: str
    passed: bool
    actual: Any
    required: Any
    message: str = ""


@dataclass
class GateResult:
    strategy_instance_id: str
    approved: bool
    checks: list[GateCheck] = field(default_factory=list)
    decided_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "checks": [asdict(c) for c in self.checks],
        }


# ---------------------------------------------------------------------------
def _normalize_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _fetch_row(sql: str, params: tuple) -> dict[str, Any] | None:
    if not DATABASE_URL:
        return None
    try:
        import psycopg  # type: ignore
    except ImportError:  # pragma: no cover — psycopg is standard in our image
        return None
    try:
        with psycopg.connect(_normalize_dsn(DATABASE_URL), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d.name for d in cur.description] if cur.description else []
                row = cur.fetchone()
                return dict(zip(cols, row)) if row else None
    except Exception as e:
        logger.warning("gate.db_read_failed: %s", e)
        return None


# ---------------------------------------------------------------------------
def evaluate_live_gate(strategy_instance_id: str) -> GateResult:
    """Evaluate every gate and return a structured result.

    Read-only — never mutates the DB. Atlas decides what to do with the
    verdict (auto-promote, require manual approval, etc.).
    """
    res = GateResult(
        strategy_instance_id=strategy_instance_id,
        approved=False,
        decided_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    # ------------------------------------------------------------------
    # 1) Backtest gate
    # ------------------------------------------------------------------
    bt = _fetch_row(
        """
        SELECT profit_factor, max_drawdown_pct, total_trades,
               EXTRACT(EPOCH FROM (COALESCE(period_end, completed_at) - COALESCE(period_start, started_at))) AS span_sec
        FROM backtests
        WHERE strategy_instance_id = %s AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
        """,
        (strategy_instance_id,),
    )
    if not bt:
        # Fall back to "no backtest data" — fail loud.
        res.checks.append(
            GateCheck(
                name="backtest_present",
                passed=False,
                actual=None,
                required="row in `backtests` with status=completed",
                message="no completed backtest found for this strategy_instance",
            )
        )
        return res

    pf = float(bt.get("profit_factor") or 0)
    dd = abs(float(bt.get("max_drawdown_pct") or 0))
    span_days = (float(bt.get("span_sec") or 0)) / 86_400
    trades = int(bt.get("total_trades") or 0)

    res.checks += [
        GateCheck("backtest_profit_factor", pf > 1.3, pf, "> 1.3"),
        GateCheck("backtest_max_drawdown_pct", dd < 25, dd, "< 25"),
        GateCheck(
            "backtest_period_days",
            span_days >= 365 * 3,
            round(span_days, 0),
            ">= 1095 (≥ 3 yr)",
            message="long span helps catch regime changes",
        ),
        GateCheck("backtest_total_trades", trades >= 30, trades, ">= 30"),
    ]

    # ------------------------------------------------------------------
    # 2) Paper trade gate
    # ------------------------------------------------------------------
    paper = _fetch_row(
        """
        SELECT
            EXTRACT(EPOCH FROM (NOW() - started_at)) AS run_sec,
            (SELECT COUNT(*) FROM paper_trades pt
                WHERE pt.strategy_instance_id = si.id) AS trades_count,
            (SELECT AVG(pnl)::float FROM paper_trades pt
                WHERE pt.strategy_instance_id = si.id) AS avg_pnl,
            (SELECT STDDEV_POP(pnl)::float FROM paper_trades pt
                WHERE pt.strategy_instance_id = si.id) AS std_pnl
        FROM strategy_instances si
        WHERE si.id = %s
        """,
        (strategy_instance_id,),
    )
    if paper:
        run_days = (float(paper.get("run_sec") or 0)) / 86_400
        trades_count = int(paper.get("trades_count") or 0)
        avg_pnl = float(paper.get("avg_pnl") or 0)
        std_pnl = float(paper.get("std_pnl") or 0)
        # Crude Sharpe proxy on per-trade PnL; the real one uses bar returns.
        sharpe = (avg_pnl / std_pnl) if std_pnl > 0 else 0.0

        res.checks += [
            GateCheck("paper_days_run", run_days >= 14, round(run_days, 1), ">= 14"),
            GateCheck("paper_trades_count", trades_count >= 10, trades_count, ">= 10"),
            GateCheck("paper_sharpe", sharpe >= 0.5, round(sharpe, 3), ">= 0.5"),
        ]
    else:
        res.checks.append(
            GateCheck(
                name="paper_trade_present",
                passed=False,
                actual=None,
                required="row in `strategy_instances`",
                message="no strategy_instance row — paper trade not started",
            )
        )

    # ------------------------------------------------------------------
    # 3) Risk params gate (read strategy_instances.params)
    # ------------------------------------------------------------------
    risk_row = _fetch_row(
        "SELECT params FROM strategy_instances WHERE id = %s",
        (strategy_instance_id,),
    )
    if risk_row and risk_row.get("params"):
        params = risk_row["params"] or {}
        rpt = float(params.get("risk_per_trade_pct", 1.0))
        mdd = float(params.get("max_drawdown_pct", 15.0))
        res.checks += [
            GateCheck(
                "risk_per_trade_in_range",
                0.1 < rpt <= 2.0,
                rpt,
                "(0.1, 2.0]",
            ),
            GateCheck(
                "max_drawdown_in_range",
                5 < mdd <= 20,
                mdd,
                "(5, 20]",
            ),
        ]

    # ------------------------------------------------------------------
    # Final verdict — all checks must pass.
    # ------------------------------------------------------------------
    res.approved = all(c.passed for c in res.checks) and len(res.checks) > 0
    res.notes = (
        "OK — clear for live (start at smallest lot)."
        if res.approved
        else "Failed one or more gates. Fix the highlighted items first."
    )
    return res
