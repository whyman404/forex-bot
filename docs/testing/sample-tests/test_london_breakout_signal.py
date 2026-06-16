"""
test_london_breakout_signal.py

Canonical pytest for the Gold London Breakout strategy on canned OHLCV data.

Pattern under test (Kairos spec)
--------------------------------
- Asian range  : 00:00-07:00 UTC, take [low, high]
- Decision     : during 07:00-10:00 UTC (London open), if a 5m candle CLOSES above
                 the Asian high  -> BUY signal
                                  if a 5m candle CLOSES below the Asian low
                                  -> SELL signal
- Stop loss    : opposite side of Asian range minus a small buffer
- Take profit  : RR >= 1:1.5 from entry
- Anti-fakeout : require close > range_high (NOT high > range_high) — wicks alone do not signal
- Anti-spike   : optional news filter (NFP, CPI window) blocks signals — covered separately

Why we test on canned fixtures
------------------------------
Real broker data is non-deterministic in tests. We hand-build OHLCV frames so the
expected behavior is unambiguous.

Owner: Themis Saori + Kairos Toki
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd
import pytest

# Under test
from trading_engine.strategies.london_breakout import GoldLondonBreakout, LBConfig
from trading_engine.strategies.base import Side


UTC = timezone.utc


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _bar(ts: datetime, o: float, h: float, l: float, c: float, v: float = 100.0) -> dict:
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _frame(rows: List[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


def _bars_5m_for_day(
    day: datetime,
    asian_low: float,
    asian_high: float,
    london_bars: List[dict],
) -> pd.DataFrame:
    """
    Build a single-day 5m frame for XAUUSD:
      - 00:00-07:00 UTC: oscillating bars inside [asian_low, asian_high]
      - 07:00 onward:   user-supplied london_bars
    """
    rows = []
    t = day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    end_asian = day.replace(hour=7, minute=0, tzinfo=UTC)
    mid = (asian_low + asian_high) / 2
    while t < end_asian:
        rows.append(_bar(t, mid, asian_high - 0.1, asian_low + 0.1, mid))
        t += timedelta(minutes=5)
    rows.extend(london_bars)
    return _frame(rows)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg() -> LBConfig:
    return LBConfig(
        symbol="XAUUSD",
        timeframe="5m",
        london_window=("07:00", "10:00"),
        sl_buffer_pips=2.0,
        rr=1.5,
        require_close_break=True,
        news_filter_enabled=False,  # tested separately
    )


@pytest.fixture
def strategy(cfg) -> GoldLondonBreakout:
    return GoldLondonBreakout(config=cfg)


# ---------------------------------------------------------------------------
# Test cases (numbering matches backtest-validation.md §2.1)
# ---------------------------------------------------------------------------

class TestLondonBreakout:
    def test_LB01_clear_breakout_day_emits_buy_with_sane_sl_tp(self, strategy):
        """LB-01: clean breakout above Asian high -> BUY."""
        day = datetime(2026, 5, 12, tzinfo=UTC)  # weekday
        asian_low, asian_high = 1800.0, 1810.0

        london_bars = [
            # 07:00 — small consolidation
            _bar(day.replace(hour=7, minute=0, tzinfo=UTC), 1809.8, 1810.2, 1809.5, 1810.1),
            # 07:05 — breakout CLOSE above 1810.0
            _bar(day.replace(hour=7, minute=5, tzinfo=UTC), 1810.0, 1812.5, 1809.9, 1812.0),
            # 07:10 — continuation
            _bar(day.replace(hour=7, minute=10, tzinfo=UTC), 1812.0, 1813.0, 1811.9, 1812.8),
        ]
        bars = _bars_5m_for_day(day, asian_low, asian_high, london_bars)

        signals = list(strategy.signals(bars))

        assert len(signals) == 1, f"Expected exactly 1 BUY signal, got {len(signals)}"
        s = signals[0]
        assert s.side == Side.BUY
        assert s.symbol == "XAUUSD"
        assert s.generated_at == bars.index[bars.index.get_loc(day.replace(hour=7, minute=5, tzinfo=UTC))]
        # SL below asian_low minus buffer
        assert s.sl_price == pytest.approx(asian_low - 0.20, abs=1e-9), \
            "SL must be Asian low minus 2 pip buffer (XAUUSD 1 pip = 0.10)"
        # TP at RR >= 1:1.5
        risk = s.entry_price - s.sl_price
        reward = s.tp_price - s.entry_price
        assert reward / risk >= 1.5 - 1e-9, f"RR violated: {reward/risk}"

    def test_LB02_flat_day_emits_no_signal(self, strategy):
        """LB-02: range stays inside Asian range — no signal."""
        day = datetime(2026, 5, 13, tzinfo=UTC)
        asian_low, asian_high = 1805.0, 1808.0
        london_bars = [
            _bar(day.replace(hour=h, minute=m, tzinfo=UTC),
                 1806.0, 1807.5, 1805.5, 1806.5)
            for h, m in [(7, 0), (7, 5), (7, 10), (7, 15), (7, 20), (8, 0), (9, 0), (9, 55)]
        ]
        bars = _bars_5m_for_day(day, asian_low, asian_high, london_bars)

        signals = list(strategy.signals(bars))
        assert signals == [], f"Expected no signal on flat day, got {signals}"

    def test_LB03_false_breakout_wick_only_does_not_signal(self, strategy):
        """LB-03: wick crosses range but close inside — must NOT signal."""
        day = datetime(2026, 5, 14, tzinfo=UTC)
        asian_low, asian_high = 1805.0, 1810.0
        london_bars = [
            # high pokes 1810.5 but closes 1808.0 -> close < range_high -> no signal
            _bar(day.replace(hour=7, minute=5, tzinfo=UTC), 1809.8, 1810.5, 1807.5, 1808.0),
            _bar(day.replace(hour=7, minute=10, tzinfo=UTC), 1808.0, 1808.5, 1807.0, 1807.5),
        ]
        bars = _bars_5m_for_day(day, asian_low, asian_high, london_bars)
        assert list(strategy.signals(bars)) == []

    def test_LB04_breakout_outside_london_window_is_ignored(self, strategy):
        """LB-04: even a clear breakout at 11:30 UTC is ignored (out of window)."""
        day = datetime(2026, 5, 15, tzinfo=UTC)
        asian_low, asian_high = 1800.0, 1810.0
        london_bars = [
            # During London window: nothing
            _bar(day.replace(hour=7, minute=0, tzinfo=UTC), 1808.0, 1809.0, 1807.0, 1808.5),
            # AFTER London window: clear breakout — must be ignored
            _bar(day.replace(hour=11, minute=30, tzinfo=UTC), 1810.0, 1813.0, 1809.9, 1812.5),
        ]
        bars = _bars_5m_for_day(day, asian_low, asian_high, london_bars)
        assert list(strategy.signals(bars)) == []

    def test_LB05_dst_boundary_uses_utc_windows_correctly(self, strategy):
        """LB-05: on DST change day, the strategy still keys off UTC 07:00 (not local 07:00)."""
        # March 2026 DST day in Europe is 2026-03-29 (last Sunday in March)
        day = datetime(2026, 3, 30, tzinfo=UTC)  # Monday after DST
        asian_low, asian_high = 1900.0, 1910.0
        london_bars = [
            _bar(day.replace(hour=7, minute=5, tzinfo=UTC), 1909.5, 1912.0, 1909.0, 1911.5),
        ]
        bars = _bars_5m_for_day(day, asian_low, asian_high, london_bars)
        signals = list(strategy.signals(bars))
        assert len(signals) == 1 and signals[0].side == Side.BUY

    def test_LB07_no_look_ahead_future_bar_modifications_do_not_change_signal(self, strategy):
        """
        LB-07 (look-ahead guard): the signal for bar t must depend only on bars <= t.
        We compute the signal once on the original frame, then mutate a FUTURE bar
        and recompute the signal at the SAME timestamp — it must be identical.
        """
        day = datetime(2026, 5, 12, tzinfo=UTC)
        asian_low, asian_high = 1800.0, 1810.0
        signal_time = day.replace(hour=7, minute=5, tzinfo=UTC)
        london_bars = [
            _bar(signal_time, 1810.0, 1812.5, 1809.9, 1812.0),
            _bar(day.replace(hour=7, minute=10, tzinfo=UTC), 1812.0, 1813.0, 1811.9, 1812.8),
        ]
        bars = _bars_5m_for_day(day, asian_low, asian_high, london_bars)

        baseline = [s for s in strategy.signals(bars) if s.generated_at == signal_time]
        assert len(baseline) == 1

        poisoned = bars.copy()
        # Mutate ONLY bars strictly after signal_time
        future_mask = poisoned.index > signal_time
        poisoned.loc[future_mask, "high"] += 50.0  # absurd spike
        poisoned.loc[future_mask, "low"]  -= 50.0
        poisoned.loc[future_mask, "close"] += 25.0

        after = [s for s in strategy.signals(poisoned) if s.generated_at == signal_time]
        assert after == baseline, (
            "Signal at time t changed when future bars were mutated -> "
            "look-ahead bias in the strategy. This is a P0 honesty defect."
        )

    @pytest.mark.parametrize("range_width,expected_min_rr", [(5.0, 1.5), (10.0, 1.5), (20.0, 1.5)])
    def test_rr_always_at_least_target(self, strategy, range_width, expected_min_rr):
        """RR must always meet config.rr regardless of range width."""
        day = datetime(2026, 5, 19, tzinfo=UTC)
        asian_low = 1800.0
        asian_high = asian_low + range_width
        london_bars = [
            _bar(day.replace(hour=7, minute=5, tzinfo=UTC),
                 asian_high - 0.1, asian_high + range_width * 0.3, asian_high - 0.2, asian_high + 0.5),
        ]
        bars = _bars_5m_for_day(day, asian_low, asian_high, london_bars)
        signals = list(strategy.signals(bars))
        assert signals, "Expected a signal for clear breakout"
        s = signals[0]
        rr = (s.tp_price - s.entry_price) / (s.entry_price - s.sl_price)
        assert rr >= expected_min_rr - 1e-9
