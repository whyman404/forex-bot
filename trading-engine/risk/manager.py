"""Risk manager — gatekeeper for every order.

Responsibilities
----------------
1. Cap per-trade risk (default 2%; 1% recommended).
2. Daily loss limit — once hit, block new entries for the rest of the UTC day.
3. Portfolio max drawdown circuit breaker — once hit, KILL all strategies.
4. Max open positions / max exposure per symbol.
5. Sketched correlation check — refuse to add highly correlated symbol if
   we already have exposure.

Every Strategy → Broker call must go through `RiskManager.evaluate()`.
The manager is intentionally conservative — it would rather pass on a good
trade than blow up the account.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RiskLimits:
    """Account-level hard limits."""

    max_risk_per_trade_pct: float = 2.0
    max_daily_loss_pct: float = 5.0
    max_drawdown_pct: float = 15.0  # circuit breaker — disable bot
    max_open_positions: int = 6
    max_positions_per_symbol: int = 1
    correlated_symbol_limit: int = 2  # max simultaneous in correlated bucket


@dataclass
class RiskState:
    """Live state the manager tracks."""

    equity: float = 10_000.0
    peak_equity: float = 10_000.0
    realized_pnl_today: float = 0.0
    today_utc: dt.date = field(default_factory=lambda: dt.datetime.utcnow().date())
    open_positions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    bot_disabled: bool = False
    disabled_reason: str = ""


@dataclass
class RiskDecision:
    """Outcome of evaluating a proposed order."""

    approved: bool
    reason: str
    adjusted_size: float | None = None  # if we trimmed size to honor risk cap

    @property
    def status(self) -> Literal["approved", "rejected", "trimmed"]:
        if not self.approved:
            return "rejected"
        return "trimmed" if self.adjusted_size is not None else "approved"


# Correlation buckets — symbols inside a bucket are treated as 1 exposure.
_CORRELATION_BUCKETS: dict[str, set[str]] = {
    "gold_block": {"XAUUSD", "XAGUSD"},
    "btc_block": {"BTCUSDT", "BTCUSD"},
}


def _bucket_of(symbol: str) -> str | None:
    for k, syms in _CORRELATION_BUCKETS.items():
        if symbol.upper() in syms:
            return k
    return None


class RiskManager:
    """Stateful manager. One instance per account / per running bot."""

    def __init__(self, limits: RiskLimits | None = None, initial_equity: float = 10_000.0):
        self.limits = limits or RiskLimits()
        self.state = RiskState(equity=initial_equity, peak_equity=initial_equity)

    # ------------------------------------------------------------------
    # State updates — call these from the broker / OMS
    # ------------------------------------------------------------------
    def on_equity_update(self, equity: float) -> None:
        """Call on every equity tick. Triggers max-DD circuit breaker."""
        self.state.equity = equity
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        dd_pct = (1 - equity / self.state.peak_equity) * 100
        if dd_pct >= self.limits.max_drawdown_pct and not self.state.bot_disabled:
            self.state.bot_disabled = True
            self.state.disabled_reason = (
                f"max_drawdown_circuit_breaker: dd={dd_pct:.2f}% "
                f">= limit={self.limits.max_drawdown_pct}%"
            )
            logger.error("risk.circuit_breaker", reason=self.state.disabled_reason)

    def on_trade_closed(self, pnl: float) -> None:
        """Update realized daily PnL."""
        self._roll_day_if_needed()
        self.state.realized_pnl_today += pnl

    def on_position_opened(self, symbol: str, info: dict[str, Any]) -> None:
        self.state.open_positions.setdefault(symbol, []).append(info)

    def on_position_closed(self, symbol: str, ticket: str | int | None = None) -> None:
        positions = self.state.open_positions.get(symbol, [])
        if ticket is None:
            positions.clear()
        else:
            self.state.open_positions[symbol] = [
                p for p in positions if p.get("ticket") != ticket
            ]

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate(
        self,
        symbol: str,
        proposed_size: float,
        proposed_risk_amount: float,
    ) -> RiskDecision:
        """Decide whether to approve a new order.

        Args:
            symbol: e.g. 'XAUUSD'.
            proposed_size: position size in broker units (lots/contracts).
            proposed_risk_amount: dollar amount at risk if SL hits.
        """
        self._roll_day_if_needed()

        if self.state.bot_disabled:
            return RiskDecision(False, f"bot_disabled:{self.state.disabled_reason}")

        # 1) Daily loss limit (use realized PnL as proxy).
        loss_cap = self.state.equity * (self.limits.max_daily_loss_pct / 100)
        if -self.state.realized_pnl_today >= loss_cap:
            return RiskDecision(False, "daily_loss_limit_hit")

        # 2) Per-trade risk cap.
        per_trade_cap = self.state.equity * (self.limits.max_risk_per_trade_pct / 100)
        if proposed_risk_amount > per_trade_cap:
            # Trim instead of reject.
            scale = per_trade_cap / proposed_risk_amount
            return RiskDecision(
                approved=True,
                reason="trimmed_to_per_trade_cap",
                adjusted_size=proposed_size * scale,
            )

        # 3) Max open positions.
        total_positions = sum(len(v) for v in self.state.open_positions.values())
        if total_positions >= self.limits.max_open_positions:
            return RiskDecision(False, "max_open_positions_reached")

        # 4) Per-symbol cap.
        if (
            len(self.state.open_positions.get(symbol, []))
            >= self.limits.max_positions_per_symbol
        ):
            return RiskDecision(False, f"per_symbol_cap_reached:{symbol}")

        # 5) Correlation cap.
        bucket = _bucket_of(symbol)
        if bucket:
            in_bucket = sum(
                len(self.state.open_positions.get(s, []))
                for s in _CORRELATION_BUCKETS[bucket]
            )
            if in_bucket >= self.limits.correlated_symbol_limit:
                return RiskDecision(
                    False, f"correlation_cap_reached:bucket={bucket}"
                )

        return RiskDecision(True, "approved")

    # ------------------------------------------------------------------
    def _roll_day_if_needed(self) -> None:
        today = dt.datetime.utcnow().date()
        if today != self.state.today_utc:
            logger.info(
                "risk.daily_roll",
                old=str(self.state.today_utc),
                new=str(today),
                realized_yday=self.state.realized_pnl_today,
            )
            self.state.today_utc = today
            self.state.realized_pnl_today = 0.0

    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot dict suitable for monitoring."""
        return {
            "equity": self.state.equity,
            "peak_equity": self.state.peak_equity,
            "drawdown_pct": round(
                (1 - self.state.equity / self.state.peak_equity) * 100, 4
            ),
            "realized_pnl_today": self.state.realized_pnl_today,
            "open_positions": {
                k: len(v) for k, v in self.state.open_positions.items()
            },
            "bot_disabled": self.state.bot_disabled,
            "disabled_reason": self.state.disabled_reason,
            "limits": vars(self.limits),
        }
