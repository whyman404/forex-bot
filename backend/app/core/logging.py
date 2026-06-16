"""Structured logging via structlog → JSON to stdout.

Atlas Goro — logs are for humans debugging at 2am. Make them grep-friendly.

Every log line includes:
  - timestamp (ISO 8601)
  - level
  - logger name
  - request_id (set by middleware via contextvars)
  - trace_id / span_id (when OpenTelemetry instrumented)
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import get_settings

# ---- Context propagation ----------------------------------------------------

# Set by request_id middleware; read by every log call within the request scope.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)


def _add_request_context(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Inject request_id + user_id from contextvars into every log line."""
    if (rid := request_id_ctx.get()) is not None:
        event_dict["request_id"] = rid
    if (uid := user_id_ctx.get()) is not None:
        event_dict["user_id"] = uid
    return event_dict


def _add_otel_trace(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Attach OTel trace_id / span_id if a span is active."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:  # noqa: BLE001 — never break logging
        pass
    return event_dict


def configure_logging() -> None:
    """Idempotent logging setup. Call once from `main.py`."""
    settings = get_settings()

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_request_context,
        _add_otel_trace,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.is_production or settings.app_env == "staging":
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Dev: human-friendly colored console
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO),
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Tame noisy stdlib loggers — uvicorn/SQLAlchemy already emit access logs.
    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger bound to `name`."""
    return structlog.get_logger(name)  # type: ignore[return-value]
