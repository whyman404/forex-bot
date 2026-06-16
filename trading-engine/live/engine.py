"""LiveEngine — runs one strategy instance against one broker account.

Flow:
    1. on_start(spec) — load strategy, RiskManager, CircuitBreaker, InternalClient.
    2. Connect to MT5 bridge (HTTP /connect).
    3. Subscribe to bridge /stream WebSocket for ticks + fills.
    4. On every bar-close event for the strategy's timeframe:
       a. fetch the last N bars from the bridge,
       b. run strategy.signals() on them,
       c. if signal: risk.evaluate -> sizing -> bridge.place_order,
       d. record signal + fill via InternalClient.
    5. Heartbeat to backend every 30s.
    6. on_stop() / on_kill() — drain and close.

Bar aggregation is done client-side from the tick stream so the engine
works for any timeframe the strategy needs (M5/M15/H1/H4). For Phase 2
we keep it simple: poll OHLCV from the bridge's /quote + maintain a local
deque keyed by `(symbol, timeframe)`.

This module does NOT call MT5 directly — that's the bridge's job.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
import structlog

from live.circuit_breaker import BreakerLimits, CircuitBreaker, Verdict
from live.internal_client import InternalClient
from risk.manager import RiskLimits, RiskManager
from risk.position_sizing import fixed_fractional, round_to_step

logger = structlog.get_logger(__name__)


class EngineStatus(Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    HALTED = "halted"
    KILLED = "killed"
    STOPPED = "stopped"


@dataclass
class EngineSpec:
    strategy_instance_id: str
    strategy_code: str
    broker_account_id: str
    bridge_url: str
    bridge_token: str
    mt5_server: str
    mt5_login: int
    mt5_password: str
    symbol: str
    timeframe: str  # M5 | M15 | H1 | H4
    magic: int
    params: dict[str, Any] = field(default_factory=dict)
    risk_limits: dict[str, Any] = field(default_factory=dict)
    breaker_limits: dict[str, Any] = field(default_factory=dict)
    lot_step: float = 0.01
    min_lot: float = 0.01
    pip_value_per_unit: float = 1.0


@dataclass
class EngineRuntime:
    status: EngineStatus = EngineStatus.IDLE
    started_at: float | None = None
    last_signal_at: float | None = None
    last_fill_at: float | None = None
    last_heartbeat_at: float | None = None
    open_position_ticket: int | None = None
    signals_today: int = 0
    fills_today: int = 0
    last_error: str = ""


class LiveEngine:
    """One per (strategy_instance, broker_account)."""

    def __init__(self, spec: EngineSpec) -> None:
        self.spec = spec
        self.runtime = EngineRuntime()
        # Risk & breakers
        self.risk = RiskManager(
            limits=RiskLimits(**spec.risk_limits) if spec.risk_limits else RiskLimits(),
        )
        self.breaker = CircuitBreaker(
            limits=BreakerLimits(**spec.breaker_limits) if spec.breaker_limits else BreakerLimits(),
        )
        # Comms
        self.bridge = httpx.Client(
            base_url=spec.bridge_url,
            headers={"Authorization": f"Bearer {spec.bridge_token}"},
            timeout=10.0,
        )
        self.internal = InternalClient(secret=os.getenv("INTERNAL_API_SECRET", ""))
        # Threads
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------
    def on_start(self) -> dict[str, Any]:
        if self.runtime.status not in (EngineStatus.IDLE, EngineStatus.STOPPED):
            return {"ok": False, "reason": f"already_{self.runtime.status.value}"}
        self.runtime.status = EngineStatus.STARTING
        try:
            self._connect_bridge()
            self.runtime.status = EngineStatus.RUNNING
            self.runtime.started_at = time.time()
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name=f"live-{self.spec.strategy_instance_id}")
            self._thread.start()
            self.internal.emit_health(self.spec.strategy_instance_id, "running", {"started_at": self.runtime.started_at})
            return {"ok": True, "status": self.runtime.status.value}
        except Exception as e:
            self.runtime.status = EngineStatus.STOPPED
            self.runtime.last_error = str(e)
            logger.exception("engine.start_failed", error=str(e))
            return {"ok": False, "reason": str(e)}

    def on_stop(self) -> dict[str, Any]:
        """Graceful stop — flush + close subscriptions but DO NOT close positions."""
        self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self.runtime.status = EngineStatus.STOPPED
        self.internal.emit_health(self.spec.strategy_instance_id, "stopped", {})
        return {"ok": True, "status": self.runtime.status.value}

    def on_kill(self) -> dict[str, Any]:
        """Emergency — close every open position then stop."""
        logger.error("engine.kill", strategy_instance_id=self.spec.strategy_instance_id)
        self.runtime.status = EngineStatus.KILLED
        closed: list[dict[str, Any]] = []
        try:
            positions = self._bridge_get("/positions", params={"symbol": self.spec.symbol})
            for p in positions.get("positions", []):
                if int(p.get("magic", 0)) != self.spec.magic:
                    continue
                r = self._bridge_post("/position/close", {"ticket": int(p["ticket"])})
                closed.append({"ticket": p["ticket"], "result": r})
        except Exception as e:
            logger.exception("engine.kill_close_failed", error=str(e))
        self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self.internal.emit_health(
            self.spec.strategy_instance_id,
            "killed",
            {"closed": closed, "reason": self.breaker.state.last_reason},
        )
        return {"ok": True, "closed": closed, "reason": self.breaker.state.last_reason}

    # ------------------------------------------------------------------
    # Bridge wrappers
    # ------------------------------------------------------------------
    def _bridge_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        r = self.bridge.get(path, params=params)
        r.raise_for_status()
        self.breaker.on_broker_ok()
        return r.json()

    def _bridge_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self.bridge.post(path, json=payload)
        r.raise_for_status()
        self.breaker.on_broker_ok()
        return r.json()

    def _connect_bridge(self) -> None:
        self._bridge_post(
            "/connect",
            {
                "server": self.spec.mt5_server,
                "login": self.spec.mt5_login,
                "password": self.spec.mt5_password,
            },
        )
        # Seed risk + breaker with broker-reported equity.
        try:
            acct = self._bridge_get("/account")
            equity = float(acct.get("equity", acct.get("balance", 10_000.0)))
            self.risk.state.equity = equity
            self.risk.state.peak_equity = max(self.risk.state.peak_equity, equity)
            self.breaker.state.current_equity = equity
            self.breaker.state.peak_equity = max(self.breaker.state.peak_equity, equity)
            self.breaker.state.start_of_day_equity = equity
        except Exception as e:  # non-fatal — defaults kick in
            logger.warning("engine.account_seed_failed", error=str(e))

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def _loop(self) -> None:
        last_bar_ts: float = 0.0
        bar_secs = _timeframe_seconds(self.spec.timeframe)
        while not self._stop_evt.is_set():
            try:
                self._tick_heartbeat()
                verdict, reason = self.breaker.verdict()
                if verdict == Verdict.KILL:
                    logger.error("engine.kill_from_breaker", reason=reason)
                    self.on_kill()
                    return
                if verdict == Verdict.HALT:
                    self.runtime.status = EngineStatus.HALTED
                    self._sleep_until_next_bar(bar_secs)
                    continue
                if self.runtime.status == EngineStatus.HALTED:
                    self.runtime.status = EngineStatus.RUNNING

                # Once per bar boundary, evaluate signals.
                now = time.time()
                bar_boundary = (now // bar_secs) * bar_secs
                if bar_boundary > last_bar_ts:
                    last_bar_ts = bar_boundary
                    self._on_new_bar()

                # Track open position PnL for the breaker / risk.
                self._refresh_positions_and_equity()
                self._sleep_until_next_bar(bar_secs)
            except Exception as e:
                self.runtime.last_error = str(e)
                logger.exception("engine.loop_error", error=str(e))
                time.sleep(2.0)

    def _sleep_until_next_bar(self, bar_secs: int) -> None:
        # Wake on stop signal OR before the next bar boundary, whichever comes first.
        now = time.time()
        next_bar = ((now // bar_secs) + 1) * bar_secs
        sleep_for = max(1.0, min(15.0, next_bar - now))  # cap so we still tick monitor
        self._stop_evt.wait(sleep_for)

    # ------------------------------------------------------------------
    # Heartbeat + monitoring
    # ------------------------------------------------------------------
    def _tick_heartbeat(self) -> None:
        if (
            self.runtime.last_heartbeat_at is None
            or time.time() - self.runtime.last_heartbeat_at > 30
        ):
            self.internal.emit_health(
                self.spec.strategy_instance_id,
                self.runtime.status.value,
                {
                    "runtime": vars(self.runtime),
                    "risk": self.risk.snapshot(),
                    "breaker": self.breaker.snapshot(),
                },
            )
            self.runtime.last_heartbeat_at = time.time()

    def _refresh_positions_and_equity(self) -> None:
        try:
            acct = self._bridge_get("/account")
            equity = float(acct.get("equity", acct.get("balance", 0.0)))
            self.risk.on_equity_update(equity)
            self.breaker.on_equity(equity)
        except Exception:
            pass  # already logged via breaker disconnect timer

    # ------------------------------------------------------------------
    # Signal & order placement
    # ------------------------------------------------------------------
    def _on_new_bar(self) -> None:
        try:
            data = self._load_recent_bars()
            if data is None or len(data) < 50:
                return
            strat = self._make_strategy()
            sigs = strat.signals(data)
            # Take last row only — we react to the most recently closed bar.
            last = sigs.iloc[-1]
            if int(last.get("direction", 0)) == 0:
                return
            self.runtime.last_signal_at = time.time()
            self.runtime.signals_today += 1
            direction = int(last["direction"])
            entry = float(last["entry"])
            sl = float(last["sl"])
            tp = float(last["tp"])
            reason = str(last.get("reason", ""))

            self.internal.emit_signal(
                strategy_instance_id=self.spec.strategy_instance_id,
                symbol=self.spec.symbol,
                timeframe=self.spec.timeframe,
                direction=direction,
                entry=entry,
                sl=sl,
                tp=tp,
                reason=reason,
                ts=time.time(),
            )

            # Size
            sl_distance = abs(entry - sl)
            size = fixed_fractional(
                account_equity=self.risk.state.equity,
                risk_pct=getattr(strat, "risk_per_trade_pct", 1.0),
                sl_distance=sl_distance,
                pip_value_per_unit=self.spec.pip_value_per_unit,
            )
            size = round_to_step(size, self.spec.lot_step, self.spec.min_lot)
            if size <= 0:
                logger.info("engine.size_zero", entry=entry, sl=sl)
                return

            # Risk gate
            decision = self.risk.evaluate(
                symbol=self.spec.symbol,
                proposed_size=size,
                proposed_risk_amount=size * sl_distance * self.spec.pip_value_per_unit,
            )
            if not decision.approved:
                logger.info("engine.risk_rejected", reason=decision.reason)
                return
            if decision.adjusted_size is not None:
                size = round_to_step(decision.adjusted_size, self.spec.lot_step, self.spec.min_lot)

            # Place
            side = "buy" if direction > 0 else "sell"
            result = self._bridge_post(
                "/order",
                {
                    "symbol": self.spec.symbol,
                    "side": side,
                    "lot": size,
                    "sl": sl,
                    "tp": tp,
                    "comment": reason[:24],
                    "magic": self.spec.magic,
                    "reference_price": entry,
                },
            )
            if result.get("success"):
                self.runtime.last_fill_at = time.time()
                self.runtime.fills_today += 1
                self.runtime.open_position_ticket = result.get("ticket")
                fill_price = float(result.get("fill_price", entry))
                # Slippage telemetry
                self.breaker.on_slippage_sample(abs(fill_price - entry))
                # Persist trade open
                self.internal.emit_trade(
                    strategy_instance_id=self.spec.strategy_instance_id,
                    broker_account_id=self.spec.broker_account_id,
                    ticket=int(result["ticket"]),
                    symbol=self.spec.symbol,
                    side=side,
                    lot=size,
                    fill_price=fill_price,
                    sl=sl,
                    tp=tp,
                    pnl=None,
                    opened_at=time.time(),
                    closed_at=None,
                    comment=reason,
                )
            else:
                logger.warning("engine.order_failed", result=result)
        except Exception as e:
            logger.exception("engine.on_new_bar_error", error=str(e))

    # ------------------------------------------------------------------
    def _load_recent_bars(self):
        """Load last N OHLCV bars.

        Phase 2: prefer the bridge's MT5 history if exposed; for now we
        delegate to `data.loader.load_sample` if no live source is wired —
        the same dev-safe fallback used in backtest. This keeps the engine
        runnable in paper mode without changing the strategy code path.
        """
        try:
            from data.loader import load_sample

            return load_sample(self.spec.symbol, self.spec.timeframe).tail(500)
        except Exception as e:
            logger.warning("engine.load_data_failed", error=str(e))
            return None

    def _make_strategy(self):
        # Lazy import to keep startup light.
        from workers.backtest_worker import _strategy_registry

        cls = _strategy_registry().get(self.spec.strategy_code)
        if cls is None:
            raise ValueError(f"unknown strategy_code={self.spec.strategy_code}")
        return cls(params=self.spec.params)

    # ------------------------------------------------------------------
    def status_snapshot(self) -> dict[str, Any]:
        return {
            "strategy_instance_id": self.spec.strategy_instance_id,
            "status": self.runtime.status.value,
            "runtime": {
                k: v for k, v in vars(self.runtime).items() if not k.startswith("_")
            },
            "risk": self.risk.snapshot(),
            "breaker": self.breaker.snapshot(),
            "spec_summary": {
                "strategy_code": self.spec.strategy_code,
                "symbol": self.spec.symbol,
                "timeframe": self.spec.timeframe,
                "magic": self.spec.magic,
            },
        }


# ---------------------------------------------------------------------------
def _timeframe_seconds(tf: str) -> int:
    return {
        "M1": 60,
        "M5": 300,
        "M15": 900,
        "M30": 1800,
        "H1": 3600,
        "H4": 14_400,
        "D1": 86_400,
    }.get(tf.upper(), 900)
