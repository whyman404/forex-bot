"""Broker abstraction — a uniform API for MT5, Binance, and paper.

The Order Management System talks ONLY to Broker — never to MT5 directly.
This means we can swap MT5 ↔ Binance ↔ Paper without touching strategy code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


@dataclass
class Order:
    """A proposed order, pre-validation."""

    symbol: str
    side: Literal["buy", "sell"]
    volume: float  # lots / contracts
    type: Literal["market", "limit", "stop"] = "market"
    price: float | None = None  # required for limit/stop
    sl: float | None = None
    tp: float | None = None
    comment: str = ""
    magic: int = 0  # MT5 EA magic number; used to tag strategy ownership
    client_order_id: str = ""


@dataclass
class OrderResult:
    """The outcome of a `place_order` call."""

    success: bool
    ticket: str | int | None = None
    fill_price: float | None = None
    error_code: int | None = None
    error_message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    """An open position as reported by the broker."""

    ticket: str | int
    symbol: str
    side: Literal["buy", "sell"]
    volume: float
    entry_price: float
    sl: float | None
    tp: float | None
    unrealized_pnl: float
    open_time: str  # ISO 8601


@dataclass
class AccountInfo:
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    currency: str = "USD"


# A callback invoked on each tick from the broker's stream.
OnTickFn = Callable[[str, float, float], None]  # (symbol, bid, ask)


class Broker(ABC):
    """Abstract broker interface. Subclasses: MT5Broker, BinanceBroker, PaperBroker."""

    name: str = "AbstractBroker"

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    @abstractmethod
    def connect(self) -> bool:
        """Open connection / log in. Return True on success."""

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    # ------------------------------------------------------------------
    # Account / positions
    # ------------------------------------------------------------------
    @abstractmethod
    def get_account(self) -> AccountInfo: ...

    @abstractmethod
    def get_positions(self, symbol: str | None = None) -> list[Position]: ...

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    @abstractmethod
    def place_order(self, order: Order) -> OrderResult: ...

    @abstractmethod
    def close_position(
        self, ticket: str | int, volume: float | None = None
    ) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, ticket: str | int) -> OrderResult: ...

    @abstractmethod
    def modify_position(
        self,
        ticket: str | int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> OrderResult: ...

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    @abstractmethod
    def subscribe_ticks(self, symbol: str, on_tick: OnTickFn) -> None: ...

    @abstractmethod
    def unsubscribe_ticks(self, symbol: str) -> None: ...

    # ------------------------------------------------------------------
    # Useful default
    # ------------------------------------------------------------------
    def close_all(self) -> list[OrderResult]:
        """Close every open position. Used by kill switch."""
        results: list[OrderResult] = []
        for pos in self.get_positions():
            results.append(self.close_position(pos.ticket))
        return results
