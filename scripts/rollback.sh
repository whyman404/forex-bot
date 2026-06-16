#!/usr/bin/env bash
# ============================================================================
# scripts/rollback.sh — Revert to last known good
# ============================================================================
# Owner: Hestia Kaoru
#
# Usage:
#   ./scripts/rollback.sh --env=production --host=ops@vps --target-revision=<sha-or-tag>
#   ./scripts/rollback.sh --env=production --host=ops@vps
#       (no target: uses /srv/forex-bot/.deploy-current → previous in .deploy-log)
#   ./scripts/rollback.sh --env=production --host=ops@vps --alembic-head=<rev>
#       (also downgrades DB if migration was applied during failed deploy)
#
# Philosophy: rollback first, debug second. If we can't rollback the entire
# app and DB to the previous state, the system is not production-ready.
# ============================================================================

set -euo pipefail
IFS=$'\n\t'

ENV=""
HOST=""
TARGET_REVISION=""
ALEMBIC_HEAD=""
REMOTE_DIR="/srv/forex-bot"
SKIP_DB=0

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

log() { printf "[%s] [%s] %s\n" "$(date -u +'%H:%M:%SZ')" "$1" "${*:2}" >&2; }
die() { log ERROR "$*"; exit 1; }

for arg in "$@"; do
    case "$arg" in
        --env=*) ENV="${arg#*=}" ;;
        --host=*) HOST="${arg#*=}" ;;
        --target-revision=*) TARGET_REVISION="${arg#*=}" ;;
        --alembic-head=*) ALEMBIC_HEAD="${arg#*=}" ;;
        --remote-dir=*) REMOTE_DIR="${arg#*=}" ;;
        --skip-db) SKIP_DB=1 ;;
        --help|-h) sed -n '2,25p' "$0"; exit 0 ;;
        *) die "unknown arg: $arg" ;;
    esac
done

[[ -n "$ENV" && -n "$HOST" ]] || die "--env and --host required"

run_remote() {
    ssh -o ServerAliveInterval=30 "$HOST" "$@"
}

# --- Determine target ------------------------------------------------------
if [[ -z "$TARGET_REVISION" ]]; then
    log INFO "no target revision; looking up previous in $REMOTE_DIR/.deploy-log"
    TARGET_REVISION=$(run_remote "tail -4 $REMOTE_DIR/.deploy-log 2>/dev/null | grep -v none | head -2 | tail -1" || echo "")
    [[ -n "$TARGET_REVISION" ]] || die "could not determine previous revision; pass --target-revision=<sha-or-tag>"
fi

log INFO "rolling back $ENV to revision: $TARGET_REVISION"

# --- Checkout target locally then rsync ------------------------------------
log INFO "checking out target locally"
ORIG_HEAD=$(git -C "$PROJECT_DIR" rev-parse HEAD)

# Stash any local changes (rollback should not lose them)
if [[ -n "$(git -C "$PROJECT_DIR" status --porcelain)" ]]; then
    STASH_NAME="rollback-stash-$(date +%s)"
    git -C "$PROJECT_DIR" stash push -u -m "$STASH_NAME"
    log WARN "local changes stashed as: $STASH_NAME"
fi

git -C "$PROJECT_DIR" fetch --tags
git -C "$PROJECT_DIR" checkout "$TARGET_REVISION"

# --- Rsync target to remote ------------------------------------------------
log INFO "rsyncing $TARGET_REVISION to $HOST:$REMOTE_DIR"
rsync -avz --delete \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.venv' \
    --exclude='*.pyc' \
    --exclude='frontend/.next' \
    --exclude='/data' \
    "$PROJECT_DIR/" "$HOST:$REMOTE_DIR/"

# --- Build target images on remote -----------------------------------------
log INFO "rebuilding images for rollback target"
run_remote "cd $REMOTE_DIR && docker compose --env-file .env.$ENV \
    -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
    build --pull --parallel" || die "build failed during rollback"

# --- Optionally downgrade alembic ------------------------------------------
if [[ "$SKIP_DB" -ne 1 ]] && [[ -n "$ALEMBIC_HEAD" ]]; then
    log WARN "downgrading alembic to $ALEMBIC_HEAD"
    run_remote "cd $REMOTE_DIR && docker compose --env-file .env.$ENV \
        -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
        run --rm backend alembic downgrade $ALEMBIC_HEAD" \
        || die "alembic downgrade failed — DB may be in inconsistent state, restore from backup"
fi

# --- Rolling restart with target images ------------------------------------
log INFO "restarting services with rollback images"
run_remote "cd $REMOTE_DIR && docker compose --env-file .env.$ENV \
    -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
    up -d --wait --wait-timeout 180 backend frontend trading-engine" \
    || die "service restart failed during rollback"

# --- Smoke ------------------------------------------------------------------
log INFO "post-rollback smoke"
run_remote "$REMOTE_DIR/scripts/smoke.sh --remote --base-url https://api.${DOMAIN:-forexbot.example.com}" \
    || log ERROR "smoke after rollback failed — escalate"

# --- Restore local HEAD ----------------------------------------------------
git -C "$PROJECT_DIR" checkout "$ORIG_HEAD" 2>/dev/null \
    || log WARN "could not restore local HEAD ($ORIG_HEAD)"

# --- Record ----------------------------------------------------------------
run_remote "echo 'ROLLBACK-$(date -u +%Y%m%dT%H%M%SZ) to $TARGET_REVISION' >> $REMOTE_DIR/.deploy-log"

if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    curl -fsS -X POST -H 'Content-Type: application/json' \
        --data "{\"text\":\":rewind: forex-bot ROLLED BACK to $TARGET_REVISION on $ENV\"}" \
        "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
fi

log INFO "rollback complete → $TARGET_REVISION"
log INFO "now write a blameless postmortem (template: docs/deployment/postmortem-template.md)"
exit 0
