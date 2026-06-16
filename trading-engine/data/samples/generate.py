"""Deterministic sample OHLCV generator for offline dev.

Why
---
We need realistic-looking OHLCV CSVs that:
- Trigger at least one trade in every strategy (London, NY, EMA/ADX, EMA/RSI,
  Donchian, Grid) so smoke tests + API tests are non-trivial.
- Stay small enough to commit (<100KB each).
- Are reproducible — seeded `numpy.random.Generator`.

How
---
- Multi-regime random walk: trending up, ranging, trending down, volatile.
- Each regime gets a drift + vol parameter.
- We bake in deliberate "Asian sessions" + "London breakout" structure for
  XAUUSD samples so session-aware strategies fire.

Usage
-----
    python data/samples/generate.py

This rewrites all CSVs under data/samples/. They are also checked in, so
running the script is OPTIONAL — the dev container works out of the box.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

SAMPLES_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Core random-walk generator
# ---------------------------------------------------------------------------
def _regime_walk(
    rng: np.random.Generator,
    n: int,
    start_price: float,
    regimes: list[tuple[int, float, float]],
) -> np.ndarray:
    """Generate `n` close-prices through a sequence of regimes.

    Each regime is (n_bars, drift_per_bar, vol_per_bar).
    """
    closes = np.zeros(n)
    closes[0] = start_price
    i = 1
    for n_bars, drift, vol in regimes:
        end = min(i + n_bars, n)
        steps = rng.normal(loc=drift, scale=vol, size=end - i)
        # Multiplicative (geometric) walk to avoid negative prices.
        closes[i:end] = closes[i - 1] * np.exp(np.cumsum(steps))
        i = end
        if i >= n:
            break
    # Fill any leftover bars with a mild continuation.
    if i < n:
        leftover = rng.normal(loc=0.0, scale=0.001, size=n - i)
        closes[i:] = closes[i - 1] * np.exp(np.cumsum(leftover))
    return closes


def _ohlc_from_close(
    rng: np.random.Generator,
    closes: np.ndarray,
    intrabar_vol: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Synthesize open/high/low from a close series.

    open[i] = close[i-1] (chain continuity).
    high/low add a positive/negative noise envelope.
    """
    n = len(closes)
    opens = np.empty(n)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]

    noise_hi = np.abs(rng.normal(0, intrabar_vol, n)) * closes
    noise_lo = np.abs(rng.normal(0, intrabar_vol, n)) * closes

    highs = np.maximum(opens, closes) + noise_hi
    lows = np.minimum(opens, closes) - noise_lo
    return opens, highs, lows, closes


# ---------------------------------------------------------------------------
# Per-sample generators
# ---------------------------------------------------------------------------
def gen_xauusd_m5(out_path: Path) -> None:
    """Gold M5, ~5 days. Designed to trigger London Breakout + NY Killzone.

    We force:
    - A wide Asian range early each day.
    - A directional breakout at 08:00 GMT.
    - A reversal sweep around 13:30–16:00 GMT.
    """
    rng = np.random.default_rng(42)
    start = datetime(2025, 6, 2, 0, 0, tzinfo=timezone.utc)  # Monday
    bars_per_day = 24 * 12  # 288 bars per day at M5
    n_days = 5
    n = bars_per_day * n_days

    closes = np.zeros(n)
    closes[0] = 2350.0
    for d in range(n_days):
        base = d * bars_per_day
        # Asian session 00:00–08:00 GMT = bars [0, 96) — gentle range.
        for i in range(base, base + 96):
            if i == 0:
                continue
            closes[i] = closes[i - 1] * np.exp(rng.normal(0.0, 0.0007))
        # 08:00 GMT — directional breakout.
        breakout_dir = 1 if d % 2 == 0 else -1
        for i in range(base + 96, base + 168):  # 08:00–14:00
            closes[i] = closes[i - 1] * np.exp(
                rng.normal(0.0008 * breakout_dir, 0.0009)
            )
        # 13:30+ NY session — partial reversal sweep.
        for i in range(base + 168, base + 240):  # 14:00–20:00
            closes[i] = closes[i - 1] * np.exp(
                rng.normal(-0.0004 * breakout_dir, 0.0011)
            )
        # Late session drift.
        for i in range(base + 240, base + bars_per_day):
            closes[i] = closes[i - 1] * np.exp(rng.normal(0.0, 0.0005))

    opens, highs, lows, closes = _ohlc_from_close(rng, closes, 0.0006)
    volumes = rng.integers(500, 5000, size=n)
    _write_csv(out_path, start, timedelta(minutes=5), opens, highs, lows, closes, volumes)


