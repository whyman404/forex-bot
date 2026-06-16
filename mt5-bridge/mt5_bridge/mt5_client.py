"""Thin wrapper around `MetaTrader5` with reconnect + structured logging.

Why a separate client?
- `MetaTrader5` is module-level (the package mutates global state).
- The Windows process owns one MT5 terminal; we want a clean async-safe
  facade on top.
- Easier to mock in tests (we never import the real package off-Windows).

The client does NOT enforce policy — that's `safety.py` and the engine
side. Here we only handle the MT5 quirks: retries, error decoding, and
shape conversion.
"""
from __future__ import annotations

import platform
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


# --------------------------------------------------------------------------
# Conditional import — on Mac/Linux the bridge fails loudly at start,
# but unit tests can still import this module.
# --------------------------------------------------------------------------
_mt5: Any = None
_IMPORT_ERROR: Exception | None = None


def _try_import_mt5() -> None:
    global _mt5, _IMPORT_ERROR
    if _mt5 is not None or _IMPORT_ERROR is not None:
        return
    if platform.system() != "Windows":
        _IMPORT_ERROR = RuntimeError(
            f"MetaTrader5 only runs on Windows; platform={platform.system()}"
        )
        return
    try:
        import MetaTrader5 as mt5  # type: ignore

        _mt5 = mt5
    except Exception as e:  # pragma: no cover
        _IMPORT_ERROR = e


def require_mt5() -> Any:
    """Return the MetaTrader5 module or raise a friendly error."""
    _try_import_mt5()
    if _mt5 is None:
        raise RuntimeError(
            "MetaTrader5 package is unavailable. "
            f"Underlying error: {_IMPORT_ERROR}. "
            "Install on a Windows machine with: pip install MetaTrader5."
        )
    return _mt5


# --------------------------------------------------------------------------
# Retry helper — exponential backoff
# --------------------------------------------------------------------------
def with_retry(fn: Callable[..., Any], *args: Any, retries: int = 3, base: float = 0.5, **kwargs: Any) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # MT5 raises C-level errors as Python exceptions
            last = e
            logger.warning("mt5.retry", attempt=attempt + 1, error=str(e))
            time.sleep(base * (2**attempt))
    raise RuntimeError(f"MT5 call failed after {retries} retries: {last}")


# --------------------------------------------------------------------------
# Lightweight DTOs (separate from broker.base — bridge has no engine deps)
# --------------------------------------------------------------------------
@dataclass
class AccountSnapshot:
    login: int
    server: str
    balance: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float
    currency: str
    leverage: int


@dataclass
class TickSnapshot:
    symbol: str
    bid: float
    ask: float
    time: float  # unix epoch seconds (from MT5)


