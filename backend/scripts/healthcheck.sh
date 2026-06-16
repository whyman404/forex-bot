#!/usr/bin/env sh
# ---------------------------------------------------------------------------
# Healthcheck script — for Docker HEALTHCHECK and Railway probes.
# Atlas Goro — exits 0 on healthy, 1 otherwise. Uses /healthz (liveness only)
# so it doesn't cascade-fail on Redis/DB hiccups (that's /readyz's job).
# ---------------------------------------------------------------------------
set -e

HOST="${HEALTHCHECK_HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
PATH_="${HEALTHCHECK_PATH:-/healthz}"
URL="http://${HOST}:${PORT}${PATH_}"

# Try curl first; fall back to python (always present in our image).
if command -v curl >/dev/null 2>&1; then
  curl -fsS --max-time 3 "$URL" >/dev/null
else
  python -c "import sys,urllib.request as u; \
    r=u.urlopen('$URL', timeout=3); \
    sys.exit(0 if r.status==200 else 1)"
fi
