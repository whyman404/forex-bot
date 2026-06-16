# syntax=docker/dockerfile:1.7
# ============================================================================
# infra/docker/trading-engine.Dockerfile
# ============================================================================
# Trading engine image. Includes:
#   - paper trading (works on Linux)
#   - backtest runner (vectorbt / backtrader / ccxt)
# Does NOT include `MetaTrader5` package (Windows-only) — that runs on the
# Windows VPS via mt5-supervisor.py.
# Build context: ./trading-engine
# ============================================================================

# ===== Stage 1: builder =====
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        # numpy / scipy / pandas C bits
        gfortran \
        libopenblas-dev \
        # TA-Lib C library is heavy; we use pure-Python `ta` instead.
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /build

COPY pyproject.toml ./
# Copy source so hatchling can resolve packages list.
COPY strategies ./strategies
COPY backtest ./backtest
COPY broker ./broker
COPY risk ./risk
COPY data ./data
COPY configs ./configs

# Install runtime deps into /opt/deps. We pin numpy <2 to satisfy vectorbt.
RUN uv pip install --system --target /opt/deps \
        "vectorbt>=0.27.0" \
        "ccxt>=4.3.0" \
        "pandas>=2.2.0" \
        "numpy>=1.26.0,<2.0.0" \
        "scipy>=1.13.0" \
        "ta>=0.11.0" \
        "python-dotenv>=1.0.1" \
        "pydantic>=2.7.0" "pydantic-settings>=2.3.0" \
        "pyyaml>=6.0.1" \
        "structlog>=24.1.0" \
        "httpx>=0.27.0" "tenacity>=8.4.0" \
        "websockets>=12.0" \
        "asyncpg>=0.29.0" \
        "redis>=5.0.1" \
        "apscheduler>=3.10.4" \
        "prometheus-client>=0.20.0" \
        "opentelemetry-api>=1.23.0" \
        "opentelemetry-sdk>=1.23.0" \
        "opentelemetry-exporter-otlp>=1.23.0"

# ===== Stage 2: runtime =====
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/deps:/app \
    PATH=/opt/deps/bin:$PATH \
    APP_ENV=production \
    MODE=paper

# Slim runtime libs only.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopenblas0 \
        libgomp1 \
        ca-certificates \
        tini \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 engine && \
    useradd --system --uid 1000 --gid engine --no-create-home --shell /sbin/nologin engine

WORKDIR /app

COPY --from=builder /opt/deps /opt/deps
COPY --chown=engine:engine . ./

# data/ is used for cached OHLCV. Make sure it is writable.
RUN mkdir -p /app/data && chown -R engine:engine /app/data

USER engine

# Engine exposes a prom metrics endpoint on 9100.
EXPOSE 9100

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -fsS http://127.0.0.1:9100/metrics > /dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# Default: run paper trading loop. Override CMD for backtest jobs.
CMD ["python", "-m", "broker.paper_runner"]
