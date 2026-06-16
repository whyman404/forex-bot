    # syntax=docker/dockerfile:1.7
    # ---------------------------------------------------------------------------
    # Stage 1: builder — install Python deps with uv
    # ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Build deps for numpy / pandas / vectorbt wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager).
COPY --from=ghcr.io/astral-sh/uv:0.4.20 /uv /usr/local/bin/uv

WORKDIR /app

# Copy only manifest first → caches the dep layer.
COPY pyproject.toml ./
COPY README.md ./

# We add fastapi + uvicorn + rq + redis on top of the trading-engine deps.
# These are runtime needs for the server / worker.
RUN uv pip install --system --no-cache \
        "fastapi>=0.111.0" \
        "uvicorn[standard]>=0.30.0" \
        "rq>=1.16.0" \
        "redis>=5.0.0" \
        "psycopg[binary]>=3.2.0"

# Install the package's pinned deps.
RUN uv pip install --system --no-cache \
    "pandas>=2.2.0" \
    "numpy>=1.26.0,<2.0.0" \
    "scipy>=1.13.0" \
    "ta>=0.11.0" \
    "ccxt>=4.3.0" \
    "python-dotenv>=1.0.1" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.3.0" \
    "pyyaml>=6.0.1" \
    "structlog>=24.1.0" \
    "httpx>=0.27.0" \
    "tenacity>=8.4.0"

# vectorbt is optional at install (heavy). Skip if it fails — runner falls back.
RUN uv pip install --system --no-cache "vectorbt>=0.27.0" || \
    echo "vectorbt install skipped — runner has a fallback"

# ---------------------------------------------------------------------------
# Stage 2: runtime — copy site-packages + app code
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    EQUITY_CURVE_DIR=/var/data/equity-curves \
    REDIS_URL=redis://redis:6379/0

# Slim runtime deps — libgomp for numpy/scipy/vectorbt.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder.
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Non-root user for safety.
RUN useradd --create-home --shell /bin/bash quant && \
    mkdir -p /var/data/equity-curves && \
    chown -R quant:quant /var/data

WORKDIR /app

# App code — copy after deps for better layer caching.
COPY --chown=quant:quant . /app

USER quant

EXPOSE 8500

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8500/healthz || exit 1

# Two run modes:
#   server  -> FastAPI (default)
#   worker  -> RQ worker on the "backtest" queue
#
# Override at run time:
#   docker run ... <image> server
#   docker run ... <image> worker
COPY --chown=quant:quant <<'EOF' /app/entrypoint.sh
#!/usr/bin/env bash
set -euo pipefail
MODE="${1:-server}"
case "$MODE" in
  server)
    exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8500}" \
        --workers "${UVICORN_WORKERS:-1}"
    ;;
  worker)
    exec rq worker backtest --url "${REDIS_URL}" --with-scheduler
    ;;
  *)
    echo "Unknown mode: $MODE (expected: server | worker)" >&2
    exit 2
    ;;
esac
EOF

USER root
RUN chmod +x /app/entrypoint.sh && chown quant:quant /app/entrypoint.sh
USER quant

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["server"]
