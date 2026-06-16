"""Async SQLAlchemy engine + session factory.

Atlas Goro — one engine per process, pooled. Sessions are short-lived,
scoped per request via FastAPI dependency.

Round 4 — Railway / Neon hardening:
- Auto-detect Neon (host endswith `.neon.tech`) → enable SSL.
- Respect explicit `sslmode=require` / `ssl=true` in DSN.
- Strip `sslmode` from URL when passing to asyncpg (asyncpg uses its own
  `ssl` connect_arg, not the libpq param), to avoid the "invalid dsn
  parameter" error reported in asyncpg #898.
- Pool sized for serverless-adjacent: small base, modest overflow,
  pre_ping to survive Neon's idle connection eviction, recycle to dodge
  edge-network NAT timeouts.
"""

from __future__ import annotations

import ssl as ssl_lib
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


# Params libpq understands but asyncpg's DSN parser does NOT — must be stripped.
_LIBPQ_ONLY_PARAMS = {"sslmode", "ssl", "channel_binding", "target_session_attrs"}


def _strip_libpq_params(url: str) -> str:
    """Remove libpq-only query params; asyncpg gets `ssl` via connect_args."""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    kept = [
        (k, v) for (k, v) in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _LIBPQ_ONLY_PARAMS
    ]
    new_query = urlencode(kept)
    return urlunparse(parsed._replace(query=new_query))


def _build_ssl_context() -> ssl_lib.SSLContext:
    """Default TLS context for asyncpg.

    Uses certifi-style system CA store (Python's `create_default_context`).
    Neon serves a publicly-trusted cert, so verify mode is correct.
    """
    ctx = ssl_lib.create_default_context()
    # Neon presents a valid cert chain; keep verify on.
    ctx.check_hostname = True
    ctx.verify_mode = ssl_lib.CERT_REQUIRED
    return ctx


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    raw_url = str(settings.database_url)

    connect_args: dict[str, Any] = {}
    if settings.db_requires_ssl:
        connect_args["ssl"] = _build_ssl_context()

    # asyncpg can't parse libpq-only flags — strip after we've made our SSL decision.
    sanitized_url = _strip_libpq_params(raw_url)

    return create_async_engine(
        sanitized_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_pre_ping=True,           # survive Neon idle eviction + DB restart
        pool_recycle=settings.database_pool_recycle_seconds,  # 5 min — beat NAT
        echo=False,                   # use OTel SQLAlchemy instrumentor instead
        future=True,
        connect_args=connect_args,
    )


engine: AsyncEngine = _build_engine()

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session that commits on success, rolls back on error.

    Usage:
        @router.post("/foo")
        async def create_foo(db: AsyncSession = Depends(get_db)): ...
    """
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        # NOTE: services own commit boundaries explicitly. We rollback on exception
        # but do NOT auto-commit here — explicit > implicit for transaction scope.


async def dispose_engine() -> None:
    """Tear down engine on app shutdown."""
    await engine.dispose()


async def ping_database(timeout_seconds: float = 2.0) -> bool:
    """Cheap liveness check for /readyz.

    Returns True iff `SELECT 1` succeeds within the timeout.
    """
    import asyncio as _asyncio

    from sqlalchemy import text

    async def _do() -> bool:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True

    try:
        return await _asyncio.wait_for(_do(), timeout=timeout_seconds)
    except Exception:  # noqa: BLE001 — health check is best-effort
        return False
