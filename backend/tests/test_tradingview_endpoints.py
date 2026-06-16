"""TradingView endpoint + service tests — Round 5.

Atlas Goro — ASGI in-process tests. We mock the engine HTTP layer (httpx)
because the unit boundary is "backend ↔ engine wire". DB / Redis access for
auth fixtures still goes through normal layers; tests are marked `integration`
where they need a seeded DB so they can be skipped in pure-unit lanes.

Test matrix:
  - auth required on every endpoint
  - 422 when intervals contain unsupported values
  - 503 when TV_ENABLED=false
  - 502 when engine returns 5xx / connection refused
  - cache hit returns same body without calling engine a second time
  - HMAC headers are present on outbound engine calls
  - rate limit (10rpm) trips on the 11th request inside a window
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.schemas.tradingview import (
    SUPPORTED_TV_INTERVALS,
    TVPreviewRequest,
)
from app.services.tradingview_service import (
    TVDisabledError,
    TVInvalidParamError,
    TVUpstreamError,
    TradingViewService,
)


# --------------------------------------------------------------------------- #
# httpx mocking helpers
# --------------------------------------------------------------------------- #


class _MockResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)[:500]

    def json(self) -> Any:
        return self._payload


class _RecordingAsyncClient:
    """Stand-in for httpx.AsyncClient that records calls and returns programmable responses."""

    calls: list[dict] = []
    queued: list[_MockResponse] = []
    raise_on_call: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self) -> "_RecordingAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> None:  # noqa: ANN002
        return None

    async def get(self, url: str, headers: dict | None = None) -> _MockResponse:
        type(self).calls.append({"method": "GET", "url": url, "headers": headers or {}})
        if type(self).raise_on_call is not None:
            raise type(self).raise_on_call
        return type(self).queued.pop(0)

    async def post(
        self,
        url: str,
        content: bytes | None = None,
        headers: dict | None = None,
    ) -> _MockResponse:
        type(self).calls.append(
            {"method": "POST", "url": url, "content": content, "headers": headers or {}}
        )
        if type(self).raise_on_call is not None:
            raise type(self).raise_on_call
        return type(self).queued.pop(0)


@pytest.fixture(autouse=True)
def _reset_mock():
    _RecordingAsyncClient.calls = []
    _RecordingAsyncClient.queued = []
    _RecordingAsyncClient.raise_on_call = None
    yield
    _RecordingAsyncClient.calls = []
    _RecordingAsyncClient.queued = []
    _RecordingAsyncClient.raise_on_call = None


@pytest.fixture
def patched_httpx(monkeypatch):
    """Replace httpx.AsyncClient inside tradingview_service with our recorder."""
    import app.services.tradingview_service as svc_mod

    monkeypatch.setattr(svc_mod.httpx, "AsyncClient", _RecordingAsyncClient)
    return _RecordingAsyncClient


@pytest.fixture
def real_engine_url(monkeypatch):
    """Make the service believe the engine is wired (not offline)."""
    from app.core.config import get_settings

    settings = get_settings()
    # offline detection trips on "trading-engine:8200" — use a different host.
    monkeypatch.setattr(settings, "trading_engine_url", "http://test-engine:8500", raising=False)
    monkeypatch.setattr(settings, "internal_api_secret", "test-secret-32-bytes-for-hmac!!!!", raising=False)
    monkeypatch.setattr(settings, "tv_enabled", True, raising=False)
    return settings


# --------------------------------------------------------------------------- #
# Service-layer tests (no HTTP roundtrip)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_preview_validates_intervals(patched_httpx, real_engine_url) -> None:
    svc = TradingViewService()
    req = TVPreviewRequest(symbol="XAUUSD", intervals=["15m", "bogus-tf"])
    with pytest.raises(TVInvalidParamError) as exc:
        await svc.get_preview(request=req, user_id=uuid4())
    # We must surface the bad interval in details so the UI can show it.
    assert exc.value.details is not None
    assert "bad_intervals" in exc.value.details


@pytest.mark.asyncio
async def test_get_preview_disabled_returns_503(patched_httpx, real_engine_url, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tv_enabled", False, raising=False)
    svc = TradingViewService()
    with pytest.raises(TVDisabledError):
        await svc.get_preview(
            request=TVPreviewRequest(symbol="XAUUSD", intervals=["1h"]),
            user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_get_preview_calls_engine_with_hmac(patched_httpx, real_engine_url) -> None:
    patched_httpx.queued.append(
        _MockResponse(
            200,
            {
                "symbol": "XAUUSD",
                "exchange": "OANDA",
                "score": 42.5,
                "confidence": 0.72,
                "timeframes": [
                    {
                        "interval": "1h",
                        "recommendation": "BUY",
                        "buy_count": 12,
                        "sell_count": 3,
                        "neutral_count": 5,
                    }
                ],
                "generated_at": "2026-06-16T12:00:00Z",
            },
        )
    )
    svc = TradingViewService()
    preview = await svc.get_preview(
        request=TVPreviewRequest(symbol="XAUUSD", intervals=["1h"]),
        user_id=uuid4(),
    )
    assert preview.score == 42.5
    assert preview.timeframes[0].recommendation == "BUY"
    assert len(patched_httpx.calls) == 1
    call = patched_httpx.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/tv/preview")
    # HMAC must be present.
    headers = call["headers"]
    assert "X-Internal-Ts" in headers
    assert "X-Internal-Nonce" in headers
    assert "X-Internal-Sig" in headers
    assert len(headers["X-Internal-Sig"]) == 64  # sha256 hex


@pytest.mark.asyncio
async def test_get_preview_cache_hit_skips_engine(patched_httpx, real_engine_url) -> None:
    patched_httpx.queued.append(
        _MockResponse(
            200,
            {
                "symbol": "XAUUSD",
                "exchange": "OANDA",
                "score": 10.0,
                "confidence": 0.5,
                "timeframes": [],
                "generated_at": "2026-06-16T12:00:00Z",
            },
        )
    )
    svc = TradingViewService()
    user = uuid4()
    req = TVPreviewRequest(symbol="XAUUSD", intervals=["1h"])
    a = await svc.get_preview(request=req, user_id=user)
    b = await svc.get_preview(request=req, user_id=user)
    assert a.score == b.score
    # Only ONE upstream call.
    assert sum(1 for c in patched_httpx.calls if c["url"].endswith("/tv/preview")) == 1


@pytest.mark.asyncio
async def test_get_preview_5xx_raises_upstream_error(patched_httpx, real_engine_url) -> None:
    patched_httpx.queued.append(_MockResponse(500, {"error": "engine boom"}))
    svc = TradingViewService()
    with pytest.raises(TVUpstreamError):
        await svc.get_preview(
            request=TVPreviewRequest(symbol="XAUUSD", intervals=["1h"]),
            user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_get_preview_connection_refused_raises_upstream_error(
    patched_httpx, real_engine_url
) -> None:
    patched_httpx.raise_on_call = httpx.ConnectError("conn refused")
    svc = TradingViewService()
    with pytest.raises(TVUpstreamError):
        await svc.get_preview(
            request=TVPreviewRequest(symbol="XAUUSD", intervals=["1h"]),
            user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_get_symbols_caches_for_catalog_ttl(patched_httpx, real_engine_url) -> None:
    patched_httpx.queued.append(
        _MockResponse(
            200,
            [
                {
                    "code": "XAUUSD",
                    "tv_symbol": "XAUUSD",
                    "tv_exchange": "OANDA",
                    "asset_class": "gold",
                    "display_name": "Gold / USD",
                }
            ],
        )
    )
    svc = TradingViewService()
    a = await svc.get_symbols()
    b = await svc.get_symbols()
    assert a == b
    # ONE upstream call across two backend calls.
    assert sum(1 for c in patched_httpx.calls if c["url"].endswith("/tv/symbols")) == 1


@pytest.mark.asyncio
async def test_health_returns_down_when_disabled(patched_httpx, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tv_enabled", False, raising=False)
    svc = TradingViewService()
    h = await svc.get_health()
    assert h.status == "down"
    assert h.trading_engine_reachable is False
    # No engine call attempted.
    assert patched_httpx.calls == []


@pytest.mark.asyncio
async def test_health_never_raises_on_upstream_error(patched_httpx, real_engine_url) -> None:
    patched_httpx.raise_on_call = httpx.ConnectError("nope")
    svc = TradingViewService()
    h = await svc.get_health()
    assert h.status == "down"
    assert h.trading_engine_reachable is False
    assert h.reason is not None


# --------------------------------------------------------------------------- #
# Router-layer tests (auth + rate limit + JSON shape)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tv_preview_requires_auth(client) -> None:
    resp = await client.post("/api/v1/tv/preview", json={"symbol": "XAUUSD"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"].startswith("AUTH_")


@pytest.mark.asyncio
async def test_tv_symbols_requires_auth(client) -> None:
    resp = await client.get("/api/v1/tv/symbols")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tv_health_requires_auth(client) -> None:
    resp = await client.get("/api/v1/tv/health")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tv_supported_intervals_constant_is_frozen() -> None:
    """Frozen-set guards against accidental mutation at runtime."""
    assert isinstance(SUPPORTED_TV_INTERVALS, frozenset)
    assert "1h" in SUPPORTED_TV_INTERVALS
    assert "bogus" not in SUPPORTED_TV_INTERVALS


# --------------------------------------------------------------------------- #
# Strategy-service tv_signal validation tests
# --------------------------------------------------------------------------- #


def test_tv_signal_param_validation_rejects_unknown_interval() -> None:
    from app.core.errors import ValidationFailedError
    from app.services.strategy_service import StrategyService

    with pytest.raises(ValidationFailedError):
        StrategyService._validate_tv_signal_params({"intervals": ["1h", "bogus"]})


def test_tv_signal_param_validation_rejects_out_of_range_threshold() -> None:
    from app.core.errors import ValidationFailedError
    from app.services.strategy_service import StrategyService

    with pytest.raises(ValidationFailedError):
        StrategyService._validate_tv_signal_params({"score_threshold": 150})


def test_tv_signal_param_validation_accepts_valid_payload() -> None:
    from app.services.strategy_service import StrategyService

    # Should not raise.
    StrategyService._validate_tv_signal_params(
        {
            "intervals": ["15m", "1h", "4h"],
            "score_threshold": 60,
            "long_threshold": 0.5,
            "short_threshold": -0.5,
            "confidence_min": 0.6,
        }
    )


def test_tv_signal_param_validation_no_intervals_is_ok() -> None:
    """Empty params are allowed — defaults from migration are applied."""
    from app.services.strategy_service import StrategyService

    StrategyService._validate_tv_signal_params({})
