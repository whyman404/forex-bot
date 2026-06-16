"""Redis-backed sliding-window rate limiter.

Algorithm: fixed-window counter with sub-window for smoothing.
Key shape: `rl:{scope}:{identity}:{window_epoch}` — TTL = window + grace.

Identity precedence:
  1. authenticated user_id (preferred — anti-share-abuse)
  2. client IP (fallback)

Atlas Goro — rate limiting is *eventual*. Tolerate Redis outage by failing OPEN
(let traffic through, alert) rather than failing CLOSED (lock everyone out).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import RateLimitedError
from app.core.logging import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


class RateLimiter:
    """Use via FastAPI dependency in router with `Depends(rate_limit(scope='auth', per_min=10))`."""

    def __init__(self, redis: "Redis") -> None:
        self.redis = redis

    async def check(self, *, scope: str, identity: str, per_min: int) -> None:
        """Raise `RateLimitedError` if the identity has exceeded `per_min` in current window."""
        window = int(time.time() // 60)
        key = f"rl:{scope}:{identity}:{window}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, 90)  # window + grace
        except Exception as exc:  # noqa: BLE001 — fail open
            logger.warning("rate_limit_redis_unavailable", err=str(exc))
            return

        if count > per_min:
            raise RateLimitedError(
                f"Rate limit exceeded for scope={scope}",
                details={"scope": scope, "limit_per_min": per_min},
            )


def identity_of(request: Request) -> str:
    """Authenticated user_id if available, else client IP."""
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"u:{user_id}"
    # X-Forwarded-For — trust only if behind known reverse proxy (configured at infra).
    xff = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = xff or (request.client.host if request.client else "unknown")
    return f"ip:{ip}"


def rate_limit(*, scope: str, per_min: int | None = None):
    """Factory: returns a dependency that enforces the limit on each call."""
    settings = get_settings()
    limit = per_min or settings.rate_limit_default_per_min

    async def _dep(request: Request) -> None:
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        if limiter is None:
            # Redis not wired — skip silently (dev convenience).
            return
        await limiter.check(scope=scope, identity=identity_of(request), per_min=limit)

    return _dep


def tier_rate_limit(*, scope: str = "tier"):
    """Per-tier rate-limit dependency.

    Looks up the user's subscription and applies plan-specific RPM:
      - free / inactive       → rate_limit_free_per_min
      - pro_monthly           → rate_limit_pro_per_min
      - pro_yearly / lifetime → rate_limit_pro_yearly_per_min

    Unauthenticated requests get free tier.
    """
    settings = get_settings()

    async def _dep(request: Request) -> None:
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        if limiter is None:
            return

        # Default = free tier
        limit = settings.rate_limit_free_per_min
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            # Best-effort plan lookup — never block traffic on DB hiccup.
            try:
                from sqlalchemy import desc, select

                from app.db.session import SessionLocal
                from app.models.subscription import Subscription

                async with SessionLocal() as s:
                    result = await s.execute(
                        select(Subscription)
                        .where(Subscription.user_id == user_id)
                        .order_by(desc(Subscription.created_at))
                        .limit(1)
                    )
                    sub = result.scalars().first()
                    if sub is not None and sub.status in {"active", "trialing"}:
                        if sub.plan == "pro_monthly":
                            limit = settings.rate_limit_pro_per_min
                        elif sub.plan in {"pro_yearly", "lifetime"}:
                            limit = settings.rate_limit_pro_yearly_per_min
            except Exception as exc:  # noqa: BLE001
                logger.warning("tier_rate_limit_lookup_failed", err=str(exc))

        await limiter.check(scope=scope, identity=identity_of(request), per_min=limit)

    return _dep
