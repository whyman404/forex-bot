#!/usr/bin/env bash
# ============================================================================
# infra/backup/verify.sh — Random backup verification (DR drill in a box)
# ============================================================================
# Owner: Hestia Kaoru
# Schedule via host cron:  0 4 * * 0  /srv/forex-bot/infra/backup/verify.sh
#
# Picks a random backup from R2, downloads, restores into a throwaway DB,
# runs schema + row-count sanity checks, then drops the throwaway DB.
#
# Goal: detect "backups silently corrupted for 3 months" before we ever
# need to restore for real (a classic ops failure mode — Charity Majors).
#
# Env: same as backup.sh (sources /etc/forex-bot/backup.env).
# Exit: 0 ok, non-zero = alert.
# ============================================================================

set -euo pipefail
IFS=$'\n\t'

CONFIG_FILE="${BACKUP_ENV_FILE:-/etc/forex-bot/backup.env}"
TMP_DIR="$(mktemp -d -t forex-bot-verify-XXXXXX)"
THROWAWAY_DB="forex_bot_verify_$(date +%s)_$$"
trap 'cleanup' EXIT INT TERM

log() { echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [$1] ${*:2}" >&2; }
die() { log ERROR "$*"; notify "ERROR" "$*"; exit 1; }

notify() {
    local level="$1" msg="$2"
    [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && return 0
    local color="good"
    [[ "$level" == "ERROR" ]] && color="danger"
    [[ "$level" == "WARN" ]] && color="warning"
    curl -fsS -X POST -H 'Content-Type: application/json' \
        --data "{\"attachments\":[{\"color\":\"$color\",\"title\":\"forex-bot backup verify: $level\",\"text\":\"$msg\"}]}" \
        "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
}

cleanup() {
    local code=$?
    if [[ -n "${PGPASSWORD:-}" ]] && [[ -n "$THROWAWAY_DB" ]]; then
        psql --host="${POSTGRES_HOST:-localhost}" \
             --port="${POSTGRES_PORT:-5432}" \
             --username="$POSTGRES_USER" --dbname="postgres" \
             --command="DROP DATABASE IF EXISTS \"$THROWAWAY_DB\"" \
             >/dev/null 2>&1 || true
    fi
    rm -rf "$TMP_DIR"
    exit "$code"
}

# --- Config ------------------------------------------------------------------
[[ -r "$CONFIG_FILE" ]] || die "config not readable: $CONFIG_FILE"
# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${R2_BUCKET:?}"; : "${R2_ENDPOINT:?}"
: "${R2_ACCESS_KEY:?}"; : "${R2_SECRET_KEY:?}"
: "${POSTGRES_USER:?}"; : "${POSTGRES_PASSWORD:?}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_KEY"
export AWS_DEFAULT_REGION="auto"

# --- Pick a random backup ----------------------------------------------------
log INFO "selecting random backup from R2..."

# Weight: 70% daily, 20% weekly, 10% monthly — daily backups are most exercised
ROLL=$((RANDOM % 100))
if [[ "$ROLL" -lt 70 ]]; then
    TIER="daily"
elif [[ "$ROLL" -lt 90 ]]; then
    TIER="weekly"
else
    TIER="monthly"
fi

# Fetch listing and pick one
ALL_KEYS=$(aws s3api list-objects-v2 \
    --bucket "$R2_BUCKET" \
    --prefix "postgres/$TIER/" \
    --endpoint-url "$R2_ENDPOINT" \
    --query 'Contents[?ends_with(Key, `.sql.gz`)].Key' \
    --output text 2>/dev/null | tr '\t' '\n' | grep -v '^$' || true)

if [[ -z "$ALL_KEYS" ]]; then
    die "no backups found in tier=$TIER — backup pipeline broken?"
fi

KEY=$(echo "$ALL_KEYS" | shuf -n 1)
log INFO "selected: $KEY (tier=$TIER, pool size=$(echo "$ALL_KEYS" | wc -l))"

# --- Download + verify checksum ---------------------------------------------
LOCAL_PATH="$TMP_DIR/backup.sql.gz"
aws s3 cp "s3://$R2_BUCKET/$KEY" "$LOCAL_PATH" \
    --endpoint-url "$R2_ENDPOINT" --no-progress \
    || die "download failed for $KEY"

SHA_KEY="${KEY}.sha256"
if aws s3 cp "s3://$R2_BUCKET/$SHA_KEY" "$TMP_DIR/sha" \
        --endpoint-url "$R2_ENDPOINT" --no-progress 2>/dev/null; then
    EXPECTED=$(awk '{print $1}' "$TMP_DIR/sha")
    ACTUAL=$(sha256sum "$LOCAL_PATH" | awk '{print $1}')
    [[ "$EXPECTED" == "$ACTUAL" ]] \
        || die "checksum mismatch for $KEY: expected=$EXPECTED actual=$ACTUAL"
    log INFO "checksum ok"
fi

# --- Restore into throwaway DB ----------------------------------------------
export PGPASSWORD="$POSTGRES_PASSWORD"
log INFO "creating throwaway db $THROWAWAY_DB"
psql --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" \
     --username="$POSTGRES_USER" --dbname="postgres" \
     --command="CREATE DATABASE \"$THROWAWAY_DB\"" >/dev/null \
    || die "could not create throwaway db"

log INFO "restoring..."
START=$(date +%s)
if ! gunzip -c "$LOCAL_PATH" \
    | psql --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" \
           --username="$POSTGRES_USER" --dbname="$THROWAWAY_DB" \
           --single-transaction --set ON_ERROR_STOP=on --quiet \
           2>"$TMP_DIR/restore.log"; then
    log ERROR "restore log tail:"
    tail -30 "$TMP_DIR/restore.log" >&2
    die "restore failed for $KEY"
fi
DURATION=$(( $(date +%s) - START ))
log INFO "restore done in ${DURATION}s"

# --- Sanity checks -----------------------------------------------------------
run_query() {
    psql --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" \
         --username="$POSTGRES_USER" --dbname="$THROWAWAY_DB" \
         --tuples-only --no-align --command="$1" 2>/dev/null
}

EXPECTED_TABLES=(users subscriptions backtests strategies broker_accounts live_engines positions trades signals audit_log)

log INFO "checking expected tables exist..."
for tbl in "${EXPECTED_TABLES[@]}"; do
    EXISTS=$(run_query "SELECT 1 FROM information_schema.tables WHERE table_name='$tbl' AND table_schema='public'")
    [[ "$EXISTS" == "1" ]] || die "missing expected table: $tbl"
done
log INFO "all expected tables present"

# Row count sanity — at minimum users table should have the seed admin
USER_COUNT=$(run_query "SELECT COUNT(*) FROM users" || echo "?")
[[ "$USER_COUNT" =~ ^[0-9]+$ ]] || die "users count is not a number: $USER_COUNT"
[[ "$USER_COUNT" -ge 1 ]] || die "users table empty (expected >= 1 seed admin)"
log INFO "users count: $USER_COUNT"

STRAT_COUNT=$(run_query "SELECT COUNT(*) FROM strategies" || echo "?")
[[ "$STRAT_COUNT" =~ ^[0-9]+$ ]] && [[ "$STRAT_COUNT" -ge 5 ]] \
    || log WARN "strategies count low: $STRAT_COUNT (expected >= 7 seeded)"

# Critical FK check — orphan subscriptions?
ORPHAN_SUBS=$(run_query "SELECT COUNT(*) FROM subscriptions s LEFT JOIN users u ON u.id = s.user_id WHERE u.id IS NULL")
[[ "$ORPHAN_SUBS" == "0" ]] || log WARN "found $ORPHAN_SUBS orphan subscriptions"

# --- Emit textfile metric for prometheus ------------------------------------
NODE_TEXTFILE_DIR="${NODE_TEXTFILE_DIR:-/var/lib/node_exporter/textfile_collector}"
if [[ -d "$NODE_TEXTFILE_DIR" ]]; then
    cat > "$NODE_TEXTFILE_DIR/forex_bot_backup_verify.prom.tmp" <<EOF
# HELP forex_bot_backup_verify_last_success_timestamp_seconds Last successful verify drill.
# TYPE forex_bot_backup_verify_last_success_timestamp_seconds gauge
forex_bot_backup_verify_last_success_timestamp_seconds $(date +%s)
# HELP forex_bot_backup_verify_restore_duration_seconds Wall clock for restore.
# TYPE forex_bot_backup_verify_restore_duration_seconds gauge
forex_bot_backup_verify_restore_duration_seconds{tier="$TIER"} $DURATION
EOF
    mv "$NODE_TEXTFILE_DIR/forex_bot_backup_verify.prom.tmp" \
       "$NODE_TEXTFILE_DIR/forex_bot_backup_verify.prom"
fi

SUMMARY="key=$KEY tier=$TIER users=$USER_COUNT strategies=$STRAT_COUNT duration=${DURATION}s"
log INFO "verify ok: $SUMMARY"
notify "INFO" "Backup verify succeeded — $SUMMARY"

# trap will drop throwaway db
exit 0
