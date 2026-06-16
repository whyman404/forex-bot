"""TradingView signal endpoints — Round 5.

Atlas Goro — these are *thin* proxies. All real logic lives in
`app.services.tradingview_service.TradingViewService`. The router only:
  1. Resolves auth (Depends(get_current_user)).
  2. Applies rate limits (TV-specific + per-tier; whichever is stricter wins).
  3. Wraps the service call.

Routes:
  - POST /api/v1/tv/preview   — multi-TF analysis for one symbol.
  - GET  /api/v1/tv/symbols   — supported symbol catalog (1h cached).
  - GET  /api/v1/tv/health    — engine + TV upstream reachability.

Rate-limit composition: both deps fire; the stricter one trips first. We
deliberately list the TV scope after the tier scope so the per-tier counter
doesn't get burned by a TV-only retry storm (per-minute window resets at
:00 anyway).

Audit log: previews are *read* operations, NOT audited (would explode the
log volume). Strategy lifecycle (start/stop/kill) is audited by
strategy_service — see strategy_service.py R5 update.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.errors import ErrorResponse
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import rate_limit, tier_rate_limit
from app.models.user import User
from app.schemas.tradingview import (
    TVHealth,
    TVPreview,
    TVPreviewRequest,
    TVSymbol,
)
from app.services.tradingview_service import TradingViewService

router = APIRouter()

ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _build_service(request: Request) -> TradingViewService:
    """Construct the service with the app-state Redis client (or None)."""
    redis = getattr(request.app.state, "redis", None)
    return TradingViewService(redis=redis)


@router.post(
    "/preview",
    response_model=TVPreview,
    responses=ERROR_RESPONSES,
    summary="Multi-timeframe TradingView signal preview for a symbol",
)
async def tv_preview(
    payload: TVPreviewRequest,
    request: Request,
    user: User = Depends(get_current_user),
    _tier_rl: None = Depends(tier_rate_limit(scope="tv_tier")),
    _tv_rl: None = Depends(rate_limit(scope="tv_preview", per_min=10)),
) -> TVPreview:
    """Return a multi-timeframe analysis snapshot from the trading-engine.

    Cached per `(symbol, exchange, intervals, user_id)` for 60 s.

    Errors:
      - 422 — interval not in supported set.
      - 429 — rate limited (10/min per user OR per-tier — whichever first).
      - 502 — engine unreachable / TV upstream error.
      - 503 — TV integration disabled at backend or engine.
    """
    svc = _build_service(request)
    return await svc.get_preview(request=payload, user_id=user.id)


@router.get(
    "/symbols",
    response_model=list[TVSymbol],
    responses=ERROR_RESPONSES,
    summary="List supported TradingView symbols (catalog, ~1h cached)",
)
async def tv_symbols(
    request: Request,
    _user: User = Depends(get_current_user),
    _tier_rl: None = Depends(tier_rate_limit(scope="tv_tier")),
) -> list[TVSymbol]:
    """Return the curated symbol catalog the engine supports.

    Catalog is global (same for every user) and cached in Redis for
    `TV_CATALOG_CACHE_TTL_SEC` seconds (default 1h).
    """
    svc = _build_service(request)
    return await svc.get_symbols()


@router.get(
    "/health",
    response_model=TVHealth,
    responses={401: {"model": ErrorResponse}},
    summary="TradingView integration health (engine + TV upstream)",
)
async def tv_health(
    request: Request,
    _user: User = Depends(get_current_user),
) -> TVHealth:
    """Health endpoint — NEVER raises. UI uses this as the live-trading
    extra-gate for `tv_signal` strategies.
    """
    svc = _build_service(request)
    return await svc.get_health()
