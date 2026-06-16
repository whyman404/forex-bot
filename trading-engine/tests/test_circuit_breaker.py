"""Circuit breaker unit tests — verdicts under different fill / equity paths."""
from __future__ import annotations

import time

from live.circuit_breaker import BreakerLimits, CircuitBreaker, Verdict


def test_initial_verdict_is_ok():
    cb = CircuitBreaker(initial_equity=10_000)
    v, _ = cb.verdict()
    assert v == Verdict.OK


def test_daily_loss_halts():
    cb = CircuitBreaker(
        limits=BreakerLimits(daily_loss_pct=5.0, max_drawdown_pct=50.0),
        initial_equity=10_000,
    )
    cb.on_broker_ok()
    cb.on_trade_closed(-600)  # 6% loss
    v, reason = cb.verdict()
    assert v == Verdict.HALT
    assert "daily_loss_pct" in reason


def test_max_drawdown_kills():
    cb = CircuitBreaker(
        limits=BreakerLimits(daily_loss_pct=50.0, max_drawdown_pct=15.0),
        initial_equity=10_000,
    )
    cb.on_broker_ok()
    cb.on_equity(10_000)
    cb.on_equity(8_400)  # 16% drawdown from peak
    v, reason = cb.verdict()
    assert v == Verdict.KILL
    assert "max_drawdown" in reason


def test_broker_disconnect_halts():
    cb = CircuitBreaker(
        limits=BreakerLimits(disconnect_grace_sec=1.0),
        initial_equity=10_000,
    )
    cb.state.last_broker_ok_at = time.time() - 5.0
    v, reason = cb.verdict()
    assert v == Verdict.HALT
    assert "broker_disconnect" in reason


def test_slippage_alarm_halts():
    cb = CircuitBreaker(
        limits=BreakerLimits(slippage_alarm_x=2.0, slippage_min_samples=3),
        initial_equity=10_000,
    )
    cb.on_broker_ok()
    # 3 small samples set baseline at 0.1
    for s in [0.10, 0.10, 0.10]:
        cb.on_slippage_sample(s)
    cb.on_slippage_sample(0.30)  # 3x baseline → trip
    v, reason = cb.verdict()
    assert v == Verdict.HALT
    assert "slippage_anomaly" in reason


def test_kill_is_sticky():
    cb = CircuitBreaker(
        limits=BreakerLimits(max_drawdown_pct=10.0),
        initial_equity=10_000,
    )
    cb.on_broker_ok()
    cb.on_equity(10_000)
    cb.on_equity(8_500)
    v1, _ = cb.verdict()
    assert v1 == Verdict.KILL
    # Even after recovery the breaker stays killed (human must reset).
    cb.on_equity(11_000)
    v2, _ = cb.verdict()
    assert v2 == Verdict.KILL


def test_halt_clears_when_conditions_resolve():
    cb = CircuitBreaker(
        limits=BreakerLimits(disconnect_grace_sec=1.0),
        initial_equity=10_000,
    )
    cb.state.last_broker_ok_at = time.time() - 5.0
    assert cb.verdict()[0] == Verdict.HALT
    cb.on_broker_ok()
    assert cb.verdict()[0] == Verdict.OK
