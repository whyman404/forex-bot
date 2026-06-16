#!/usr/bin/env bash
# ============================================================================
# scripts/deploy.sh — Production deploy with rolling restart + auto-rollback
# ============================================================================
# Owner: Hestia Kaoru
#
# Usage:
#   ./scripts/deploy.sh --env=production --host=ops@vps.forexbot.example.com
#   ./scripts/deploy.sh --env=staging    --host=ops@staging.forexbot.example.com
#   ./scripts/deploy.sh --env=production --host=... --dry-run
#   ./scripts/deploy.sh --env=production --host=... --skip-tests
#   ./scripts/deploy.sh --env=production --host=... --no-rollback
#
# Make targets:
#   make deploy-staging
#   make deploy-prod
#
# Flow:
#   1) Pre-flight (local: tests pass; remote: disk free, no firing alerts,
#                 no in-progress backups, on-call ack if production)
#   2) Tag local git as v$(date)-$(sha)
#   3) Rsync code to remote (excluding .git, node_modules, etc.)
#   4) Remote: docker compose build (multi-stage; layers cached)
#   5) Remote: alembic upgrade head (capture migration revision for rollback)
#   6) Remote: rolling restart (backend, frontend — 1 replica at a time)
#      Caddy stays up the whole time.
#   7) Smoke test (curl /healthz, /readyz, /api/v1/users/me with test token)
#   8) On success: git push tag, update /etc/forex-bot/last_good_revision
#   9) On failure: invoke rollback.sh automatically (unless --no-rollback)
# ============================================================================

set -euo pipefail
IFS=$'\n\t'

# --- Defaults ---------------------------------------------------------------
ENV=""
HOST=""
DRY_RUN=0
SKIP_TESTS=0
AUTO_ROLLBACK=1
REMOTE_DIR="/srv/forex-bot"
TIMEOUT_HEALTH=180
TIMEOUT_BUILD=900

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

log() {
    local level="$1"; shift
    printf "[%s] [%s] %s\n" "$(date -u +'%H:%M:%SZ')" "$level" "$*" >&2
}
die() { log ERROR "$*"; exit 1; }

# --- Arg parse --------------------------------------------------------------
for arg in "$@"; do
    case "$arg" in
        --env=*) ENV="${arg#*=}" ;;
        --host=*) HOST="${arg#*=}" ;;
        --dry-run) DRY_RUN=1 ;;
        --skip-tests) SKIP_TESTS=1 ;;
        --no-rollback) AUTO_ROLLBACK=0 ;;
        --remote-dir=*) REMOTE_DIR="${arg#*=}" ;;
        --help|-h)
            sed -n '2,40p' "$0"
            exit 0
            ;;
        *) die "unknown arg: $arg" ;;
    esac
done

[[ -n "$ENV" ]] || die "--env=staging|production required"
[[ -n "$HOST" ]] || die "--host=user@server required"
[[ "$ENV" =~ ^(staging|production)$ ]] || die "--env must be staging or production"

run_remote() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf "[dry-run] ssh %s -- %s\n" "$HOST" "$*"
        return 0
    fi
    ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=5 "$HOST" "$@"
}

# --- Pre-flight: local ------------------------------------------------------
log INFO "preflight: local checks"

# Working tree must be clean (no uncommitted prod changes)
if [[ "$ENV" == "production" ]] && [[ -n "$(git -C "$PROJECT_DIR" status --porcelain)" ]]; then
    die "production deploy requires a clean working tree (git status --porcelain)"
fi

# Must be on main for production
if [[ "$ENV" == "production" ]]; then
    branch=$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD)
    [[ "$branch" == "main" ]] || die "production deploy must be from main (current: $branch)"
fi

# Tests
if [[ "$SKIP_TESTS" -eq 0 ]]; then
    log INFO "running tests (backend + frontend + engine)"
    (cd "$PROJECT_DIR" && make test) || die "tests failed — aborting"
else
    log WARN "tests skipped (--skip-tests)"
fi

# --- Tag --------------------------------------------------------------------
TIMESTAMP=$(date -u +'%Y%m%d-%H%M%S')
SHA=$(git -C "$PROJECT_DIR" rev-parse --short HEAD)
TAG="$ENV-$TIMESTAMP-$SHA"
log INFO "deploy tag: $TAG"

# --- Pre-flight: remote -----------------------------------------------------
log INFO "preflight: remote checks ($HOST)"

# Disk free > 2GB
remote_disk_free=$(run_remote "df --output=avail -B1G $REMOTE_DIR | tail -1 | tr -d ' '") || die "cannot stat $REMOTE_DIR"
[[ "$remote_disk_free" -ge 2 ]] || die "remote disk free is ${remote_disk_free}GB; need >= 2GB"
log INFO "remote disk free: ${remote_disk_free}GB"

# No backup running
if run_remote "[ -f /var/lock/forex-bot-backup.lock ]" 2>/dev/null; then
    die "backup currently running — wait, then retry"
fi

# No critical alerts firing (production only)
if [[ "$ENV" == "production" ]]; then
    log INFO "checking Prometheus for firing critical alerts"
    firing=$(run_remote "curl -fsS http://prometheus:9090/api/v1/alerts 2>/dev/null | grep -c '\"state\":\"firing\".*\"severity\":\"critical\"'" || echo "0")
    if [[ "${firing:-0}" -gt 0 ]]; then
        log WARN "$firing critical alerts firing — proceed only with explicit override"
        read -r -p "type 'override' to deploy anyway: " ans
        [[ "$ans" == "override" ]] || die "aborted (alerts firing)"
    fi