def gen_xauusd_h1(out_path: Path) -> None:
    """Gold H1, ~1 month. Designed for EMA50 + ADX trend."""
    rng = np.random.default_rng(7)
    start = datetime(2025, 5, 5, 0, 0, tzinfo=timezone.utc)
    n = 30 * 24  # 30 days of H1

    closes = _regime_walk(
        rng,
        n,
        start_price=2300.0,
        regimes=[
            (96, 0.0015, 0.0030),    # 4-day uptrend
            (72, -0.0001, 0.0018),   # ranging
            (120, -0.0017, 0.0034),  # 5-day downtrend
            (96, 0.0002, 0.0022),    # ranging
            (96, 0.0018, 0.0030),    # 4-day uptrend
            (240, 0.0000, 0.0025),   # rest = noise
        ],
    )
    opens, highs, lows, closes = _ohlc_from_close(rng, closes, 0.0015)
    volumes = rng.integers(800, 8000, size=n)
    _write_csv(out_path, start, timedelta(hours=1), opens, highs, lows, closes, volumes)


def gen_btcusdt_h1(out_path: Path) -> None:
    """BTC H1, ~1 month. Designed for Donchian + Grid."""
    rng = np.random.default_rng(101)
    start = datetime(2025, 5, 5, 0, 0, tzinfo=timezone.utc)
    n = 30 * 24

    closes = _regime_walk(
        rng,
        n,
        start_price=65000.0,
        regimes=[
            (72, 0.0020, 0.0050),    # rally
            (120, 0.0001, 0.0030),   # range — feeds grid
            (96, 0.0025, 0.0045),    # breakout — feeds Donchian
            (96, -0.0018, 0.0050),   # pullback
            (336, 0.0003, 0.0035),   # mixed
        ],
    )
    opens, highs, lows, closes = _ohlc_from_close(rng, closes, 0.0030)
    volumes = rng.integers(1000, 20000, size=n)
    _write_csv(out_path, start, timedelta(hours=1), opens, highs, lows, closes, volumes)


def gen_btcusdt_h4(out_path: Path) -> None:
    """BTC H4, ~3 months. Designed for EMA12/26 + RSI swing."""
    rng = np.random.default_rng(202)
    start = datetime(2025, 3, 5, 0, 0, tzinfo=timezone.utc)
    n = 90 * 6  # 90 days, 6 H4 bars/day

    closes = _regime_walk(
        rng,
        n,
        start_price=55000.0,
        regimes=[
            (60, 0.0040, 0.0080),    # 10-day rally
            (40, -0.0030, 0.0075),   # correction
            (80, 0.0035, 0.0070),    # rally
            (60, -0.0040, 0.0080),   # correction
            (90, 0.0025, 0.0065),    # rally
            (210, 0.0005, 0.0060),   # mixed swings
        ],
    )
    opens, highs, lows, closes = _ohlc_from_close(rng, closes, 0.0060)
    volumes = rng.integers(2000, 30000, size=n)
    _write_csv(out_path, start, timedelta(hours=4), opens, highs, lows, closes, volumes)


# ---------------------------------------------------------------------------
# CSV writer (csv module — no pandas dep at generation time)
# ---------------------------------------------------------------------------
def _write_csv(
    path: Path,
    start: datetime,
    step: timedelta,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["datetime", "open", "high", "low", "close", "volume"])
        ts = start
        for i in range(len(closes)):
            writer.writerow(
                [
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    f"{opens[i]:.2f}",
                    f"{highs[i]:.2f}",
                    f"{lows[i]:.2f}",
                    f"{closes[i]:.2f}",
                    int(volumes[i]),
                ]
            )
            ts += step


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    gen_xauusd_m5(SAMPLES_DIR / "XAUUSD_M5_sample.csv")
    gen_xauusd_h1(SAMPLES_DIR / "XAUUSD_H1_sample.csv")
    gen_btcusdt_h1(SAMPLES_DIR / "BTCUSDT_H1_sample.csv")
    gen_btcusdt_h4(SAMPLES_DIR / "BTCUSDT_H4_sample.csv")
    print(f"Wrote samples to {SAMPLES_DIR}")


if __name__ == "__main__":
    main()
