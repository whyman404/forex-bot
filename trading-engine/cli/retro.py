"""Strategy retrospective — read 30 days of live/paper trades, write a
markdown report into `dev-team/09-quant-kairos-toki/work/.../retrospectives/`.

Usage:
    python -m cli.retro --strategy-instance <id> --window-days 30 \
        --out-dir /Users/.../retrospectives

Verdicts:
    - KEEP    — realized metrics within 25% of expected (from backtest)
    - ADJUST  — realized metrics outside band but PF > 1.0 and DD within hard limit
    - KILL    — PF <= 1.0 OR DD breached
"""
from __future__ import annotations

import argparse
import logging
import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _normalize_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _fetch_all(sql: str, params: tuple) -> list[dict[str, Any]]:
    if not DATABASE_URL:
        return []
    try:
        import psycopg  # type: ignore
    except ImportError:
        return []
    with psycopg.connect(_normalize_dsn(DATABASE_URL), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_one(sql: str, params: tuple) -> dict[str, Any] | None:
    rows = _fetch_all(sql, params)
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
def _stats(pnls: list[float]) -> dict[str, Any]:
    if not pnls:
        return {"n": 0}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total = sum(pnls)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    avg_win = statistics.fmean(wins) if wins else 0.0
    avg_loss = statistics.fmean([abs(x) for x in losses]) if losses else 0.0
    expectancy = (
        (len(wins) / len(pnls)) * avg_win - (len(losses) / len(pnls)) * avg_loss
        if pnls
        else 0.0
    )
    return {
        "n": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 2),
        "total_pnl": round(total, 2),
        "profit_factor": round(pf, 3) if pf != float("inf") else "Inf",
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 3),
    }


def _decide(realized: dict[str, Any], expected: dict[str, Any] | None, hard_dd_pct: float) -> tuple[str, str]:
    n = realized.get("n", 0)
    if n == 0:
        return "INSUFFICIENT_DATA", "no trades in window — extend window or check engine."
    pf = realized.get("profit_factor")
    if pf == "Inf":
        pf_num = float("inf")
    else:
        pf_num = float(pf or 0)
    if pf_num <= 1.0:
        return "KILL", f"profit factor {pf_num} <= 1.0 — edge gone."
    if realized.get("max_drawdown_pct", 0) >= hard_dd_pct:
        return "KILL", f"realized DD {realized['max_drawdown_pct']} >= hard limit {hard_dd_pct}."
    if expected and expected.get("profit_factor"):
        exp_pf = float(expected["profit_factor"])
        if pf_num < exp_pf * 0.75:
            return "ADJUST", f"PF {pf_num} < 75% of expected {exp_pf}."
    return "KEEP", f"PF {pf_num} within band."


# ---------------------------------------------------------------------------
def render_markdown(report: dict[str, Any]) -> str:
    r = report
    lines = [
        f"# Strategy retrospective — {r['strategy_code']} ({r['symbol']} {r['timeframe']})",
        "",
        f"**Window:** {r['window_start']} → {r['window_end']}",
        f"**Strategy instance:** `{r['strategy_instance_id']}`",
        f"**Generated:** {r['generated_at']}",
        "",
        "## Verdict",
        f"**{r['verdict']}** — {r['verdict_reason']}",
        "",
        "## Realized metrics",
        "",
    ]
    for k, v in r["realized"].items():
        lines.append(f"- **{k}**: {v}")
    lines += [
        "",
        "## Expected (from latest backtest)",
        "",
    ]
    if r["expected"]:
        for k, v in r["expected"].items():
            lines.append(f"- **{k}**: {v}")
    else:
        lines.append("_no backtest summary on file_")
    lines += [
        "",
        "## What to do next",
        "",
    ]
    if r["verdict"] == "KEEP":
        lines.append("- Keep the strategy running with current params.")
        lines.append("- Next retro at +30 days.")
    elif r["verdict"] == "ADJUST":
        lines.append("- Re-run walk-forward with current params on the last 6 months — confirm decay.")
        lines.append("- Try one parameter sweep (one param at a time, smallest grid).")
        lines.append("- Consider lowering `risk_per_trade_pct` by 25% until next retro.")
    elif r["verdict"] == "KILL":
        lines.append("- POST /live/stop immediately (or /live/kill if open positions).")
        lines.append("- Move to paper for re-validation; do not re-promote until walk-forward passes.")
    else:
        lines.append("- Extend window and re-run.")
    lines += ["", "---", "_Generated by `python -m cli.retro`._", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
def build_report(strategy_instance_id: str, window_days: int) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(days=window_days)

    si = _fetch_one(
        """
        SELECT id, strategy_code, asset AS symbol, timeframe, params
        FROM strategy_instances WHERE id = %s
        """,
        (strategy_instance_id,),
    ) or {}

    trades = _fetch_all(
        """
        SELECT pnl, opened_at, closed_at, sl, tp, fill_price
        FROM live_trades
        WHERE strategy_instance_id = %s AND closed_at >= %s
        ORDER BY closed_at ASC
        """,
        (strategy_instance_id, window_start),
    )
    pnls = [float(t["pnl"]) for t in trades if t.get("pnl") is not None]

    realized = _stats(pnls)
    # rough realized max DD from running equity
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        running += p
        peak = max(peak, running)
        if peak > 0:
            max_dd = max(max_dd, (peak - running) / max(abs(peak), 1.0) * 100)
    realized["max_drawdown_pct"] = round(max_dd, 2)

    bt = _fetch_one(
        """
        SELECT profit_factor, sharpe, sortino, win_rate_pct, max_drawdown_pct,
               total_return_pct, total_trades
        FROM backtests
        WHERE strategy_instance_id = %s AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST LIMIT 1
        """,
        (strategy_instance_id,),
    )
    hard_dd = float((si.get("params") or {}).get("max_drawdown_pct", 15.0))
    verdict, reason = _decide(realized, bt, hard_dd)

    return {
        "strategy_instance_id": strategy_instance_id,
        "strategy_code": si.get("strategy_code", "unknown"),
        "symbol": si.get("symbol", "unknown"),
        "timeframe": si.get("timeframe", "unknown"),
        "window_start": window_start.isoformat(),
        "window_end": now.isoformat(),
        "generated_at": now.isoformat(),
        "realized": realized,
        "expected": bt,
        "verdict": verdict,
        "verdict_reason": reason,
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Live strategy retrospective.")
    p.add_argument("--strategy-instance", required=True)
    p.add_argument("--window-days", type=int, default=30)
    p.add_argument(
        "--out-dir",
        default="/Users/shinzo/Desktop/whyman404/dev-team/09-quant-kairos-toki/work/forex-bot-phase1/retrospectives",
    )
    args = p.parse_args(argv)

    report = build_report(args.strategy_instance, args.window_days)
    md = render_markdown(report)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    yyyymm = datetime.now(tz=timezone.utc).strftime("%Y%m")
    fname = f"{yyyymm}-{report['strategy_code']}-{report['strategy_instance_id'][:8]}.md"
    path = out_dir / fname
    path.write_text(md)
    logger.info("wrote %s", path)
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
