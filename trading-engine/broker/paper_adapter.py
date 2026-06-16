"""Paper trading broker.

A drop-in `Broker` implementation that simulates fills on top of a stream
of market quotes. Used for:
  - End-to-end test of the OMS without touching real money.
  - Pre-launch dry runs with live market data.

Slippage model
--------------
- Market orders fill at `mid ± half_spread ± slippage`.
- Limit/Stop orders fill when the trigger is crossed by `low`/`high`.

This is intentionally a simple, transparent simulator — not a substitute for
real execution. Always run live with micro lots first.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from broker.base import (
    AccountInfo,
    Broker,
    OnTickFn,
    Order,
    OrderResult,
    Position,
)

logger = structlog.get_logger(__name__)


@dataclass
class _OpenPos:
    ticket: int
    symbol: str
    side: str
    volume: float
    entry_price: float
    sl: float | None
    tp: float | None
    open_time: float
    unrealized: float = 0.0


@dataclass
class _PendingOrder:
    ticket: int
    order: Order


@dataclass
class _Account:
    balance: float
    equity: float
    realized_pnl: float = 0.0


class PaperBroker(Broker):
    """In-memory simulated broker."""

    name = "PAPER"

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        slippage_pips: float = 0.5,
        spread_pips: float = 2.0,
        pip_size: dict[str, float] | None = None,
    ) -> None:
        self._account = _Account(
            balance=initial_balance, equity=initial_balance
        )
        self._slippage_pips = slippage_pips
        self._spread_pips = spread_pips
        self._pip_size = pip_size or {"XAUUSD": 0.1, "BTCUSDT": 1.0}
        self._open: dict[int, _OpenPos] = {}
        self._pending: dict[int, _PendingOrder] = {}
        self._ticker = itertools.count(start=1)
        self._tick_handlers: dict[str, OnTickFn] = {}
        self._connected = False
        self._last_quote: dict[str, tuple[float, float]] = {}

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        self._connected = True
        logger.info("paper.connected", balance=self._account.balance)
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------
    def get_account(self) -> AccountInfo:
        equity = self._account.balance + sum(p.unrealized for p in self._open.values())
        self._account.equity = equity
        return AccountInfo(
            balance=self._account.balance,
            equity=equity,
            margin=0.0,
            free_margin=equity,
            margin_level=0.0 if equity == 0 else 999.0,
        )

    def get_positions(self, symbol: str | None = None) -> list[Position]:
        out: list[Position] = []
        for p in self._open.values():
            if symbol and p.symbol != symbol:
                continue
            out.append(
                Position(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    side=p.side,  # type: ignore[arg-type]
                    volume=p.volume,
                    entry_price=p.entry_price,
                    sl=p.sl,
                    tp=p.tp,
                    unrealized_pnl=p.unrealized,
                    open_time=str(p.open_time),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def _pip(self, symbol: str) -> float:
        return self._pip_size.get(symbol, 0.0001)

    def _apply_costs(self, symbol: str, side: str, price: float) -> float:
        pip = self._pip(symbol)
        spread = self._spread_pips * pip / 2
        slip = self._slippage_pips * pip
        if side == "buy":
            return price + spread + slip
        return price - spread - slip

    def place_order(self, order: Order) -> OrderResult:
        ticket = next(self._ticker)
        if order.type == "market":
            bid, ask = self._last_quote.get(order.symbol, (order.price or 0, order.price or 0))
            base = ask if order.side == "buy" else bid
            if base <= 0:
                return OrderResult(False, error_message="no_quote_for_symbol")
            fill = self._apply_costs(order.symbol, order.side, base)
            self._open[ticket] = _OpenPos(
                ticket=ticket,
                symbol=order.symbol,
                side=order.side,
                volume=order.volume,
                entry_price=fill,
                sl=order.sl,
                tp=order.tp,
                open_time=time.time(),
            )
            return OrderResult(True, ticket=ticket, fill_price=fill)
        # Pending — sits until a tick triggers it.
        self._pending[ticket] = _PendingOrder(ticket=ticket, order=order)
        return OrderResult(True, ticket=ticket)

    def close_position(
        self, ticket: str | int, volume: float | None = None
    ) -> OrderResult:
        ticket = int(ticket)
        pos = self._open.get(ticket)
        if pos is None:
            return OrderResult(False, error_message=f"position_not_found:{ticket}")
        bid, ask = self._last_quote.get(pos.symbol, (pos.entry_price, pos.entry_price))
        exit_base = bid if pos.side == "buy" else ask
        exit_price = self._apply_costs(
            pos.symbol, "sell" if pos.side == "buy" else "buy", exit_base
        )
        pnl = (exit_price - pos.entry_price) * (1 if pos.side == "buy" else -1) * pos.volume
        self._account.balance += pnl
        self._account.realized_pnl += pnl
        del self._open[ticket]
        return OrderResult(True, ticket=ticket, fill_price=exit_price)

    def cancel_order(self, ticket: str | int) -> OrderResult:
        ticket = int(ticket)
        if ticket in self._pending:
            del self._pending[ticket]
            return OrderResult(True, ticket=ticket)
        return OrderResult(False, error_message="order_not_found")

    def modify_position(
        self,
        ticket: str | int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> OrderResult:
        ticket = int(ticket)
        pos = self._open.get(ticket)
        if pos is None:
            return OrderResult(False, error_message="position_not_found")
        if sl is not None:
            pos.sl = sl
        if tp is not None:
            pos.tp = tp
        return OrderResult(True, ticket=ticket)

    # ------------------------------------------------------------------
    # Ticks
    # ------------------------------------------------------------------
    def subscribe_ticks(self, symbol: str, on_tick: OnTickFn) -> None:
        self._tick_handlers[symbol] = on_tick

    def unsubscribe_ticks(self, symbol: str) -> None:
        self._tick_handlers.pop(symbol, None)

    def on_quote(self, symbol: str, bid: float, ask: float) -> None:
        """Feed a market quote — fires SL/TP/pending triggers and updates equity."""
        self._last_quote[symbol] = (bid, ask)
        mid = (bid + ask) / 2

        # Update unrealized & check SL/TP for open positions.
        closed_now: list[int] = []
        for ticket, pos in list(self._open.items()):
            if pos.symbol != symbol:
                continue
            if pos.side == "buy":
                pos.unrealized = (bid - pos.entry_price) * pos.volume
                if pos.sl is not None and bid <= pos.sl:
                    closed_now.append(ticket)
                elif pos.tp is not None and ask >= pos.tp:
                    closed_now.append(ticket)
            else:
                pos.unrealized = (pos.entry_price - ask) * pos.volume
                if pos.sl is not None and ask >= pos.sl:
                    closed_now.append(ticket)
                elif pos.tp is not None and bid <= pos.tp:
                    closed_now.append(ticket)
        for t in closed_now:
            self.close_position(t)

        # Trigger pending orders.
        for ticket, pend in list(self._pending.items()):
            o = pend.order
            if o.symbol != symbol:
                continue
            price = o.price or mid
            trig = False
            if o.type == "limit":
                trig = (o.side == "buy" and ask <= price) or (
                    o.side == "sell" and bid >= price
                )
            elif o.type == "stop":
                trig = (o.side == "buy" and ask >= price) or (
                    o.side == "sell" and bid <= price
                )
            if trig:
                self._open[ticket] = _OpenPos(
                    ticket=ticket,
                    symbol=o.symbol,
                    side=o.side,
                    volume=o.volume,
                    entry_price=self._apply_costs(o.symbol, o.side, price),
                    sl=o.sl,
                    tp=o.tp,
                    open_time=time.time(),
                )
                del self._pending[ticket]

        # Notify handler.
        handler = self._tick_handlers.get(symbol)
        if handler:
            handler(symbol, bid, ask)
