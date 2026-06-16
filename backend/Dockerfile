# syntax=docker/dockerfile:1.7
#
# Forex Bot Backend — multi-stage container.
# Atlas Goro — slim, non-root, deterministic install via uv from pyproject.toml.

# ===== Stage 1: builder =====
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

# Install build deps for argon2-cffi, cryptography, asyncpg, pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast resolver from Astral)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /build

# Copy project files needed to resolve deps.
COPY pyproject.toml README.md ./
COPY app ./app

# Resolve & install runtime deps to /opt/deps (system-wide target).
RUN uv pip install --system --target /opt/deps \
        "fastapi>=0.110.0" "uvicorn[standard]>=0.29.0" "starlette>=0.36.0" \
        "sqlalchemy[asyncio]>=2.0.27" "asyncpg>=0.29.0" "alembic>=1.13.1" \
        "pydantic>=2.6.0" "pydantic-settings>=2.2.0" "email-validator>=2.1.0" \
        "python-jose[cryptography]>=3.3.0" "passlib[argon2]>=1.7.4" "argon2-cffi>=23.1.0" \
        "pyotp>=2.9.0" "cryptography>=42.0.0" "qrcode[pil]>=7.4.2" \
        "structlog>=24.1.0" \
        "opentelemetry-api>=1.23.0" "opentelemetry-sdk>=1.23.0" \
        "opentelemetry-instrumentation-fastapi>=0.44b0" \
        "opentelemetry-instrumentation-sqlalchemy>=0.44b0" \
        "opentelemetry-instrumentation-httpx>=0.44b0" \
        "opentelemetry-exporter-otlp>=1.23.0" \
        "sentry-sdk[fastapi]>=1.40.0" \
        "stripe>=8.5.0" "redis>=5.0.1" "httpx>=0.27.0" "rq>=1.16.0" \
        "python-multipart>=0.0.9" "tenacity>=8.2.3"

# ===== Stage 2: runtime =====
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/deps:/app \
    PATH=/opt/deps/bin:$PATH \
    APP_ENV=production

# Runtime libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --system --gid 1000 app && \
    useradd --system --uid 1000 --gid app --no-create-home --shell /sbin/nologin app

WORKDIR /app

# Copy installed deps and app source
COPY --from=builder /opt/deps /opt/deps
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app scripts ./scripts

USER app

EXPOSE 8000

# Healthcheck — liveness only. /readyz is for orchestrator-side readiness
# probes (Railway, k8s); /healthz/full is for ops dashboards.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD ["/bin/sh", "/app/scripts/healthcheck.sh"]

ENTRYPOINT ["/usr/bin/tini", "--"]
# $PORT is auto-injected by Railway/Render/Fly; default 8000 for plain Docker.
# Note: exec-form CMD won't expand env vars — use shell form for $PORT.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
