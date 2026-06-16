"""TradingView integration — backend → trading-engine proxy + cache.

Atlas Goro — Round 5.

This is the only place the backend talks to the engine's `/tv/*` namespace.
Everything else (router, gate, strategy_service) routes through here.

Design notes:
  - HMAC reuse: we sign requests with the same canonical scheme that
    `oms_client.OMSClient` uses (`sign_canonical`). One signer, one secret —
    don't fork.
  - Cache: two tiers, both Redis-backed when available, in-process fallback
    otherwise (dev-friendly):
        * Symbol catalog — TTL configurable (default 1h). Global key (the
          catalog is the same for every user).
        * Preview — keyed by (symbol, exchange, intervals-canonical, user_id);
          TTL 60s. Per-user so two users on different tiers can't pollute
          each other.
  - Failure modes:
        * trading-engine 5xx     → raise BadGateway equivalent (502 mapped).
        * trading-engine timeout → raise BadGateway equivalent.
        * TV disabled            → raise ServiceUnavailableError (503).
        * Redis down             → cache silently degrades (fail-open).
  - Typed return: every public method returns a Pydantic model from
    `app.schemas.tradingview`, NOT a raw dict.

Sources:
  - tradingview-ta — `https://github.com/rongardF/tradingview-ta`
  - Marc Brooker — "Errors, retries, and idempotency" (2020)
  - Cindy Sridharan — "On the diversity of failure modes" (2018)
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.schemas.tradingview import (
    SUPPORTED_TV_INTERVALS,
    TVHealth,
    TVPreview,
    TVPreviewRequest,
    TVSymbol,
    TVTimeframeAnalysis,
)
from app.services.oms_client import sign_canonical

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Dedicated errors (mapped to HTTP via the standard error handler)
# --------------------------------------------------------------------------- #


class TVDisabledError(AppError):
    """TV_ENABLED=false at the backend or the engine refused (503 upstream)."""

    status_code = 503
    code = "TV_DISABLED"
    message = "TradingView integration is disabled on this deployment."


class TVUpstreamError(AppError):
    """trading-engine returned 4xx/5xx or timed out (502 → bad gateway)."""

    status_code = 502
    code = "TV_UPSTREAM_ERROR"
    message = "TradingView upstream is not reachable."


class TVInvalidParamError(AppError):
    """Caller passed an interval not in the supported set, or other bad input."""

    status_code = 422
    code = "TV_INVALID_PARAM"
    message = "Invalid TradingView request parameters."


# --------------------------------------------------------------------------- #
# In-process fallback cache (Redis-down dev mode)
# --------------------------------------------------------------------------- #


class _InProcCache:
    """Tiny TTL cache used only when Redis is not wired (local dev).

    Not LRU — bounded by the natural shape of the data (catalog = 1 entry,
    previews = per-(symbol, intervals, user) which is bounded by user count).
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_sec: int) -> None:
        self._data[key] = (time.time() + ttl_sec, value)

    def clear(self) -> None:
        self._data.clear()


_INPROC = _InProcCache()


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


CATALOG_CACHE_KEY = "tv:catalog:v1"