fi

# Friday afternoon UTC guard (production)
if [[ "$ENV" == "production" ]]; then
    dow=$(date -u +'%u')      # 1..7 (Mon..Sun)
    hour=$(date -u +'%H')
    if [[ "$dow" == "5" ]] && [[ "$hour" -ge 14 ]]; then
        log WARN "Friday late deploy detected (UTC $(date -u +'%a %H:%M')). On-call coverage?"
        read -r -p "type 'yes' to proceed: " ans
        [[ "$ans" == "yes" ]] || die "aborted (friday guard)"
    fi
fi

# --- Build (remote) ---------------------------------------------------------
log INFO "rsyncing code to $HOST:$REMOTE_DIR"
if [[ "$DRY_RUN" -eq 1 ]]; then
    rsync_flags="--dry-run -avz"
else
    rsync_flags="-avz"
fi

rsync $rsync_flags --delete \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.venv' \
    --exclude='*.pyc' \
    --exclude='frontend/.next' \
    --exclude='backend/.pytest_cache' \
    --exclude='/data' \
    "$PROJECT_DIR/" "$HOST:$REMOTE_DIR/"

# Store current revision for rollback
PREV_REVISION=$(run_remote "cat $REMOTE_DIR/.deploy-current 2>/dev/null || echo none")
log INFO "previous deployed revision: $PREV_REVISION"

# Build images on remote
log INFO "building images on remote (timeout ${TIMEOUT_BUILD}s)"
run_remote "cd $REMOTE_DIR && timeout $TIMEOUT_BUILD docker compose \
    --env-file .env.$ENV \
    -f infra/docker-compose.yml \
    -f infra/docker-compose.prod.yml \
    build --pull --parallel" || die "build failed"

# --- Migrate ---------------------------------------------------------------
log INFO "capturing current alembic head for rollback"
PRE_ALEMBIC_HEAD=$(run_remote "cd $REMOTE_DIR && docker compose --env-file .env.$ENV exec -T backend alembic current 2>/dev/null | awk '{print \$1}' | head -1" || echo "")
log INFO "current alembic head: ${PRE_ALEMBIC_HEAD:-(none)}"

log INFO "running migrations (alembic upgrade head)"
run_remote "cd $REMOTE_DIR && docker compose --env-file .env.$ENV \
    -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
    run --rm backend alembic upgrade head" || die "migration failed"

# --- Rolling restart -------------------------------------------------------
log INFO "rolling restart: backend"
run_remote "cd $REMOTE_DIR && docker compose --env-file .env.$ENV \
    -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
    up -d --no-deps --scale backend=2 --wait --wait-timeout 120 backend" \
    || die "backend rolling restart failed"

log INFO "rolling restart: frontend"
run_remote "cd $REMOTE_DIR && docker compose --env-file .env.$ENV \
    -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
    up -d --no-deps --scale frontend=2 --wait --wait-timeout 120 frontend" \
    || die "frontend rolling restart failed"

log INFO "restart: trading-engine (singleton, brief pause expected)"
run_remote "cd $REMOTE_DIR && docker compose --env-file .env.$ENV \
    -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
    up -d --no-deps --wait --wait-timeout 60 trading-engine"

# --- Smoke test ------------------------------------------------------------
log INFO "smoke tests"
SMOKE_OK=1
run_remote "$REMOTE_DIR/scripts/smoke.sh --remote --base-url https://api.${DOMAIN:-forexbot.example.com}" \
    || SMOKE_OK=0

if [[ "$SMOKE_OK" -ne 1 ]]; then
    log ERROR "smoke tests FAILED"
    if [[ "$AUTO_ROLLBACK" -eq 1 ]]; then
        log ERROR "auto-rollback engaged → previous revision $PREV_REVISION"
        "$SCRIPT_DIR/rollback.sh" --env="$ENV" --host="$HOST" \
            --target-revision="$PREV_REVISION" \
            --alembic-head="$PRE_ALEMBIC_HEAD" \
            || die "rollback failed (manual intervention required)"
        die "deploy rolled back; investigate before retrying"
    else
        die "smoke failed; --no-rollback: leaving system in current state"
    fi
fi

# --- Success bookkeeping ----------------------------------------------------
log INFO "deploy succeeded — bookkeeping"

# Tag git
if [[ "$DRY_RUN" -ne 1 ]]; then
    git -C "$PROJECT_DIR" tag -a "$TAG" -m "Deploy $ENV $TAG (sha=$SHA)"
    log INFO "git tag created: $TAG (push manually with: git push origin $TAG)"
fi

# Record successful revision on remote
run_remote "echo $SHA > $REMOTE_DIR/.deploy-current && echo '$(date -u +'%Y-%m-%dT%H:%M:%SZ')' >> $REMOTE_DIR/.deploy-log && echo '$TAG' >> $REMOTE_DIR/.deploy-log"

# Notify
if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    curl -fsS -X POST -H 'Content-Type: application/json' \
        --data "{\"text\":\":rocket: forex-bot deployed to $ENV — tag=$TAG sha=$SHA\"}" \
        "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
fi

log INFO "DONE — $ENV is now at $TAG"
exit 0
