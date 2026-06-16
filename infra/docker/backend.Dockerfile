# syntax=docker/dockerfile:1.7
# ============================================================================
# infra/docker/backend.Dockerfile — alt Dockerfile mirroring backend/Dockerfile
# ============================================================================
# Atlas already shipped backend/Dockerfile. This copy lives under infra/docker/
# for teams (e.g. CI) that prefer all Dockerfiles in one place. Keep in sync
# with backend/Dockerfile via lint: `diff backend/Dockerfile infra/docker/backend.Dockerfile`.
# ============================================================================

# ===== Stage 1: builder =====
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /build

COPY backend/pyproject.toml ./
COPY backend/app ./app

# Lock + install into /opt/deps so the runtime stage stays slim.
RUN uv pip install --system --target /opt/deps \
        fastapi "uvicorn[standard]" "gunicorn>=22.0" \
        "sqlalchemy[asyncio]" asyncpg alembic \
        pydantic pydantic-settings email-validator \
        "python-jose[cryptography]" "passlib[argon2]" argon2-cffi pyotp cryptography \
        structlog \
        opentelemetry-api opentelemetry-sdk \
        opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy \
        opentelemetry-instrumentation-httpx opentelemetry-exporter-otlp \
        "sentry-sdk[fastapi]" \
        prometheus-fastapi-instrumentator \
        stripe redis httpx python-multipart tenacity

# ===== Stage 2: runtime =====
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/deps:/app \
    PATH=/opt/deps/bin:$PATH \
    APP_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        ca-certificates \
        tini \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 app && \
    useradd --system --uid 1000 --gid app --no-create-home --shell /sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/deps /opt/deps
COPY --chown=app:app backend/app ./app
COPY --chown=app:app backend/alembic.ini ./alembic.ini

# Tmp dir for prometheus multiproc + uvicorn workers.
RUN mkdir -p /tmp/prom && chown app:app /tmp/prom

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "app.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--max-requests", "10000", \
     "--max-requests-jitter", "1000"]
