#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Railway post-deploy script — runs migrations and seeds.
# Atlas Goro — idempotent. Safe to run on every deploy.
#
# Set as the Railway "release" command, or invoke manually:
#   railway run bash scripts/railway_post_deploy.sh
# ---------------------------------------------------------------------------
set -euo pipefail

log() { printf '[post-deploy] %s\n' "$*" >&2; }

log "starting post-deploy at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 1. Migrations — alembic is idempotent (upgrade head is a no-op when current).
log "running alembic upgrade head"
alembic upgrade head

# 2. Seed admin (idempotent UPSERT).
log "seeding admin user"
python -m scripts.seed_admin || {
  log "WARN: seed_admin failed — continuing (likely already exists)"
}

# 3. Seed sample backtest (first deploy only — script is idempotent).
log "seeding sample backtest (idempotent)"
python -m scripts.seed_sample_backtest || {
  log "WARN: seed_sample_backtest failed — non-fatal"
}

# 4. Print first-user credentials banner.
cat <<'BANNER' >&2

============================================================
  First user provisioned:
    email:    admin@local
    password: changeme123

  *** CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN ***
============================================================
BANNER

log "post-deploy complete"
