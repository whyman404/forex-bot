"""Walk-forward analysis CLI.

Usage:
    python -m cli.walk_forward \
        --strategy london_breakout \
        --asset XAUUSD \
        --tf M15 \
        --start 2022-01-01 --end 2025-12-31 \
        --train-days 180 --test-days 30 --step 30 \
        --params '{"buffer_pips": 5.0}' \
        --out walk-forward-london.json

Outputs per-window metrics and a parameter-stability rollup. We
intentionally do NOT refit parameters here — the goal is to expose
performance degradation in fixed-params over time. If the user wants a
proper parameter-stability sweep, the next iteration will accept
`--param-grid` (Phase 3).

Why we care:
- Backtest on one window flatters every strategy.
- Walk-forward exposes regime decay — the only honest test before live.
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Walk-forward backtest runner.")
    p.add_argument("--strategy", required=True)
    p.add_argument("--asset", required=True)
    p.add_argument("--tf", required=True, help="M5 | M15 | H1 | H4")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--train-days", type=int, default=180)
    p.add_argument("--test-days", type=int, default=30)
    p.add_argument("--step", type=int, default=30)
    p.add_argument("--params", default="{}", help="JSON-encoded strategy params")
    p.add_argument("--out", default=None, help="Path to write JSON report (stdout if absent)")
    return p.parse_args(argv)


def _windows(start: datetime, end: datetime, train: int, test: int, step: int):
    """Yield (train_start, train_end, test_start, test_end) tuples."""
    cur = start
    while True:
        train_end = cur + timedelta(days=train)
        test_end = train_end + timedelta(days=test)
        if test_end > end:
            break
        yield cur, train_end, train_end, test_end
        cur = cur + timedelta(days=step)


def _run_window(
    strategy_code: str,
    asset: str,
    tf: str,
    start: datetime,
    end: datetime,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Run one backtest window and return its summary."""
    # Lazy import so `--help` is fast.
    import uuid

    from workers.backtest_worker import run_backtest_job

    res = run_backtest_job(
        backtest_id=str(uuid.uuid4()),
        strategy_code=strategy_code,
        asset=asset,
        timeframe=tf,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        params=params,
    )
    summary = res.get("summary", {}) if res.get("status") == "completed" else {}
    return {
        "status": res.get("status"),
        "summary": summary,
    }


def _aggregate(windows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up per-window metrics for the report header."""
    test_results = [w["test"] for w in windows if w["test"].get("status") == "completed"]
    metrics = ["profit_factor", "sharpe", "sortino", "total_return_pct", "max_drawdown_pct", "win_rate_pct"]
    rollup: dict[str, Any] = {"n_windows": len(test_results)}
    for m in metrics:
        vals = [s["summary"].get(m) for s in test_results if s["summary"].get(m) is not None]
        if not vals:
            continue
        rollup[m] = {
            "mean": round(statistics.fmean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "stdev": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
        }
    # Parameter stability proxy — variance of `profit_factor` across windows.
    pf = rollup.get("profit_factor")
    if pf and pf["mean"] > 0:
        rollup["stability_ratio"] = round(pf["stdev"] / pf["mean"], 3)
        rollup["verdict_hint"] = (
            "stable"
            if rollup["stability_ratio"] < 0.4
            else "borderline"
            if rollup["stability_ratio"] < 0.7
            else "unstable"
        )
    return rollup


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args(argv)
    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")
    params = json.loads(args.params)

    rows: list[dict[str, Any]] = []
    for ts, te, vs, ve in _windows(start, end, args.train_days, args.test_days, args.step):
        logger.info("window train=%s..%s test=%s..%s", ts.date(), te.date(), vs.date(), ve.date())
        # We run the *test* slice with frozen params (no refit) — the train
        # slice is informational here. Phase 3 will add a refit hook.
        train_summary = _run_window(args.strategy, args.asset, args.tf, ts, te, params)
        test_summary = _run_window(args.strategy, args.asset, args.tf, vs, ve, params)
        rows.append(
            {
                "train_start": ts.date().isoformat(),
                "train_end": te.date().isoformat(),
                "test_start": vs.date().isoformat(),
                "test_end": ve.date().isoformat(),
                "train": train_summary,
                "test": test_summary,
            }
        )

    report = {
        "strategy": args.strategy,
        "asset": args.asset,
        "timeframe": args.tf,
        "params": params,
        "train_days": args.train_days,
        "test_days": args.test_days,
        "step_days": args.step,
        "windows": rows,
        "rollup": _aggregate(rows),
    }
    out_json = json.dumps(report, indent=2, default=str)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out_json)
        logger.info("wrote %s", args.out)
    else:
        sys.stdout.write(out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
