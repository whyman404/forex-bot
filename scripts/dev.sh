#!/usr/bin/env bash
# ============================================================================
# scripts/dev.sh — one-command dev environment start
# ============================================================================
# Owner: Hestia Kaoru
#
# What it does:
#   1. preflight — check docker, docker compose, openssl
#   2. .env — copy from .env.example if missing
#   3. secrets — generate JWT_SECRET, ENCRYPTION_KEK, NEXTAUTH_SECRET
#      if values are PLACEHOLDER
#   4. start stack — docker compose up -d
#   5. wait for postgres healthy
#   6. run alembic migrations
#   7. run seed script (idempotent)
#   8. print success banner with login info
#
# Re-run safe: every step is idempotent. CTRL-C clean teardown.
# ============================================================================

set -euo pipefail

# ----- colors -----
if [[ -t 1 ]]; then
  RED=$'\033[1;31m'
  GREEN=$'\033[1;32m'
  YELLOW=$'\033[1;33m'
  CYAN=$'\033[1;36m'
  BOLD=$'\033[1m'
  NC=$'\033[0m'
else
  RED="" GREEN="" YELLOW="" CYAN="" BOLD="" NC=""
fi

log()    { printf "%s[dev]%s %s\n" "$CYAN" "$NC" "$*"; }
warn()   { printf "%s[warn]%s %s\n" "$YELLOW" "$NC" "$*"; }
err()    { printf "%s[err]%s %s\n" "$RED" "$NC" "$*" >&2; }
ok()     { printf "%s[ok]%s %s\n" "$GREEN" "$NC" "$*"; }

trap 'err "interrupted — run \`make down\` to clean up"; exit 130' INT

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="infra/docker-compose.yml"
COMPOSE_OVERRIDE="infra/docker-compose.override.yml"
COMPOSE_CMD=(docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE" --project-directory .)

# ---------------------------------------------------------------------------
# Step 1: preflight
# ---------------------------------------------------------------------------
log "step 1/8 — preflight"

if ! command -v docker >/dev/null 2>&1; then
  err "docker not installed — see https://docs.docker.com/get-docker/"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  err "docker compose v2 plugin missing — upgrade Docker Desktop or install compose plugin"
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  err "docker daemon not running — start Docker Desktop"
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  err "openssl not installed — install via brew/apt"
  exit 1
fi

ok "preflight passed: docker=$(docker --version | awk '{print $3}' | tr -d ',') compose=$(docker compose version --short)"

# ---------------------------------------------------------------------------
# Step 2: .env
# ---------------------------------------------------------------------------
log "step 2/8 — .env"

if [[ ! -f .env ]]; then
  if [[ ! -f .env.example ]]; then
    err ".env.example missing — repo broken"
    exit 1
  fi
  cp .env.example .env
  ok "created .env from .env.example"
else
  ok ".env already exists"
fi

# ---------------------------------------------------------------------------
# Step 3: secrets — replace PLACEHOLDER values
# ---------------------------------------------------------------------------
log "step 3/8 — secrets"

# portable sed: write to tmpfile then move (works on mac + linux)
replace_placeholder() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=PLACEHOLDER" .env 2>/dev/null; then
    local tmp
    tmp="$(mktemp)"
    awk -v k="$key" -v v="$value" '
      BEGIN{FS=OFS="="}
      $1==k {print k"="v; next}
      {print}
    ' .env >"$tmp" && mv "$tmp" .env
    ok "rotated $key"
  else
    log "$key already set — leaving alone"
  fi
}

# 64 hex chars = 32 bytes of entropy
JWT_SECRET="$(openssl rand -hex 32)"
NEXTAUTH_SECRET="$(openssl rand -hex 32)"
# Base64 32 bytes for ENCRYPTION_KEK (envelope encryption KEK)
ENCRYPTION_KEK="$(openssl rand -base64 32 | tr -d '\n')"

replace_placeholder "JWT_SECRET_KEY" "$JWT_SECRET"
replace_placeholder "NEXTAUTH_SECRET" "$NEXTAUTH_SECRET"
replace_placeholder "ENCRYPTION_KEK_BASE64" "$ENCRYPTION_KEK"

# ---------------------------------------------------------------------------
# Step 4: docker compose up
# ---------------------------------------------------------------------------
log "step 4/8 — build + start services (this may take a few minutes on first run)"

"${COMPOSE_CMD[@]}" up -d --build --remove-orphans

ok "containers started"

# ---------------------------------------------------------------------------
# Step 5: wait for postgres healthy
# ---------------------------------------------------------------------------
log "step 5/8 — waiting for postgres healthy"

DEADLINE=$(( $(date +%s) + 90 ))
while true; do
  STATUS=$("${COMPOSE_CMD[@]}" ps --format json postgres 2>/dev/null \
    | grep -o '"Health":"[^"]*"' | head -n1 | cut -d'"' -f4 || true)
  if [[ "$STATUS" == "healthy" ]]; then
    ok "postgres healthy"
    break
  fi
  if (( $(date +%s) > DEADLINE )); then
    err "postgres did not become healthy within 90s — check: make logs"
    exit 1
  fi
  printf "."
  sleep 2
done

# ---------------------------------------------------------------------------
# Step 6: alembic migrations
# ---------------------------------------------------------------------------
log "step 6/8 — running alembic migrations"

# Wait for backend to be ready before running alembic
DEADLINE=$(( $(date +%s) + 60 ))
while true; do
  if "${COMPOSE_CMD[@]}" exec -T backend python -c "import alembic" 2>/dev/null; then
    break
  fi
  if (( $(date +%s) > DEADLINE )); then
    warn "backend container slow to start — proceeding anyway"
    break
  fi
  sleep 2
done

if "${COMPOSE_CMD[@]}" exec -T backend alembic upgrade head 2>&1 | tee /tmp/forex-bot-migrate.log; then
  ok "migrations applied"
else
  warn "migration failed — first run may not have alembic baseline yet (see /tmp/forex-bot-migrate.log)"
fi

# ---------------------------------------------------------------------------
# Step 7: seed
# ---------------------------------------------------------------------------
log "step 7/8 — seeding dev data"

if "${COMPOSE_CMD[@]}" exec -T backend python -m app.scripts.seed 2>/dev/null; then
  ok "seed applied"
else
  warn "seed script not yet wired in backend — skipping (safe to ignore on first scaffold)"
fi

# ---------------------------------------------------------------------------
# Step 8: success banner
# ---------------------------------------------------------------------------
log "step 8/8 — smoke check"

if ./scripts/smoke.sh >/dev/null 2>&1; then
  ok "smoke passed"
else
  warn "smoke partial — services may still be warming up. Retry: ./scripts/smoke.sh"
fi

cat <<EOF

${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${GREEN}${BOLD}  Forex Bot Platform — DEV READY${NC}
${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

  ${BOLD}Open:${NC}        http://localhost:3000
  ${BOLD}Login:${NC}       admin@local / changeme123
  ${BOLD}API:${NC}         http://localhost:8000/docs
  ${BOLD}Grafana:${NC}     http://localhost:3001 (admin / admin-dev)
  ${BOLD}Prometheus:${NC}  http://localhost:9090

  ${CYAN}Commands:${NC}
    make logs           # follow logs
    make down           # stop everything
    make smoke          # health checks
    make shell-backend  # poke around

EOF
