"""Circuit breakers — automatic halt + kill triggers for live trading.

Four breakers:
    1. Daily loss   — realized PnL today > daily_loss_pct of start-of-day equity
                      → halt new entries until UTC midnight rolls.
    2. Max drawdown — peak-to-trough drawdown >= max_dd_pct
                      → KILL: close all positions, stop engine.
    3. Broker disconnect — no successful bridge call for `disconnect_grace_sec`
                           → halt (do not enter) + alert. Engine resumes on
                             successful reconnect.
    4. Abnormal slippage — observed slippage vs modeled (cumulative)
                           > slippage_alarm_x × baseline → halt + alert.

The breakers DO NOT decide policy — they expose a `verdict()` method the
engine consults before every new entry. The engine is responsible for
acting on a `KILL` verdict (closing positions, calling internal_client).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(Enum):
    OK = "ok"
    HALT = "halt"  # block new entries; existing positions OK
    KILL = "kill"  # close all positions + stop engine


@dataclass
class BreakerLimits:
    daily_loss_pct: float = 5.0
    max_drawdown_pct: float = 15.0
    disconnect_grace_sec: float = 300.0  # 5 min
    slippage_alarm_x: float = 3.0
    slippage_min_samples: int = 5


@dataclass
class BreakerState:
    start_of_day_equity: float = 10_000.0
    peak_equity: float = 10_000.0
    realized_pnl_today: float = 0.0
    current_equity: float = 10_000.0
    last_broker_ok_at: float = field(default_factory=time.time)
    slippage_samples: list[float] = field(default_factory=list)
    slippage_baseline: float | None = None  # set after first N samples
    today_utc_date: str = ""  # YYYY-MM-DD
    killed: bool = False
    halted: bool = False
    last_reason: str = ""


class CircuitBreaker:
    """Stateful — one instance per strategy instance (per account)."""

    def __init__(self, limits: BreakerLimits | None = None, initial_equity: float = 10_000.0):
        self.limits = limits or BreakerLimits()
        self.state = BreakerState(
            start_of_day_equity=initial_equity,
            peak_equity=initial_equity,
            current_equity=initial_equity,
            today_utc_date=time.strftime("%Y-%m-%d", time.gmtime()),
        )

    # ------------------------------------------------------------------
    # State updates
    # ------------------------------------------------------------------
    def on_equity(self, equity: float) -> None:
        self.state.current_equity = equity
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity

    def on_trade_closed(self, pnl: float) -> None:
        self._roll_day()
        self.state.realized_pnl_today += pnl

    def on_broker_ok(self) -> None:
        self.state.last_broker_ok_at = time.time()

    def on_slippage_sample(self, slippage_abs: float) -> None:
        """Push observed |fill - quote| sample.

        After `slippage_min_samples`, the median becomes the baseline. From
        then on, individual samples > baseline * slippage_alarm_x trigger HALT.
        """
        self.state.slippage_samples.append(slippage_abs)
        if (
            self.state.slippage_baseline is None
            and len(self.state.slippage_samples) >= self.limits.slippage_min_samples
        ):
            sorted_s = sorted(self.state.slippage_samples)
            mid = len(sorted_s) // 2
            self.state.slippage_baseline = sorted_s[mid]

    # ------------------------------------------------------------------
    # Verdict — call before any new entry / on every monitor tick
    # ------------------------------------------------------------------
    def verdict(self) -> tuple[Verdict, str]:
        self._roll_day()

        if self.state.killed:
            return Verdict.KILL, self.state.last_reason

        # Max DD — KILL
        peak = max(self.state.peak_equity, self.state.start_of_day_equity)
        if peak > 0:
            dd_pct = (1 - self.state.current_equity / peak) * 100
            if dd_pct >= self.limits.max_drawdown_pct:
                self.state.killed = True
                self.state.last_reason = f"max_drawdown_pct: {dd_pct:.2f}%"
                return Verdict.KILL, self.state.last_reason

        # Daily loss — HALT
        if self.state.start_of_day_equity > 0:
            daily_loss_pct = -self.state.realized_pnl_today / self.state.start_of_day_equity * 100
            if daily_loss_pct >= self.limits.daily_loss_pct:
                self.state.halted = True
                self.state.last_reason = f"daily_loss_pct: {daily_loss_pct:.2f}%"
                return Verdict.HALT, self.state.last_reason

        # Broker disconnect — HALT
        gap = time.time() - self.state.last_broker_ok_at
        if gap > self.limits.disconnect_grace_sec:
            self.state.halted = True
            self.state.last_reason = f"broker_disconnect: {gap:.0f}s"
            return Verdict.HALT, self.state.last_reason

        # Slippage anomaly — HALT
        baseline = self.state.slippage_baseline
        if baseline and baseline > 0 and self.state.slippage_samples:
            recent = self.state.slippage_samples[-1]
            if recent > baseline * self.limits.slippage_alarm_x:
                self.state.halted = True
                self.state.last_reason = (
                    f"slippage_anomaly: {recent:.4f} > {baseline:.4f} × "
                    f"{self.limits.slippage_alarm_x}"
                )
                return Verdict.HALT, self.state.last_reason

        # If we passed all checks, clear stale halted flag.
        if self.state.halted and not self.state.killed:
            self.state.halted = False
            self.state.last_reason = ""
        return Verdict.OK, ""

    # ------------------------------------------------------------------
    def _roll_day(self) -> None:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self.state.today_utc_date:
            self.state.today_utc_date = today
            self.state.realized_pnl_today = 0.0
            self.state.start_of_day_equity = self.state.current_equity
            self.state.halted = False  # fresh day, fresh chance

    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "killed": self.state.killed,
            "halted": self.state.halted,
            "reason": self.state.last_reason,
            "realized_pnl_today": self.state.realized_pnl_today,
            "start_of_day_equity": self.state.start_of_day_equity,
            "current_equity": self.state.current_equity,
            "peak_equity": self.state.peak_equity,
            "drawdown_pct": (
                (1 - self.state.current_equity / self.state.peak_equity) * 100
                if self.state.peak_equity > 0
                else 0.0
            ),
            "slippage_baseline": self.state.slippage_baseline,
            "slippage_samples_n": len(self.state.slippage_samples),
            "limits": vars(self.limits),
        }