def _preview_cache_key(symbol: str, exchange: str | None, intervals: list[str], user_id: UUID) -> str:
    """Stable, collision-free cache key.

    intervals are sorted so {15m,1h} and {1h,15m} hit the same entry.
    user_id is included to prevent cross-user pollution (different tiers may
    see different generated_at — we don't want a Free user's cached preview
    leaking into a Pro user's slot or vice versa).
    """
    canonical = json.dumps(
        {
            "s": symbol.upper(),
            "x": (exchange or "").upper(),
            "i": sorted(intervals),
            "u": str(user_id),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    digest = hashlib.sha256(canonical).hexdigest()[:24]
    return f"tv:preview:v1:{digest}"


class TradingViewService:
    """Backend façade for TV operations."""

    def __init__(self, redis: Any | None = None) -> None:
        s = get_settings()
        self.base_url = s.trading_engine_url.rstrip("/")
        self.secret = s.internal_api_secret
        self.timeout = httpx.Timeout(8.0, connect=3.0)
        self.tv_enabled = bool(getattr(s, "tv_enabled", True))
        self.catalog_ttl = int(getattr(s, "tv_catalog_cache_ttl_sec", 3600))
        self.preview_ttl = 60  # spec
        self.redis = redis
        # Offline detect (matches OMSClient): hostnames that look like dev stubs.
        self.offline = not self.base_url or self.base_url.endswith("trading-engine:8200")

    # ----------------------------------------------------------------- #
    # Public API
    # ----------------------------------------------------------------- #

    async def get_symbols(self) -> list[TVSymbol]:
        """Return the supported-symbol catalog. Cached for `catalog_ttl` seconds."""
        if not self.tv_enabled:
            raise TVDisabledError()

        cached = await self._cache_get(CATALOG_CACHE_KEY)
        if cached is not None:
            return [TVSymbol.model_validate(row) for row in cached]

        if self.offline:
            # Dev convenience — engine not wired; surface an empty list so the
            # UI degrades gracefully instead of erroring out.
            logger.info("tv_symbols_offline_empty")
            return []

        raw = await self._get("/tv/symbols")
        symbols_raw = raw if isinstance(raw, list) else raw.get("symbols", [])
        symbols = [self._normalize_symbol(row) for row in symbols_raw]
        # Cache the raw model dicts (cheap serialize on read).
        await self._cache_set(
            CATALOG_CACHE_KEY,
            [s.model_dump() for s in symbols],
            ttl_sec=self.catalog_ttl,
        )
        return symbols

    async def get_preview(
        self,
        *,
        request: TVPreviewRequest,
        user_id: UUID,
    ) -> TVPreview:
        """Return a multi-timeframe preview for one symbol. Cached per-user 60s."""
        if not self.tv_enabled:
            raise TVDisabledError()

        # Validate intervals against allowlist — never trust caller input.
        bad = [i for i in request.intervals if i not in SUPPORTED_TV_INTERVALS]
        if bad:
            raise TVInvalidParamError(
                f"Unsupported intervals: {bad}. Supported: {sorted(SUPPORTED_TV_INTERVALS)}",
                details={"bad_intervals": bad, "supported": sorted(SUPPORTED_TV_INTERVALS)},
            )

        key = _preview_cache_key(request.symbol, request.exchange, request.intervals, user_id)
        cached = await self._cache_get(key)
        if cached is not None:
            return TVPreview.model_validate(cached)

        if self.offline:
            raise TVUpstreamError("trading-engine offline; preview unavailable.")

        body: dict[str, Any] = {
            "symbol": request.symbol.upper(),
            "intervals": request.intervals,
        }
        if request.exchange:
            body["exchange"] = request.exchange.upper()

        raw = await self._post("/tv/preview", body)
        preview = self._normalize_preview(raw)
        await self._cache_set(key, preview.model_dump(mode="json"), ttl_sec=self.preview_ttl)
        return preview

    async def get_health(self) -> TVHealth:
        """Probe both the engine reachability and TV upstream health.

        Does NOT raise — health endpoints must never throw; they return a body
        that says what's wrong instead. We want the dashboard to show degraded
        state, not 500.
        """
        if not self.tv_enabled:
            return TVHealth(
                status="down",
                trading_engine_reachable=False,
                upstream_tv_reachable=None,
                reason="TV_ENABLED=false on backend.",
                checked_at=datetime.now(UTC),
            )

        if self.offline:
            return TVHealth(
                status="down",
                trading_engine_reachable=False,
                upstream_tv_reachable=None,
                reason="trading-engine not configured (TRADING_ENGINE_URL).",
                checked_at=datetime.now(UTC),
            )

        try:
            raw = await self._get("/tv/health")
        except TVUpstreamError as exc:
            return TVHealth(
                status="down",
                trading_engine_reachable=False,
                upstream_tv_reachable=None,
                reason=str(exc),
                checked_at=datetime.now(UTC),
            )

        engine_ok = bool(raw.get("trading_engine_reachable", True))
        upstream_ok_raw = raw.get("upstream_tv_reachable")
        upstream_ok = bool(upstream_ok_raw) if upstream_ok_raw is not None else None
        status: str = raw.get("status") or ("ok" if engine_ok and upstream_ok is not False else "degraded")
        return TVHealth(
            status=status if status in {"ok", "degraded", "down"} else "degraded",
            trading_engine_reachable=engine_ok,
            upstream_tv_reachable=upstream_ok,
            reason=raw.get("reason"),
            checked_at=datetime.now(UTC),
        )

    async def is_healthy_for_gate(self) -> tuple[bool, str | None]:
        """Tight contract for the live-gate: returns (ok, reason_if_bad).

        Treats `degraded` as a soft pass — TV is up but cross-TF agreement is
        spotty. Only `down` blocks live start.
        """
        health = await self.get_health()
        if health.status == "ok":
            return True, None
        if health.status == "degraded":
            return True, None
        return False, health.reason or "TradingView health is 'down'."

    # ----------------------------------------------------------------- #
    # HTTP plumbing — mirrors OMSClient (don't fork the signer)
    # ----------------------------------------------------------------- #

    def _sign_headers(self, method: str, path: str, body: bytes) -> dict[str, str]:
        if not self.secret:
            return {}
        ts, nonce, sig = sign_canonical(self.secret, method, path, body)
        return {
            "X-Internal-Ts": ts,
            "X-Internal-Nonce": nonce,
            "X-Internal-Sig": sig,
        }

    async def _get(self, path: str) -> Any:
        body = b""
        headers = {"Accept": "application/json"}
        headers.update(self._sign_headers("GET", path, body))
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                r = await client.get(f"{self.base_url}{path}", headers=headers)
            except httpx.HTTPError as exc:
                logger.warning("tv_call_failed", path=path, err=str(exc))
                raise TVUpstreamError(f"trading-engine GET {path} failed: {exc}") from exc
        if r.status_code == 503:
            raise TVDisabledError("trading-engine reports TV disabled.")
        if r.status_code >= 400:
            logger.warning("tv_call_status", path=path, status=r.status_code)
            raise TVUpstreamError(
                f"trading-engine GET {path} → {r.status_code}: {r.text[:200]}"
            )
        try:
            return r.json()
        except Exception as exc:  # noqa: BLE001
            raise TVUpstreamError(f"Malformed JSON from {path}") from exc

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        headers.update(self._sign_headers("POST", path, body))
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                r = await client.post(f"{self.base_url}{path}", content=body, headers=headers)
            except httpx.HTTPError as exc:
                logger.warning("tv_call_failed", path=path, err=str(exc))
                raise TVUpstreamError(f"trading-engine POST {path} failed: {exc}") from exc
        if r.status_code == 503:
            raise TVDisabledError("trading-engine reports TV disabled.")
        if r.status_code == 422:
            # Pass-through validation error from upstream.
            try:
                details = r.json()
            except Exception:  # noqa: BLE001
                details = {"raw": r.text[:200]}
            raise TVInvalidParamError(
                "trading-engine rejected request parameters.",
                details={"upstream": details},
            )
        if r.status_code >= 400:
            logger.warning("tv_call_status", path=path, status=r.status_code)
            raise TVUpstreamError(
                f"trading-engine POST {path} → {r.status_code}: {r.text[:200]}"
            )
        try:
            return r.json()
        except Exception as exc:  # noqa: BLE001
            raise TVUpstreamError(f"Malformed JSON from {path}") from exc

    # ----------------------------------------------------------------- #
    # Cache abstraction
    # ----------------------------------------------------------------- #

    async def _cache_get(self, key: str) -> Any | None:
        if self.redis is not None:
            try:
                blob = await self.redis.get(key)
                if blob is None:
                    return None
                return json.loads(blob)
            except Exception as exc:  # noqa: BLE001 — fail open
                logger.warning("tv_cache_redis_get_failed", key=key, err=str(exc))
                return _INPROC.get(key)
        return _INPROC.get(key)

    async def _cache_set(self, key: str, value: Any, *, ttl_sec: int) -> None:
        if self.redis is not None:
            try:
                await self.redis.set(key, json.dumps(value), ex=ttl_sec)
                return
            except Exception as exc:  # noqa: BLE001 — fail open
                logger.warning("tv_cache_redis_set_failed", key=key, err=str(exc))
        _INPROC.set(key, value, ttl_sec)

    # ----------------------------------------------------------------- #
    # Wire → schema normalization
    # ----------------------------------------------------------------- #

    @staticmethod
    def _normalize_symbol(row: dict[str, Any]) -> TVSymbol:
        """Engine returns either `tradingview.symbols.list_supported()` shape
        (`internal_symbol`/`tv_symbol`/`tv_exchange`/`asset_class`/`display_name`)
        or a flat shape (`code`/`tv_symbol`/`tv_exchange`/`asset_class`).
        Tolerate both.
        """
        code = row.get("code") or row.get("internal_symbol") or row.get("tv_symbol") or ""
        return TVSymbol(
            code=str(code),
            tv_symbol=str(row.get("tv_symbol") or code),
            tv_exchange=str(row.get("tv_exchange") or row.get("exchange") or "FX_IDC"),
            asset_class=row.get("asset_class") or "forex",  # type: ignore[arg-type]
            display_name=str(row.get("display_name") or row.get("name") or code),
        )

    @staticmethod
    def _normalize_preview(raw: dict[str, Any]) -> TVPreview:
        tfs_raw = raw.get("timeframes") or raw.get("analysis") or []
        tfs: list[TVTimeframeAnalysis] = []
        for tf in tfs_raw:
            tfs.append(
                TVTimeframeAnalysis(
                    interval=str(tf.get("interval") or tf.get("tf") or "?"),
                    recommendation=str(tf.get("recommendation") or "NEUTRAL"),  # type: ignore[arg-type]
                    buy_count=int(tf.get("buy_count") or tf.get("buy") or 0),
                    sell_count=int(tf.get("sell_count") or tf.get("sell") or 0),
                    neutral_count=int(tf.get("neutral_count") or tf.get("neutral") or 0),
                )
            )
        generated_raw = raw.get("generated_at")
        if isinstance(generated_raw, str):
            try:
                generated = datetime.fromisoformat(generated_raw.replace("Z", "+00:00"))
            except ValueError:
                generated = datetime.now(UTC)
        elif isinstance(generated_raw, datetime):
            generated = generated_raw
        else:
            generated = datetime.now(UTC)
        return TVPreview(
            symbol=str(raw.get("symbol") or "?"),
            exchange=str(raw.get("exchange") or "?"),
            score=float(raw.get("score") or 0.0),
            confidence=float(raw.get("confidence") or 0.0),
            timeframes=tfs,
            generated_at=generated,
        )


__all__ = [
    "TradingViewService",
    "TVDisabledError",
    "TVUpstreamError",
    "TVInvalidParamError",
]
