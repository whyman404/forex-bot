"""MetaTrader5 (Exness) adapter.

This module is import-safe on any platform. The `MetaTrader5` package only
runs on Windows; on Mac/Linux we raise a clear error at `connect()` time
instead of failing at import.

Production usage
----------------
- Run on a Windows VPS where MT5 terminal is installed + logged in.
- Keep `MetaTrader5.initialize(path=...)` pointing at the correct terminal
  for multi-account setups.
- Retry / reconnect logic is in `_with_retry`. We use exponential backoff.
- Every call is logged via structlog.

Symbols
-------
- Exness gold is typically `XAUUSDm` or `XAUUSD` depending on account
  type — we normalize via `data.symbols`.
"""
from __future__ import annotations

import platform
import time
from typing import Any, Callable

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

# --------------------------------------------------------------------------
# Conditional import — only attempt on Windows.
# --------------------------------------------------------------------------
_mt5: Any = None
_MT5_IMPORT_ERROR: Exception | None = None

if platform.system() == "Windows":
    try:
        import MetaTrader5 as _mt5  # type: ignore
    except Exception as e:  # pragma: no cover
        _MT5_IMPORT_ERROR = e


def _require_mt5() -> Any:
    if _mt5 is None:
        msg = (
            "MetaTrader5 is not available. "
            f"platform={platform.system()}. "
            "MT5 only runs on Windows. "
            f"Install with `uv sync --extra mt5` on a Windows VPS. "
            f"Underlying error: {_MT5_IMPORT_ERROR}"
        )
        raise RuntimeError(msg)
    return _mt5


