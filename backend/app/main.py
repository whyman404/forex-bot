"""FastAPI application entrypoint.

Atlas Goro — keep this file thin. Wire-up only.
Order of middleware matters: outermost first (request_id), innermost last (CORS).

Round 4 (Railway / Vercel / Neon / Upstash readiness):
- CORS accepts allow_origin_regex for `https://*.vercel.app` preview branches.
- GZip middleware shrinks egress (Railway charges per-GB).
- Lifespan: opt-in migrations, Sentry tags with Railway service/env, graceful
  Redis + DB shutdown. SIGTERM is handled by Uvicorn itself; we add a small
  drain grace via `app.state.shutting_down` so handlers can return 503 fast.
- Health endpoints split into /healthz (liveness), /readyz (readiness),
  and /healthz/full (deep-dive with external deps).
"""

from __future__ import annotations

import asyncio
import signal as _signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import api_router
from app.core.config import get_settings
from app.core.errors import AppError, ErrorBody, ErrorResponse
from app.core.logging import configure_logging, get_logger
from app.core.migrate_on_boot import run_migrations_if_enabled
from app.core.redis import build_redis_client, close_redis
from app.db.session import dispose_engine
from app.middleware.audit import AuditMutationMiddleware
from app.middleware.rate_limit import RateLimiter
from app.middleware.request_id import RequestIdMiddleware

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    logger.info(
        "startup",
        env=settings.app_env,
        version=__version__,
        railway_service=settings.railway_service_name or None,
        railway_env=settings.railway_environment_name or None,
    )

    app.state.shutting_down = False

    # ---- Sentry ----
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            release=__version__,
            traces_sample_rate=settings.otel_traces_sampler_arg,
            send_default_pii=False,
        )
        # Auto-tag Railway service/env if we're on Railway.
        if settings.railway_service_name:
            sentry_sdk.set_tag("railway.service", settings.railway_service_name)
        if settings.railway_environment_name:
            sentry_sdk.set_tag("railway.environment", settings.railway_environment_name)

    # ---- Redis (rate limiter, optional / fail-open) ----
    redis_client: Redis | None = build_redis_client()
    if redis_client is not None:
        try:
            await asyncio.wait_for(redis_client.ping(), timeout=settings.redis_socket_timeout_seconds)
            app.state.rate_limiter = RateLimiter(redis_client)
            logger.info("redis_connected", tls=settings.redis_uses_tls)
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_unavailable_skipping_rate_limit", err=str(exc))
            app.state.rate_limiter = None
    else:
        app.state.rate_limiter = None

    app.state.redis = redis_client

    # ---- Opt-in migrations on boot ----
    try:
        await run_migrations_if_enabled()
    except Exception as exc:  # noqa: BLE001
        logger.error("migrate_on_boot_failed", err=str(exc))
        # We continue startup; alarm via Sentry.

    # ---- OpenTelemetry — best-effort, skip if exporter not configured ----
    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            attrs = {"service.name": settings.otel_service_name}
            if settings.railway_service_name:
                attrs["railway.service"] = settings.railway_service_name
            if settings.railway_environment_name:
                attrs["railway.environment"] = settings.railway_environment_name

            resource = Resource.create(attrs)
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
            )
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app)
            SQLAlchemyInstrumentor().instrument()
            logger.info("otel_instrumented")
        except Exception as exc:  # noqa: BLE001
            logger.warning("otel_setup_failed", err=str(exc))

    # ---- Graceful shutdown signal hook (best-effort) ----
    # Uvicorn already traps SIGTERM and stops accepting new requests; we
    # add a `shutting_down` flag so /readyz can flip to 503 quickly and
    # Railway's load balancer drains us cleanly.
    loop = asyncio.get_running_loop()

    def _on_term() -> None:
        logger.info("sigterm_received_draining")
        app.state.shutting_down = True

    for sig in (_signal.SIGTERM, _signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_term)
        except (NotImplementedError, ValueError):
            # Windows or already-bound handlers — Uvicorn handles it.
            pass

    try:
        yield
    finally:
        logger.info("shutdown_begin")
        app.state.shutting_down = True
        # Give in-flight requests a moment to finish (Railway sends SIGTERM
        # then waits up to ~30 s before SIGKILL).
        await asyncio.sleep(min(settings.shutdown_grace_seconds, 1.0))
        await close_redis(redis_client)
        await dispose_engine()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = get_settings()

    # OpenAPI server URL: prefer Railway public domain if set, else localhost.
    servers: list[dict] = []
    if settings.railway_public_domain:
        servers.append({
            "url": f"https://{settings.railway_public_domain}",
            "description": "Railway public",
        })
    if settings.backend_public_url and settings.backend_public_url != "http://localhost:8000":
        servers.append({
            "url": settings.backend_public_url,
            "description": "Configured public URL",
        })

    app = FastAPI(
        title="Forex Bot API",
        version=__version__,
        description="Forex/Crypto trading bot SaaS — backend API.",
        openapi_url="/openapi.json" if not settings.is_production else None,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        servers=servers or None,
        lifespan=lifespan,
    )

    # ===== Middleware (outer → inner) =====
    # Order: GZip outermost (compress before any other layer); request-id next
    # so every other layer sees it; CORS for browsers; audit innermost (sees
    # the authn-populated user_id).
    app.add_middleware(AuditMutationMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.effective_cors_origins,
        allow_origin_regex=settings.cors_allow_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    # GZip last in `add_middleware` call order means OUTERMOST at runtime
    # (Starlette wraps in reverse) — so compression runs after CORS preflight.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # ===== Exception handlers =====

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        trace_id = getattr(request.state, "request_id", None)
        logger.warning(
            "app_error",
            code=exc.code,
            status=exc.status_code,
            path=request.url.path,
            err=exc.message,
        )
        body = ErrorResponse(
            error=ErrorBody(
                code=exc.code, message=exc.message, details=exc.details, trace_id=trace_id
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(body, by_alias=True),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        trace_id = getattr(request.state, "request_id", None)
        body = ErrorResponse(
            error=ErrorBody(
                code="VALIDATION_FAILED",
                message="Request validation failed.",
                details={"errors": jsonable_encoder(exc.errors())},
                trace_id=trace_id,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=jsonable_encoder(body, by_alias=True),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        trace_id = getattr(request.state, "request_id", None)
        body = ErrorResponse(
            error=ErrorBody(
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
                trace_id=trace_id,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(body, by_alias=True),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        trace_id = getattr(request.state, "request_id", None)
        logger.exception("unhandled_exception", path=request.url.path)
        body = ErrorResponse(
            error=ErrorBody(
                code="INTERNAL_ERROR",
                message="Unexpected error.",
                trace_id=trace_id,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=jsonable_encoder(body, by_alias=True),
        )

    # ===== Mount routers =====
    # Health router carries /healthz, /readyz, /healthz/full at app root.
    from app.api import health as health_router_module

    app.include_router(health_router_module.router, tags=["health"])
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
