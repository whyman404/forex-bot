"""
test_kill_switch.py

Canonical pytest for the kill switch on max-drawdown breach.

Why this test is the most important in the codebase
---------------------------------------------------
The kill switch is the user's ONLY guarantee that, when something goes wrong,
their bot stops trading. If this test does not fail when the implementation is
broken, every user is exposed to runaway loss.

This test exercises three layers in one scenario:
1. RiskManager computes drawdown from the equity stream
2. RiskManager raises CircuitBreaker when peak->current >= max_dd
3. OMS observes the breach, sets the strategy to STOPPED, cancels in-flight
   intent, and records audit_log

Owner: Themis Saori + Kairos Toki
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

import pytest

# Under test (paths align with planned trading-engine layout)
from trading_engine.risk import RiskManager, RiskConfig, RiskBreach
from trading_engine.oms import OrderManagementSystem
from trading_engine.strategies.base import Signal, Side
from trading_engine.broker.paper import PaperBrokerAdapter
from trading_engine.types import StrategyInstance, StrategyStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass
class FakeClock:
    now: datetime

    def utcnow(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    # Fixed deterministic clock — no real time anywhere.
    return FakeClock(now=datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc))


@pytest.fixture
def risk_config() -> RiskConfig:
    return RiskConfig(
        risk_per_trade_pct=0.01,
        max_drawdown_pct=0.20,   # 20% peak-to-trough -> kill switch
        daily_loss_limit_pct=0.02,
        max_concurrent_orders=1,
        leverage_cap=30,
    )


@pytest.fixture
def risk_manager(risk_config, clock) -> RiskManager:
    return RiskManager(config=risk_config, clock=clock)


@pytest.fixture
def broker() -> PaperBrokerAdapter:
    return PaperBrokerAdapter(initial_equity=10_000.0)


@pytest.fixture
def oms(risk_manager, broker, clock) -> OrderManagementSystem:
    return OrderManagementSystem(risk=risk_manager, broker=broker, clock=clock)


@pytest.fixture
def strategy_instance() -> StrategyInstance:
    return StrategyInstance(
        id="si-1",
        user_id="u-1",
        strategy_name="GoldLondonBreakout",
        status=StrategyStatus.RUNNING,
        paper=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def feed_equity_curve(rm: RiskManager, points: List[float]) -> None:
    """Push equity samples to RiskManager so peak/drawdown are computed."""
    for p in points:
        rm.observe_equity(p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDrawdownBreaker:
    def test_no_breach_within_limit(self, risk_manager):
        # Peak 10_000 -> trough 8_100 -> 19% drawdown < 20%
        feed_equity_curve(risk_manager, [10_000, 9_500, 8_500, 8_100])
        assert risk_manager.is_circuit_open() is False
        assert risk_manager.current_drawdown_pct() == pytest.approx(0.19, abs=1e-9)

    def test_breach_at_exactly_limit_trips_breaker(self, risk_manager):
        # 20.0% drawdown — limit is inclusive (safer for users)
        feed_equity_curve(risk_manager, [10_000, 10_500, 8_400])  # peak 10_500 -> 8_400 = 20%
        assert risk_manager.is_circuit_open() is True
        assert risk_manager.breach_reason() == RiskBreach.MAX_DRAWDOWN

    def test_breach_does_not_reset_on_recovery(self, risk_manager):
        # Tripped by drawdown, then equity recovers — breaker stays open.
        feed_equity_curve(risk_manager, [10_000, 8_000])           # 20%
        assert risk_manager.is_circuit_open() is True
        feed_equity_curve(risk_manager, [9_500, 10_000, 10_500])
        assert risk_manager.is_circuit_open() is True, (
            "Operator must explicitly reset; equity recovery must NOT silently rearm trading."
        )

    def test_explicit_operator_reset_clears_breaker(self, risk_manager):
        feed_equity_curve(risk_manager, [10_000, 8_000])
        assert risk_manager.is_circuit_open() is True
        risk_manager.operator_reset(operator_id="ops-1", reason="post-incident review complete")
        assert risk_manager.is_circuit_open() is False


class TestKillSwitchE2EOnDrawdown:
    """End-to-end at the engine layer (no network): signal -> risk -> stopped."""

    def test_signal_after_drawdown_is_rejected_and_strategy_stops(
        self, oms, risk_manager, strategy_instance, clock
    ):
        # Set up: equity drops past max DD before next signal.
        feed_equity_curve(risk_manager, [10_000, 7_900])  # 21% drawdown -> breach
        assert risk_manager.is_circuit_open() is True

        signal = Signal(
            strategy_instance_id=strategy_instance.id,
            side=Side.BUY,
            symbol="XAUUSD",
            volume=0.1,
            sl_price=1800.0,
            tp_price=1820.0,
            generated_at=clock.utcnow(),
        )

        result = oms.handle_signal(strategy_instance, signal)

        # 1. Order must NOT be placed.
        assert result.placed is False
        assert result.reason == "RISK_BREACH:MAX_DRAWDOWN"
        assert oms.broker.placed_orders == [], (
            "Order placed after kill switch tripped — this is the single most "
            "dangerous bug this project can ship."
        )

        # 2. Strategy must be flipped to STOPPED.
        assert strategy_instance.status == StrategyStatus.STOPPED
        assert strategy_instance.stopped_at == clock.utcnow()
        assert strategy_instance.stopped_reason == "RISK_BREACH:MAX_DRAWDOWN"

        # 3. Audit trail must record who/what/when.
        log = oms.audit_log_for(strategy_instance.id)
        assert any(
            entry.action == "kill_switch_triggered"
            and entry.actor == "RiskManager"
            and entry.metadata["reason"] == "MAX_DRAWDOWN"
            for entry in log
        ), "kill_switch_triggered audit_log entry is required for compliance."

    def test_in_flight_signals_after_breach_in_same_tick_are_all_rejected(
        self, oms, risk_manager, strategy_instance, clock
    ):
        """If 3 signals arrive at the same tick the breach was detected, none must fill."""
        feed_equity_curve(risk_manager, [10_000, 7_900])

        signals = [
            Signal(strategy_instance.id, Side.BUY, "XAUUSD", 0.1, 1800.0, 1820.0, clock.utcnow()),
            Signal(strategy_instance.id, Side.SELL, "XAUUSD", 0.1, 1820.0, 1800.0, clock.utcnow()),
            Signal(strategy_instance.id, Side.BUY, "BTCUSDT", 0.01, 60000.0, 61000.0, clock.utcnow()),
        ]
        for s in signals:
            r = oms.handle_signal(strategy_instance, s)
            assert r.placed is False, "Any signal after breach must be rejected."

        assert oms.broker.placed_orders == []
        assert strategy_instance.status == StrategyStatus.STOPPED

    def test_operator_kill_switch_button_stops_engine_within_one_tick(
        self, oms, strategy_instance, clock
    ):
        """User pressing the kill switch in UI -> engine receives stop event.

        This simulates what the API does when POST /strategy-instances/:id/stop fires.
        """
        assert strategy_instance.status == StrategyStatus.RUNNING

        oms.stop(strategy_instance, actor="user:u-1", reason="user_request")

        assert strategy_instance.status == StrategyStatus.STOPPED
        assert strategy_instance.stopped_reason == "user_request"

        # New signals are silently rejected.
        signal = Signal(
            strategy_instance.id, Side.BUY, "XAUUSD", 0.1, 1800.0, 1820.0, clock.utcnow()
        )
        result = oms.handle_signal(strategy_instance, signal)
        assert result.placed is False
        assert result.reason == "STRATEGY_STOPPED"

        # Audit log records who pressed it.
        log = oms.audit_log_for(strategy_instance.id)
        assert any(
            e.action == "stop" and e.actor == "user:u-1" and e.metadata["reason"] == "user_request"
            for e in log
        )


class TestKillSwitchInvariants:
    def test_kill_switch_is_idempotent(self, oms, strategy_instance):
        oms.stop(strategy_instance, actor="user:u-1", reason="user_request")
        first_stopped_at = strategy_instance.stopped_at
        oms.stop(strategy_instance, actor="user:u-1", reason="user_request_again")
        # Repeated stop must be a no-op (idempotent), do not overwrite reason/time.
        assert strategy_instance.stopped_at == first_stopped_at
        assert strategy_instance.stopped_reason == "user_request"