@dataclass
class PositionSnapshot:
    ticket: int
    symbol: str
    side: str  # buy | sell
    volume: float
    entry_price: float
    sl: float | None
    tp: float | None
    profit: float
    open_time: float
    magic: int
    comment: str


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------
class MT5Client:
    """Owns a single MT5 terminal session. Thread-safe via a coarse lock."""

    def __init__(self, mt5_path: str | None = None) -> None:
        self.mt5_path = mt5_path
        self._lock = threading.RLock()
        self._connected = False
        self._account_login: int | None = None
        self._server: str | None = None
        self.last_tick_at: float = 0.0
        self.last_order_at: float = 0.0

    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def account_login(self) -> int | None:
        return self._account_login

    @property
    def server(self) -> str | None:
        return self._server

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self, server: str, login: int, password: str) -> AccountSnapshot:
        mt5 = require_mt5()
        with self._lock:
            init_kwargs: dict[str, Any] = {}
            if self.mt5_path:
                init_kwargs["path"] = self.mt5_path
            ok = with_retry(mt5.initialize, **init_kwargs)
            if not ok:
                err = mt5.last_error()
                raise RuntimeError(f"mt5.initialize failed: {err}")
            ok = with_retry(mt5.login, login, password=password, server=server)
            if not ok:
                err = mt5.last_error()
                # Don't leak the password in the error message — MT5 doesn't
                # echo it, but be defensive in case future versions do.
                raise RuntimeError(f"mt5.login failed: {err}")
            self._connected = True
            self._account_login = login
            self._server = server
            logger.info("mt5.connected", login=login, server=server)
            return self.account_info()

    def disconnect(self) -> None:
        with self._lock:
            if not self._connected:
                return
            try:
                require_mt5().shutdown()
            finally:
                self._connected = False
                self._account_login = None
                self._server = None
                logger.info("mt5.disconnected")

    # ------------------------------------------------------------------
    # Account / market data
    # ------------------------------------------------------------------
    def account_info(self) -> AccountSnapshot:
        mt5 = require_mt5()
        info = with_retry(mt5.account_info)
        if info is None:
            raise RuntimeError(f"mt5.account_info failed: {mt5.last_error()}")
        return AccountSnapshot(
            login=int(info.login),
            server=str(getattr(info, "server", self._server or "")),
            balance=float(info.balance),
            equity=float(info.equity),
            margin=float(info.margin),
            margin_free=float(info.margin_free),
            margin_level=float(getattr(info, "margin_level", 0.0)),
            currency=str(getattr(info, "currency", "USD")),
            leverage=int(getattr(info, "leverage", 0)),
        )

    def symbols(self) -> list[str]:
        mt5 = require_mt5()
        syms = with_retry(mt5.symbols_get)
        return [str(s.name) for s in (syms or [])]

    def tick(self, symbol: str) -> TickSnapshot | None:
        mt5 = require_mt5()
        if not mt5.symbol_select(symbol, True):
            return None
        t = with_retry(mt5.symbol_info_tick, symbol)
        if t is None:
            return None
        self.last_tick_at = time.time()
        return TickSnapshot(
            symbol=symbol,
            bid=float(t.bid),
            ask=float(t.ask),
            time=float(getattr(t, "time", time.time())),
        )

    def positions(self, symbol: str | None = None) -> list[PositionSnapshot]:
        mt5 = require_mt5()
        raw = (
            with_retry(mt5.positions_get, symbol=symbol)
            if symbol
            else with_retry(mt5.positions_get)
        )
        if raw is None:
            return []
        out: list[PositionSnapshot] = []
        for p in raw:
            side = "buy" if getattr(p, "type", 0) == 0 else "sell"
            out.append(
                PositionSnapshot(
                    ticket=int(p.ticket),
                    symbol=str(p.symbol),
                    side=side,
                    volume=float(p.volume),
                    entry_price=float(p.price_open),
                    sl=float(p.sl) if p.sl else None,
                    tp=float(p.tp) if p.tp else None,
                    profit=float(p.profit),
                    open_time=float(p.time),
                    magic=int(getattr(p, "magic", 0)),
                    comment=str(getattr(p, "comment", "")),
                )
            )
        return out

    def history_deals(self, start: float, end: float) -> list[dict[str, Any]]:
        mt5 = require_mt5()
        from datetime import datetime, timezone

        d_from = datetime.fromtimestamp(start, tz=timezone.utc)
        d_to = datetime.fromtimestamp(end, tz=timezone.utc)
        deals = with_retry(mt5.history_deals_get, d_from, d_to)
        if deals is None:
            return []
        return [
            {
                "ticket": int(d.ticket),
                "order": int(d.order),
                "time": float(d.time),
                "symbol": str(d.symbol),
                "type": int(d.type),
                "volume": float(d.volume),
                "price": float(d.price),
                "profit": float(d.profit),
                "magic": int(getattr(d, "magic", 0)),
                "comment": str(getattr(d, "comment", "")),
            }
            for d in deals
        ]

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def place_market(
        self,
        symbol: str,
        side: str,
        lot: float,
        sl: float | None,
        tp: float | None,
        comment: str,
        magic: int,
        deviation: int = 10,
    ) -> dict[str, Any]:
        mt5 = require_mt5()
        with self._lock:
            mt5.symbol_select(symbol, True)
            order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
            tick = self.tick(symbol)
            if tick is None:
                raise RuntimeError(f"no tick for {symbol}")
            price = tick.ask if side == "buy" else tick.bid
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(lot),
                "type": order_type,
                "price": price,
                "deviation": deviation,
                "magic": int(magic),
                "comment": comment[:31],  # MT5 truncates anyway; be polite
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            if sl is not None and sl > 0:
                request["sl"] = float(sl)
            if tp is not None and tp > 0:
                request["tp"] = float(tp)
            result = with_retry(mt5.order_send, request)
            self.last_order_at = time.time()
            if result is None:
                err = mt5.last_error()
                return {
                    "success": False,
                    "retcode": err[0] if err else -1,
                    "comment": str(err),
                }
            ok = result.retcode == mt5.TRADE_RETCODE_DONE
            return {
                "success": ok,
                "ticket": int(result.order) if ok else None,
                "fill_price": float(result.price) if ok else None,
                "volume": float(result.volume) if ok else None,
                "retcode": int(result.retcode),
                "comment": str(result.comment),
                "request_price": price,
            }

    def place_pending(
        self,
        symbol: str,
        side: str,
        order_kind: str,  # "limit" | "stop"
        lot: float,
        price: float,
        sl: float | None,
        tp: float | None,
        comment: str,
        magic: int,
    ) -> dict[str, Any]:
        mt5 = require_mt5()
        with self._lock:
            mt5.symbol_select(symbol, True)
            type_map = {
                ("limit", "buy"): mt5.ORDER_TYPE_BUY_LIMIT,
                ("limit", "sell"): mt5.ORDER_TYPE_SELL_LIMIT,
                ("stop", "buy"): mt5.ORDER_TYPE_BUY_STOP,
                ("stop", "sell"): mt5.ORDER_TYPE_SELL_STOP,
            }
            try:
                order_type = type_map[(order_kind, side)]
            except KeyError:
                raise ValueError(
                    f"invalid pending combo: kind={order_kind} side={side}"
                )
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": float(lot),
                "type": order_type,
                "price": float(price),
                "magic": int(magic),
                "comment": comment[:31],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            if sl is not None and sl > 0:
                request["sl"] = float(sl)
            if tp is not None and tp > 0:
                request["tp"] = float(tp)
            result = with_retry(mt5.order_send, request)
            self.last_order_at = time.time()
            if result is None:
                return {"success": False, "comment": "no result"}
            ok = result.retcode == mt5.TRADE_RETCODE_DONE
            return {
                "success": ok,
                "ticket": int(result.order) if ok else None,
                "retcode": int(result.retcode),
                "comment": str(result.comment),
            }

    def close_position(self, ticket: int) -> dict[str, Any]:
        mt5 = require_mt5()
        with self._lock:
            positions = [p for p in self.positions() if p.ticket == ticket]
            if not positions:
                return {"success": False, "comment": f"position_not_found:{ticket}"}
            pos = positions[0]
            tick = self.tick(pos.symbol)
            if tick is None:
                return {"success": False, "comment": "no tick"}
            opp_type = (
                mt5.ORDER_TYPE_SELL if pos.side == "buy" else mt5.ORDER_TYPE_BUY
            )
            price = tick.bid if pos.side == "buy" else tick.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": opp_type,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": pos.magic,
                "comment": "close_via_bridge",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = with_retry(mt5.order_send, request)
            ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
            return {
                "success": ok,
                "ticket": int(result.order) if ok else None,
                "fill_price": float(result.price) if ok else None,
                "comment": str(result.comment) if result else "no result",
            }

    def modify_position(
        self,
        ticket: int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> dict[str, Any]:
        mt5 = require_mt5()
        with self._lock:
            positions = [p for p in self.positions() if p.ticket == ticket]
            if not positions:
                return {"success": False, "comment": f"position_not_found:{ticket}"}
            pos = positions[0]
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": ticket,
                "sl": float(sl) if sl is not None else (pos.sl or 0.0),
                "tp": float(tp) if tp is not None else (pos.tp or 0.0),
            }
            result = with_retry(mt5.order_send, request)
            ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
            return {"success": ok, "comment": str(result.comment) if result else "no result"}
