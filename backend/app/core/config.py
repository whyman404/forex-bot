"""Application settings (Pydantic Settings, env-driven).

Atlas Goro — one source of truth for configuration.
Settings are eagerly validated at import time → fail fast on misconfig.

Round 4 (Railway-readiness) additions:
- `PORT` is read from env (Railway auto-injects).
- `RAILWAY_PUBLIC_DOMAIN` is honored as a `frontend_url` fallback for
  Stripe redirects when the env var is missing (rare, but useful for the
  first cold-deploy before you wire the Vercel domain).
- `frontend_urls_extra` accepts CSV preview-deploy domains.
- `database_url` is normalized to `postgresql+asyncpg://...` so callers
  needn't care about Railway's `postgres://` scheme.

References:
- Railway environment variables — https://docs.railway.app/reference/variables
  (PORT, RAILWAY_PUBLIC_DOMAIN, RAILWAY_PRIVATE_DOMAIN auto-injected).
- asyncpg DSN handling — accepts `postgresql://` only; we normalize.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse, urlunparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_database_url(raw: str) -> str:
    """Normalize a Postgres DSN into `postgresql+asyncpg://...`.

    Handles:
      - Railway's `postgres://...`
      - Plain `postgresql://...`
      - Existing `postgresql+asyncpg://...` (no-op)
      - Stray `+psycopg2` / `+psycopg` drivers (replace → asyncpg)
    Preserves user, password, host, port, path, and query string.
    """
    if not raw:
        return raw
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()

    if scheme in {"postgres", "postgresql"}:
        new_scheme = "postgresql+asyncpg"
    elif scheme.startswith("postgresql+"):
        new_scheme = "postgresql+asyncpg"
    else:
        return raw  # not a postgres URL — leave alone (tests may pass sqlite, etc.)

    return urlunparse(parsed._replace(scheme=new_scheme))


class Settings(BaseSettings):
    """All app settings. Read once at startup, then cached."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== App =====
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "forex-bot-backend"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    debug: bool = False

    # ===== Server =====
    host: str = "0.0.0.0"  # noqa: S104 — bind-all is expected for containers
    port: int = 8000
    # CORS — primary list, single FRONTEND_URL, csv extras for preview deploys.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    frontend_urls_extra: list[str] = Field(default_factory=list)
    # Regex pattern for preview deploys (e.g. https://my-app-git-foo-org.vercel.app).
    cors_allow_origin_regex: str = r"^https://([a-z0-9-]+\.)*vercel\.app$"

    # ===== Database =====
    # NOTE: typed as `str` (not PostgresDsn) because Railway emits `postgres://`
    # which Pydantic's PostgresDsn rejects. We normalize in the validator below.
    database_url: str
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle_seconds: int = 300

    # ===== Redis =====
    # Typed as `str` to accept both `redis://` (Railway) and `rediss://` (Upstash).
    redis_url: str
    redis_rate_limit_db: int = 1
    redis_session_db: int = 2
    redis_socket_timeout_seconds: float = 5.0

    # ===== JWT =====
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_min: int = 15
    jwt_refresh_token_ttl_days: int = 7
    jwt_issuer: str = "forex-bot"
    jwt_audience: str = "forex-bot-api"

    # ===== Envelope encryption (ADR-005) =====
    encryption_kek_base64: str = Field(min_length=44, description="base64(32-byte KEK)")
    encryption_key_version: int = 1

    # ===== Stripe =====
    stripe_api_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro_monthly: str = ""
    stripe_price_pro_yearly: str = ""
    stripe_price_lifetime: str = ""
    # Back-compat aliases (older code paths read these names)
    stripe_price_id_pro_monthly: str = ""
    stripe_price_id_pro_yearly: str = ""
    stripe_trial_days: int = 14

    # ===== Observability =====
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "forex-bot-backend"
    otel_traces_sampler: str = "parentbased_traceidratio"
    otel_traces_sampler_arg: float = 0.1

    # ===== Email =====
    email_provider: Literal["console", "smtp", "resend"] = "console"
    email_from: str = "noreply@forexbot.local"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@forexbot.local"
    smtp_starttls: bool = True
    resend_api_key: str = ""
    email_queue_name: str = "email_queue"

    # ===== Rate limit (per-tier rpm) =====
    rate_limit_default_per_min: int = 60
    rate_limit_auth_per_min: int = 10
    rate_limit_burst: int = 20
    rate_limit_free_per_min: int = 30
    rate_limit_pro_per_min: int = 120
    rate_limit_pro_yearly_per_min: int = 240
    rate_limit_lifetime_per_min: int = 240

    # ===== TOTP =====
    totp_issuer: str = "ForexBot"

    # ===== External services =====
    mt5_bridge_url: str = "http://mt5-bridge-stub:9100"
    trading_engine_url: str = "http://trading-engine:8200"
    internal_api_secret: str = ""
    # CSV of CIDR / prefixes the internal endpoints prefer (HMAC is still primary).
    internal_trusted_proxy_cidrs: list[str] = Field(default_factory=list)

    # ===== TradingView integration (Round 5) =====
    # Kill switch — set false to fail-fast all /tv/* endpoints with 503 without
    # touching the engine. Useful when TV upstream is having an outage and we
    # want the UI to show a friendly degraded state.
    tv_enabled: bool = True
    # Per-user rate limit for the heavy `/tv/preview` endpoint (in addition to
    # the per-tier limit). 10rpm matches frontend's `useTVPreview` cadence.
    tv_preview_rate_limit_per_min: int = 10
    # Symbol catalog cache TTL — the catalog is updated rarely; 1h is generous.
    tv_catalog_cache_ttl_sec: int = 3600

    # ===== URLs (used in email templates + Stripe redirects) =====
    frontend_url: str = "http://localhost:3000"
    backend_public_url: str = "http://localhost:8000"

    # ===== Railway-specific (auto-injected) =====
    railway_public_domain: str = ""
    railway_service_name: str = ""
    railway_environment_name: str = ""

    # ===== Lifecycle =====
    run_migrations_on_boot: bool = False
    shutdown_grace_seconds: float = 10.0

    # ===== Live-trading gate thresholds =====
    live_min_account_size_forex_cents: int = 50000   # USD $500
    live_min_account_size_crypto_cents: int = 20000  # USD $200
    live_min_paper_days: int = 14
    live_min_paper_trades: int = 10
    live_min_profit_factor: float = 1.3
    live_max_drawdown_pct: float = 25.0

    # -----------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            if v.startswith("["):
                # JSON-ish list will be parsed by Pydantic
                return v  # type: ignore[return-value]
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("frontend_urls_extra", mode="before")
    @classmethod
    def _split_extra(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [u.strip() for u in v.split(",") if u.strip()]
        return v

    @field_validator("internal_trusted_proxy_cidrs", mode="before")
    @classmethod
    def _split_cidrs(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [c.strip() for c in v.split(",") if c.strip()]
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_db(cls, v: str) -> str:
        return _normalize_database_url(v) if isinstance(v, str) else v

    # -----------------------------------------------------------------
    # Derived properties
    # -----------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def effective_frontend_url(self) -> str:
        """Prefer explicit FRONTEND_URL; fall back to RAILWAY_PUBLIC_DOMAIN.

        Stripe / email redirects must always resolve to *something*, even on
        the first cold-deploy before you wire your Vercel domain.
        """
        if self.frontend_url and self.frontend_url != "http://localhost:3000":
            return self.frontend_url
        if self.railway_public_domain:
            return f"https://{self.railway_public_domain}"
        return self.frontend_url

    @property
    def effective_cors_origins(self) -> list[str]:
        """Union of cors_origins + frontend_url + extras (deduped)."""
        seen: set[str] = set()
        out: list[str] = []
        for origin in [*self.cors_origins, self.frontend_url, *self.frontend_urls_extra]:
            if origin and origin not in seen:
                seen.add(origin)
                out.append(origin)
        return out

    @property
    def db_is_neon(self) -> bool:
        """Detect Neon (managed Postgres) so SSL gets auto-enabled."""
        try:
            host = urlparse(self.database_url).hostname or ""
        except Exception:  # noqa: BLE001
            return False
        return host.endswith(".neon.tech")

    @property
    def db_requires_ssl(self) -> bool:
        """True if URL explicitly asks for SSL or host is Neon."""
        url = self.database_url or ""
        ql = url.lower()
        return (
            self.db_is_neon
            or "sslmode=require" in ql
            or "sslmode=verify-full" in ql
            or "sslmode=verify-ca" in ql
            or "ssl=true" in ql
        )

    @property
    def redis_uses_tls(self) -> bool:
        """True if rediss:// (TLS, used by Upstash)."""
        return (self.redis_url or "").lower().startswith("rediss://")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance — call from anywhere.

    Reading PORT directly from env here (in addition to Pydantic auto-binding)
    is intentional: some PaaS providers (Railway, Render, Fly) inject PORT
    *after* container boot, so we re-read on cache-miss.
    """
    env_port = os.environ.get("PORT")
    if env_port and "PORT" not in os.environ.get("_PORT_FORCED", ""):
        # Ensure Pydantic sees it.
        os.environ["PORT"] = env_port
    return Settings()  # type: ignore[call-arg]
