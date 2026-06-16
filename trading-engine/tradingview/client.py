"""TradingView analysis client.

Wraps `tradingview-ta` (PyPI) with:
- retry (3 attempts, exponential backoff via tenacity)
- TTL cache (60s default — TV's bar data updates at most every minute)
- concurrency throttle (max 4 concurrent calls, 0.8s spacing)
  — mirrors upstream PR #34 in atilaahmettaner/tradingview-mcp
- graceful disable when the library is unavailable (TV_ENABLED=false)

The client is INTENTIONALLY synchronous. Our LiveEngine runs each
strategy in its own thread already, and TV's TA_Handler is sync-only.
Adding an async wrapper would only add complexity without throughput
gain at our scale.

Performance budget
------------------
At 4 strategies × 4 timeframes × 1 call/bar-close = 16 calls/minute peak.
TV's informal rate limit (per IP) is ~300 req/min, so we're well under.
The throttle is defensive against bursts (e.g. all 4 strategies wake at
the same bar boundary).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Library availability
# ---------------------------------------------------------------------------
_TV_IMPORT_ERROR: str | None = None
try:
    # `tradingview-ta` is the PyPI dist; module path is `tradingview_ta`.
    from tradingview_ta import TA_Handler, Interval  # type: ignore

    _TV_LIB_AVAILABLE = True
except Exception as e:  # pragma: no cover — depends on install env
    _TV_LIB_AVAILABLE = False
    _TV_IMPORT_ERROR = str(e)
    TA_Handler = None  # type: ignore[assignment]
    Interval = None  # type: ignore[assignment]


def tv_enabled() -> bool:
    """Return True if TV integration is both installed AND env-enabled.

    Env `TV_ENABLED=false` (or any non-truthy) forces the integration off
    even when the library is installed — useful for paranoid prod rollouts.
    """
    if not _TV_LIB_AVAILABLE:
        return False
    flag = os.getenv("TV_ENABLED", "true").strip().lower()
    return flag in ("1", "true", "yes", "on")


def tv_unavailable_reason() -> str:
    if not _TV_LIB_AVAILABLE:
        return f"library_not_installed: {_TV_IMPORT_ERROR or 'unknown'}"
    if not tv_enabled():
        return "disabled_by_env_TV_ENABLED"
    return ""


# ---------------------------------------------------------------------------
# Interval mapping (our timeframe ↔ TV Interval)
# ---------------------------------------------------------------------------
def _interval(name: str):
    """Map our string '15m'/'1h'/etc to a TV `Interval` constant.

    Accepts both lowercase 'm/h/d' and our internal 'M15/H1/D1' shorthand.
    """
    if Interval is None:  # library missing
        return None
    n = name.strip().upper()
    table = {
        "1M": Interval.INTERVAL_1_MINUTE,
        "5M": Interval.INTERVAL_5_MINUTES,
        "15M": Interval.INTERVAL_15_MINUTES,
        "30M": Interval.INTERVAL_30_MINUTES,
        "1H": Interval.INTERVAL_1_HOUR,
        "2H": Interval.INTERVAL_2_HOURS,
        "4H": Interval.INTERVAL_4_HOURS,
        "1D": Interval.INTERVAL_1_DAY,
        "1W": Interval.INTERVAL_1_WEEK,
        # internal shorthand
        "M1": Interval.INTERVAL_1_MINUTE,
        "M5": Interval.INTERVAL_5_MINUTES,
        "M15": Interval.INTERVAL_15_MINUTES,
        "M30": Interval.INTERVAL_30_MINUTES,
        "H1": Interval.INTERVAL_1_HOUR,
        "H2": Interval.INTERVAL_2_HOURS,
        "H4": Interval.INTERVAL_4_HOURS,
        "D1": Interval.INTERVAL_1_DAY,
        "W1": Interval.INTERVAL_1_WEEK,
    }
    return table.get(n, Interval.INTERVAL_15_MINUTES)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------
@dataclass
class TVAnalysis:
    """One snapshot of a single (symbol, exchange, interval) call."""

    symbol: str
    exchange: str
    interval: str
    recommendation: str       # STRONG_BUY | BUY | NEUTRAL | SELL | STRONG_SELL
    buy_signals: int
    sell_signals: int
    neutral_signals: int
    price: float | None = None
    fetched_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval,
            "recommendation": self.recommendation,
            "buy_signals": self.buy_signals,
            "sell_signals": self.sell_signals,
            "neutral_signals": self.neutral_signals,
            "price": self.price,
            "fetched_at": self.fetched_at,
        }


# ---------------------------------------------------------------------------
# Throttle + cache
# ---------------------------------------------------------------------------
class _Throttle:
    """Concurrency + spacing throttle, shared across all callers."""

    def __init__(self, max_concurrent: int, min_spacing_sec: float) -> None:
        self._sem = threading.BoundedSemaphore(max_concurrent)
        self._spacing = min_spacing_sec
        self._lock = threading.Lock()
        self._last_call_at = 0.0

    def acquire(self) -> None:
        self._sem.acquire()
        with self._lock:
            wait = (self._last_call_at + self._spacing) - time.monotonic()
            if wait > 0:
                # Hold the lock so concurrent callers serialize on spacing too.
                time.sleep(wait)
            self._last_call_at = time.monotonic()

    def release(self) -> None:
        self._sem.release()


class _TTLCache:
    """Tiny TTL cache keyed by (symbol, exchange, interval)."""

    def __init__(self, ttl_sec: float) -> None:
        self.ttl = ttl_sec
        self._store: dict[tuple[str, str, str], tuple[float, TVAnalysis]] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple[str, str, str]) -> TVAnalysis | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.time() - ts > self.ttl:
                self._store.pop(key, None)
                return None
            return value

    def put(self, key: tuple[str, str, str], value: TVAnalysis) -> None:
        with self._lock:
            self._store[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class TVDisabledError(RuntimeError):
    """Raised when the TV library is not installed or disabled by env."""


class TVClient:
    """Thread-safe TradingView analysis client.

    One instance per process is sufficient — all caches + throttles are
    module-shared so multiple clients don't double-up rate limits.
    """

    # Shared throttle + cache (one per process, configured at first import).
    _throttle: _Throttle | None = None
    _cache: _TTLCache | None = None
    _shared_lock = threading.Lock()

    def __init__(
        self,
        *,
        max_concurrent: int | None = None,
        min_spacing_sec: float | None = None,
        cache_ttl_sec: float | None = None,
        max_retries: int = 3,
    ) -> None:
        self.max_retries = max_retries
        with TVClient._shared_lock:
            if TVClient._throttle is None:
                TVClient._throttle = _Throttle(
                    max_concurrent=max_concurrent
                    or int(os.getenv("TV_THROTTLE_CONCURRENT", "4")),
                    min_spacing_sec=min_spacing_sec
                    or float(os.getenv("TV_THROTTLE_SPACING_SEC", "0.8")),
                )
            if TVClient._cache is None:
                TVClient._cache = _TTLCache(
                    ttl_sec=cache_ttl_sec
                    or float(os.getenv("TV_CACHE_TTL_SEC", "60")),
                )

    # ------------------------------------------------------------------
    # Single-call analysis
    # ------------------------------------------------------------------
    def get_analysis(
        self,
        symbol: str,
        exchange: str,
        interval: str = "15m",
        *,
        screener: str = "forex",
    ) -> TVAnalysis:
        """Fetch one analysis snapshot (with retry, throttle, and cache).

        Raises TVDisabledError if the integration is off — callers
        should catch this and degrade gracefully (e.g. emit no signal).
        """
        if not tv_enabled():
            raise TVDisabledError(tv_unavailable_reason())

        key = (symbol.upper(), exchange.upper(), interval.lower())
        cached = TVClient._cache.get(key) if TVClient._cache else None
        if cached is not None:
            return cached

        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                analysis = self._fetch(symbol, exchange, interval, screener=screener)
                if TVClient._cache is not None:
                    TVClient._cache.put(key, analysis)
                return analysis
            except Exception as e:  # network/parse/transient
                last_err = e
                backoff = 0.5 * (2 ** (attempt - 1))  # 0.5, 1.0, 2.0
                logger.warning(
                    "tv.get_analysis.retry attempt=%d/%d sym=%s err=%s backoff=%.1fs",
                    attempt,
                    self.max_retries,
                    symbol,
                    str(e)[:200],
                    backoff,
                )
                time.sleep(backoff)
        # All retries exhausted.
        raise RuntimeError(
            f"tv.get_analysis failed after {self.max_retries} attempts: {last_err}"
        )

    def _fetch(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        *,
        screener: str,
    ) -> TVAnalysis:
        """Single TV call — throttle-bracketed."""
        assert TVClient._throttle is not None
        TVClient._throttle.acquire()
        try:
            handler = TA_Handler(  # type: ignore[misc]
                symbol=symbol,
                screener=screener,
                exchange=exchange,
                interval=_interval(interval),
            )
            raw = handler.get_analysis()
            summary = raw.summary or {}
            indicators = raw.indicators or {}
            return TVAnalysis(
                symbol=symbol.upper(),
                exchange=exchange.upper(),
                interval=interval.lower(),
                recommendation=str(summary.get("RECOMMENDATION", "NEUTRAL")),
                buy_signals=int(summary.get("BUY", 0)),
                sell_signals=int(summary.get("SELL", 0)),
                neutral_signals=int(summary.get("NEUTRAL", 0)),
                price=float(indicators.get("close")) if "close" in indicators else None,
            )
        finally:
            TVClient._throttle.release()

    # ------------------------------------------------------------------
    # Multi-timeframe + batch
    # ------------------------------------------------------------------
    def multi_timeframe_analysis(
        self,
        symbol: str,
        exchange: str,
        intervals: list[str] | None = None,
        *,
        screener: str = "forex",
    ) -> dict[str, Any]:
        """Run get_analysis() across multiple timeframes; return agreement summary.

        The returned dict has shape:
            {
                "symbol": ...,
                "exchange": ...,
                "per_interval": [TVAnalysis.to_dict(), ...],
                "agreement_pct": float,        # what % of TFs agree on direction
                "consensus": "BUY"|"SELL"|"NEUTRAL",
                "errors": [{interval, error}, ...],
            }

        Partial failures are tolerated — we return whatever succeeded.
        """
        ivs = intervals or ["5m", "15m", "1h", "4h", "1d"]
        results: list[TVAnalysis] = []
        errors: list[dict[str, str]] = []
        for iv in ivs:
            try:
                results.append(
                    self.get_analysis(symbol, exchange, iv, screener=screener)
                )
            except Exception as e:
                errors.append({"interval": iv, "error": str(e)[:200]})

        consensus, agreement = _consensus(results)
        return {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "intervals_requested": ivs,
            "per_interval": [r.to_dict() for r in results],
            "agreement_pct": agreement,
            "consensus": consensus,
            "errors": errors,
        }

    def combined_analysis(
        self,
        symbols: list[tuple[str, str]],
        interval: str = "15m",
        *,
        screener: str = "forex",
    ) -> list[dict[str, Any]]:
        """Batch over (symbol, exchange) pairs at a single timeframe."""
        out: list[dict[str, Any]] = []
        for sym, ex in symbols:
            try:
                a = self.get_analysis(sym, ex, interval, screener=screener)
                out.append({"ok": True, **a.to_dict()})
            except Exception as e:
                out.append(
                    {
                        "ok": False,
                        "symbol": sym,
                        "exchange": ex,
                        "interval": interval,
                        "error": str(e)[:200],
                    }
                )
        return out

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    @classmethod
    def clear_cache(cls) -> None:
        if cls._cache is not None:
            cls._cache.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_BULLISH = {"STRONG_BUY", "BUY"}
_BEARISH = {"STRONG_SELL", "SELL"}


def _consensus(results: list[TVAnalysis]) -> tuple[str, float]:
    """Return (consensus_label, agreement_pct in [0,1])."""
    if not results:
        return ("NEUTRAL", 0.0)
    buys = sum(1 for r in results if r.recommendation.upper() in _BULLISH)
    sells = sum(1 for r in results if r.recommendation.upper() in _BEARISH)
    total = len(results)
    if buys > sells:
        return ("BUY", buys / total)
    if sells > buys:
        return ("SELL", sells / total)
    return ("NEUTRAL", max(buys, sells) / total)