def _with_retry(
    fn: Callable[..., Any],
    *args: Any,
    retries: int = 3,
    backoff_sec: float = 1.0,
    **kwargs: Any,
) -> Any:
    """Run an MT5 call with retry + exponential backoff."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # broad: MT5 calls can raise C-level errors
            last = e
            logger.warning(
                "mt5.retry",
                attempt=attempt + 1,
                retries=retries,
                error=str(e),
            )
            time.sleep(backoff_sec * (2**attempt))
    raise RuntimeError(f"MT5 call failed after {retries} retries: {last}")


class MT5Broker(Broker):
    """Exness / MT5 broker adapter."""

    name = "MT5"

    def __init__(
        self,
        account: int | None = None,
        password: str | None = None,
        server: str | None = None,
        terminal_path: str | None = None,
    ) -> None:
        self.account = account
        self.password = password
        self.server = server
        self.terminal_path = terminal_path
        self._connected = False
        self._tick_handlers: dict[str, OnTickFn] = {}

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        """Initialize MT5 and log in.

        Returns True on success. Raises RuntimeError on Mac/Linux or login failure.
        """
        mt5 = _require_mt5()
        kwargs: dict[str, Any] = {}
        if self.terminal_path:
            kwargs["path"] = self.terminal_path
        ok = _with_retry(mt5.initialize, **kwargs)
        if not ok:
            err = mt5.last_error()
            logger.error("mt5.initialize_failed", err=err)
            raise RuntimeError(f"MT5 initialize failed: {err}")

        if self.account and self.password and self.server:
            ok = _with_retry(
                mt5.login,
                self.account,
                password=self.password,
                server=self.server,
            )
            if not ok:
                err = mt5.last_error()
                logger.error("mt5.login_failed", err=err, account=self.account)
                raise RuntimeError(f"MT5 login failed: {err}")

        self._connected = True
        logger.info("mt5.connected", account=self.account, server=self.server)
        return True

    def disconnect(self) -> None:
        if _mt5 is not None and self._connected:
            try:
                _mt5.shutdown()
            finally:
                self._connected = False
                logger.info("mt5.disconnected")

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Account / positions
    # ------------------------------------------------------------------
    def get_account(self) -> AccountInfo:
        mt5 = _require_mt5()
        info = _with_retry(mt5.account_info)
        if info is None:
            raise RuntimeError(f"MT5 account_info failed: {mt5.last_error()}")
        return AccountInfo(
            balance=float(info.balance),
            equity=float(info.equity),
            margin=float(info.margin),
            free_margin=float(info.margin_free),
            margin_level=float(getattr(info, "margin_level", 0.0)),
            currency=str(getattr(info, "currency", "USD")),
        )

    def get_positions(self, symbol: str | None = None) -> list[Position]:
        mt5 = _require_mt5()
        raw = _with_retry(mt5.positions_get, symbol=symbol) if symbol else _with_retry(
            mt5.positions_get
        )
        if raw is None:
            return []
        out: list[Position] = []
        for p in raw:
            side = "buy" if getattr(p, "type", 0) == 0 else "sell"
            out.append(
                Position(
                    ticket=int(p.ticket),
                    symbol=str(p.symbol),
                    side=side,  # type: ignore[arg-type]
                    volume=float(p.volume),
                    entry_price=float(p.price_open),
                    sl=float(p.sl) if p.sl else None,
                    tp=float(p.tp) if p.tp else None,
                    unrealized_pnl=float(p.profit),
                    open_time=str(p.time),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def place_order(self, order: Order) -> OrderResult:
        """Place a market / limit / stop order.

        For MT5, we use `order_send` with TRADE_ACTION_DEAL (market) or
        TRADE_ACTION_PENDING (limit/stop).
        """
        mt5 = _require_mt5()

        # Map our types → MT5 constants.
        type_map = {
            ("market", "buy"): mt5.ORDER_TYPE_BUY,
            ("market", "sell"): mt5.ORDER_TYPE_SELL,
            ("limit", "buy"): mt5.ORDER_TYPE_BUY_LIMIT,
            ("limit", "sell"): mt5.ORDER_TYPE_SELL_LIMIT,
            ("stop", "buy"): mt5.ORDER_TYPE_BUY_STOP,
            ("stop", "sell"): mt5.ORDER_TYPE_SELL_STOP,
        }
        action = (
            mt5.TRADE_ACTION_DEAL
            if order.type == "market"
            else mt5.TRADE_ACTION_PENDING
        )
        request = {
            "action": action,
            "symbol": order.symbol,
            "volume": order.volume,
            "type": type_map[(order.type, order.side)],
            "deviation": 10,
            "magic": order.magic,
            "comment": order.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if order.price is not None:
            request["price"] = order.price
        if order.sl is not None:
            request["sl"] = order.sl
        if order.tp is not None:
            request["tp"] = order.tp

        result = _with_retry(mt5.order_send, request)
        if result is None:
            err = mt5.last_error()
            return OrderResult(False, error_code=err[0], error_message=str(err))
        ok = result.retcode == mt5.TRADE_RETCODE_DONE
        return OrderResult(
            success=ok,
            ticket=int(result.order) if ok else None,
            fill_price=float(result.price) if ok else None,
            error_code=None if ok else int(result.retcode),
            error_message="" if ok else str(result.comment),
            raw={"retcode": int(result.retcode)},
        )

    def close_position(
        self, ticket: str | int, volume: float | None = None
    ) -> OrderResult:
        mt5 = _require_mt5()
        positions = [p for p in self.get_positions() if int(p.ticket) == int(ticket)]
        if not positions:
            return OrderResult(False, error_message=f"position_not_found:{ticket}")
        pos = positions[0]
        opp_side = "sell" if pos.side == "buy" else "buy"
        type_const = (
            mt5.ORDER_TYPE_SELL if opp_side == "sell" else mt5.ORDER_TYPE_BUY
        )
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": volume if volume is not None else pos.volume,
            "type": type_const,
            "position": int(ticket),
            "deviation": 10,
            "magic": 0,
            "comment": "close_via_adapter",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = _with_retry(mt5.order_send, request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        return OrderResult(
            success=ok,
            ticket=int(result.order) if ok else None,
            error_code=None if ok else (int(result.retcode) if result else -1),
            error_message="" if ok else (str(result.comment) if result else "unknown"),
        )

    def cancel_order(self, ticket: str | int) -> OrderResult:
        mt5 = _require_mt5()
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(ticket),
        }
        result = _with_retry(mt5.order_send, request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        return OrderResult(
            success=ok,
            error_code=None if ok else (int(result.retcode) if result else -1),
        )

    def modify_position(
        self,
        ticket: str | int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> OrderResult:
        mt5 = _require_mt5()
        positions = [p for p in self.get_positions() if int(p.ticket) == int(ticket)]
        if not positions:
            return OrderResult(False, error_message=f"position_not_found:{ticket}")
        pos = positions[0]
        request: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": int(ticket),
            "sl": sl if sl is not None else (pos.sl or 0.0),
            "tp": tp if tp is not None else (pos.tp or 0.0),
        }
        result = _with_retry(mt5.order_send, request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        return OrderResult(
            success=ok,
            error_code=None if ok else (int(result.retcode) if result else -1),
        )

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------
    def subscribe_ticks(self, symbol: str, on_tick: OnTickFn) -> None:
        """MT5 doesn't push ticks via Python; caller must poll `symbol_info_tick`.

        We register the handler — a thin event loop (in the OMS) is expected
        to call this in its tick loop. Implementation lives there.
        """
        mt5 = _require_mt5()
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"symbol_select failed for {symbol}")
        self._tick_handlers[symbol] = on_tick
        logger.info("mt5.tick_subscribed", symbol=symbol)

    def unsubscribe_ticks(self, symbol: str) -> None:
        self._tick_handlers.pop(symbol, None)
        logger.info("mt5.tick_unsubscribed", symbol=symbol)

    # ------------------------------------------------------------------
    # OMS helper — call this from a poller.
    # ------------------------------------------------------------------
    def poll_tick(self, symbol: str) -> tuple[float, float] | None:
        """Pull a single tick and fire the handler. Returns (bid, ask) or None."""
        mt5 = _require_mt5()
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            return None
        handler = self._tick_handlers.get(symbol)
        if handler:
            handler(symbol, float(t.bid), float(t.ask))
        return float(t.bid), float(t.ask)
