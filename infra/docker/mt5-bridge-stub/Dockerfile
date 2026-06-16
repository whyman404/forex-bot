# syntax=docker/dockerfile:1.7
# ============================================================================
# mt5-bridge-stub Dockerfile
# ============================================================================
# Tiny Python HTTP server returning canned MT5 responses.
# In production, this image is replaced by the real bridge running on a
# Windows VPS (see docs/deployment/deployment-architecture.md).
# ============================================================================

FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BRIDGE_PORT=8500 \
    STUB_MODE=canned

# Non-root user
RUN addgroup -S -g 1000 stub && \
    adduser -S -u 1000 -G stub stub

# wget for healthcheck
RUN apk add --no-cache wget

WORKDIR /app
COPY server.py /app/server.py

USER stub
EXPOSE 8500

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=10s \
  CMD wget --quiet --spider http://127.0.0.1:8500/healthz || exit 1

CMD ["python", "-u", "/app/server.py"]
