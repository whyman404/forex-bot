"""Health endpoints — liveness, readiness, deep health.

Atlas Goro — three separate checks, three different purposes:

- **/healthz**       — *liveness*. Cheapest possible: is the process alive?
                       Used by Railway, Docker HEALTHCHECK, k8s livenessProbe.
                       MUST NOT touch DB / Redis / network.
- **/readyz**        — *readiness*. DB ping + Redis ping, each capped at 2 s.
                       Flips to 503 during shutdown so LB drains us.
                       Used by k8s readinessProbe and Railway's "is this
                       replica taking traffic?" hint.
- **/healthz/full**  — *deep*. Adds external deps (Stripe, email provider).
                       Slow; not for hot polling. Used by ops dashboards
                       and the smoke-test script.

References:
- "Liveness / Readiness / Startup Probes" — Kubernetes docs
- Railway healthchecks — https://docs.railway.app/reference/healthchecks
- Cindy Sridharan, "Health checks for microservices" (Medium, 2018)
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import ping_redis
from app.db.session import ping_database

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/healthz",
    include_in_schema=False,
    summary="Liveness probe (no deps, never blocks)",
)
async def healthz() -> dict[str, str]:
    """Return 200 as long as the event loop is alive.

    Railway's healthcheck should point here. DO NOT add DB / Redis pings —
    that's what /readyz is for. Conflating the two leads to cascading
    restarts when a downstream dep flaps.
    """
    return {"status": "ok", "version": __version__}


@router.get(
    "/readyz",
    include_in_schema=False,
    summary="Readiness probe — DB + Redis ping (2 s timeout each)",
)
async def readyz(request: Request) -> JSONResponse:
    """Deep-ish: are the things we need to serve a real request reachable?

    Returns 503 during shutdown so the load balancer drains us. Each
    dependency ping is capped at 2 s — total worst case ~4 s.
    """
    # Drain mode (graceful shutdown) — fail readiness so LB stops sending us
    # new requests while in-flight ones finish.
    if getattr(request.app.state, "shutting_down", False):
        return JSONResponse(
            status_code=503,
            content={"status": "draining", "checks": {}},
        )

    checks: dict[str, str] = {}
    ok = True

    db_ok, redis_ok = await asyncio.gather(
        ping_database(timeout_seconds=2.0),
        ping_redis(getattr(request.app.state, "redis", None), timeout_seconds=2.0),
        return_exceptions=False,
    )

    checks["db"] = "ok" if db_ok else "fail"
    if not db_ok:
        ok = False

    # Redis is *optional* (fail-open). Report status but don't 503 just for
    # Redis being down — the app keeps serving without rate limiting.
    if getattr(request.app.state, "redis", None) is None:
        checks["redis"] = "not_configured"
    else:
        checks["redis"] = "ok" if redis_ok else "degraded"

    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "degraded", "checks": checks},
    )


@router.get(
    "/healthz/full",
    include_in_schema=False,
    summary="Deep health — DB, Redis, Stripe, email provider",
)
async def healthz_full(request: Request) -> JSONResponse:
    """Full external-dependency probe. Slow — do NOT use as Railway probe.

    Use this from an ops dashboard or a smoke-test script.
    """
    settings = get_settings()
    checks: dict[str, Any] = {}

    # Local deps
    db_ok = await ping_database(timeout_seconds=2.0)
    checks["db"] = "ok" if db_ok else "fail"
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        checks["redis"] = "not_configured"
    else:
        checks["redis"] = "ok" if await ping_redis(redis_client, 2.0) else "fail"

    # Stripe — cheap reachability check (HEAD /v1/...). Skip if API key empty.
    if settings.stripe_api_key:
        checks["stripe"] = await _check_stripe(timeout_seconds=3.0)
    else:
        checks["stripe"] = "not_configured"

    # Email provider — connectivity (SMTP TCP open OR Resend HEAD), no auth.
    checks["email"] = await _check_email(timeout_seconds=2.0)

    bad = {"fail", "error", "timeout"}
    ok = not any(str(v) in bad for v in checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "degraded", "checks": checks, "version": __version__},
    )


# -------------------------------------------------------------------
# Internal probes
# -------------------------------------------------------------------
async def _check_stripe(timeout_seconds: float) -> str:
    """Reach Stripe API root — does NOT use our key (no DB / billing side effect)."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout_seconds) as cx:
            r = await cx.get("https://api.stripe.com/v1/")
        # 401 (no auth) is "reachable" — exactly what we want.
        return "ok" if r.status_code in {200, 401} else f"unexpected_{r.status_code}"
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as exc:  # noqa: BLE001
        logger.warning("healthz_stripe_fail", err=str(exc))
        return "fail"


async def _check_email(timeout_seconds: float) -> str:
    """Reach email provider:
       - resend → HTTPS HEAD api.resend.com
       - smtp   → TCP connect smtp_host:smtp_port
       - console → always ok
    """
    settings = get_settings()
    if settings.email_provider == "console":
        return "ok"
    if settings.email_provider == "resend":
        try:
            import httpx

            async with httpx.AsyncClient(timeout=timeout_seconds) as cx:
                r = await cx.head("https://api.resend.com")
            return "ok" if r.status_code < 500 else f"unexpected_{r.status_code}"
        except Exception:  # noqa: BLE001
            return "fail"
    # SMTP
    try:
        fut = asyncio.open_connection(settings.smtp_host, settings.smtp_port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout_seconds)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return "ok"
    except asyncio.TimeoutError:
        return "timeout"
    except Exception:  # noqa: BLE001
        return "fail"
