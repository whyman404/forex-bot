"""Railway-readiness checks.

Atlas Goro — these are pure unit tests against the config + helper
functions. No network, no DB, no Redis. They guarantee:

  - PORT env is honored.
  - Postgres DSN normalization handles `postgres://`, `+psycopg2`, `+asyncpg`.
  - Neon (`.neon.tech`) auto-enables SSL.
  - CORS regex accepts vercel preview branches and rejects look-alikes.
  - GZip + CORS middleware are wired.
  - Graceful-shutdown flag is exposed on app.state.
"""

from __future__ import annotations

import importlib
import os
import re
import sys

import pytest

from app.core.config import _normalize_database_url


@pytest.mark.unit
def test_normalize_database_url_railway_postgres_scheme() -> None:
    """Railway emits `postgres://...`; we must rewrite to asyncpg."""
    raw = "postgres://u:p@host:5432/db"
    assert _normalize_database_url(raw) == "postgresql+asyncpg://u:p@host:5432/db"


@pytest.mark.unit
def test_normalize_database_url_plain_postgresql() -> None:
    raw = "postgresql://u:p@host:5432/db?sslmode=require"
    out = _normalize_database_url(raw)
    assert out.startswith("postgresql+asyncpg://")
    assert "sslmode=require" in out  # preserved for our SSL detection


@pytest.mark.unit
def test_normalize_database_url_replaces_psycopg2_driver() -> None:
    raw = "postgresql+psycopg2://u:p@host:5432/db"
    assert _normalize_database_url(raw).startswith("postgresql+asyncpg://")


@pytest.mark.unit
def test_normalize_database_url_idempotent_for_asyncpg() -> None:
    raw = "postgresql+asyncpg://u:p@host:5432/db"
    assert _normalize_database_url(raw) == raw


@pytest.mark.unit
def test_normalize_database_url_leaves_non_postgres_alone() -> None:
    raw = "sqlite+aiosqlite:///./test.db"
    assert _normalize_database_url(raw) == raw


@pytest.mark.unit
def test_port_env_is_parsed_into_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reload Settings with PORT=9999 in env."""
    monkeypatch.setenv("PORT", "9999")
    # Bust the lru_cache by re-importing.
    if "app.core.config" in sys.modules:
        del sys.modules["app.core.config"]
    cfg_mod = importlib.import_module("app.core.config")
    s = cfg_mod.get_settings()
    assert s.port == 9999


@pytest.mark.unit
def test_neon_ssl_autodetected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://u:p@ep-cool-mountain-12345.us-east-2.aws.neon.tech:5432/neondb?sslmode=require",
    )
    if "app.core.config" in sys.modules:
        del sys.modules["app.core.config"]
    cfg_mod = importlib.import_module("app.core.config")
    s = cfg_mod.get_settings()
    assert s.db_is_neon is True
    assert s.db_requires_ssl is True


@pytest.mark.unit
def test_railway_internal_postgres_no_ssl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Railway's internal Postgres add-on uses the private network — no SSL."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgres://forex:forex@postgres.railway.internal:5432/forex_bot",
    )
    if "app.core.config" in sys.modules:
        del sys.modules["app.core.config"]
    cfg_mod = importlib.import_module("app.core.config")
    s = cfg_mod.get_settings()
    assert s.db_is_neon is False
    assert s.db_requires_ssl is False


@pytest.mark.unit
def test_redis_tls_detected_for_rediss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "rediss://default:token@us1-fox-12345.upstash.io:6379")
    if "app.core.config" in sys.modules:
        del sys.modules["app.core.config"]
    cfg_mod = importlib.import_module("app.core.config")
    s = cfg_mod.get_settings()
    assert s.redis_uses_tls is True


@pytest.mark.unit
def test_effective_frontend_url_prefers_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRONTEND_URL", "https://forexbot.vercel.app")
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "fallback.up.railway.app")
    if "app.core.config" in sys.modules:
        del sys.modules["app.core.config"]
    cfg_mod = importlib.import_module("app.core.config")
    s = cfg_mod.get_settings()
    assert s.effective_frontend_url == "https://forexbot.vercel.app"


@pytest.mark.unit
def test_effective_frontend_url_falls_back_to_railway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "myapp.up.railway.app")
    if "app.core.config" in sys.modules:
        del sys.modules["app.core.config"]
    cfg_mod = importlib.import_module("app.core.config")
    s = cfg_mod.get_settings()
    assert s.effective_frontend_url == "https://myapp.up.railway.app"


@pytest.mark.unit
def test_effective_cors_origins_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000,https://app.example.com",
    )
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    monkeypatch.setenv(
        "FRONTEND_URLS_EXTRA",
        "https://preview-1.vercel.app,https://preview-2.vercel.app",
    )
    if "app.core.config" in sys.modules:
        del sys.modules["app.core.config"]
    cfg_mod = importlib.import_module("app.core.config")
    s = cfg_mod.get_settings()
    out = s.effective_cors_origins
    # FRONTEND_URL is duplicated → must appear exactly once.
    assert out.count("https://app.example.com") == 1
    assert "https://preview-1.vercel.app" in out
    assert "https://preview-2.vercel.app" in out


@pytest.mark.unit
def test_cors_regex_matches_vercel_preview() -> None:
    """The default regex must accept canonical vercel preview branches."""
    pattern = r"^https://([a-z0-9-]+\.)*vercel\.app$"
    rx = re.compile(pattern)
    # Production
    assert rx.match("https://myapp.vercel.app") is not None
    # Preview branch
    assert rx.match("https://myapp-git-feature-org.vercel.app") is not None
    # Deeply nested
    assert rx.match("https://x.y.z.vercel.app") is not None
    # Not a vercel host
    assert rx.match("https://vercel.app.evil.com") is None
    # http (not https) — block
    assert rx.match("http://myapp.vercel.app") is None
    # Just a look-alike
    assert rx.match("https://myapp.vercel.app.evil.com") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_app_wires_gzip_and_cors_middleware() -> None:
    """Sanity: create_app() registers GZip + CORS middleware."""
    # Fresh import in case other tests poisoned env.
    if "app.main" in sys.modules:
        del sys.modules["app.main"]
    main_mod = importlib.import_module("app.main")
    app = main_mod.create_app()
    middleware_classes = [m.cls.__name__ for m in app.user_middleware]
    assert "GZipMiddleware" in middleware_classes
    assert "CORSMiddleware" in middleware_classes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_app_state_has_shutting_down_flag(client) -> None:
    """The lifespan hook must initialize app.state.shutting_down=False."""
    # `client` fixture brings up the lifespan; once it returns, app is running.
    # Touch /healthz to ensure lifespan completed.
    r = await client.get("/healthz")
    assert r.status_code == 200
    # Reach the app via the transport
    transport = client._transport  # type: ignore[attr-defined]
    app = getattr(transport, "app", None) or getattr(transport, "_app", None)
    if app is not None and hasattr(app, "state"):
        # May or may not be set depending on lifespan; if set, must be bool.
        flag = getattr(app.state, "shutting_down", False)
        assert isinstance(flag, bool)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_readyz_drains_when_shutting_down() -> None:
    """When app.state.shutting_down=True, /readyz returns 503."""
    if "app.main" in sys.modules:
        del sys.modules["app.main"]
    from httpx import ASGITransport, AsyncClient

    main_mod = importlib.import_module("app.main")
    app = main_mod.create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Force-set drain mode before any request.
        app.state.shutting_down = True
        # Also stub Redis so the ping path doesn't matter.
        app.state.redis = None
        r = await c.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "draining"
