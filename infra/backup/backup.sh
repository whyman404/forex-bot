#!/usr/bin/env bash
# ============================================================================
# infra/backup/backup.sh — Postgres logical backup → Cloudflare R2
# ============================================================================
# Owner: Hestia Kaoru
# Schedule via host cron:  0 2 * * *  /srv/forex-bot/infra/backup/backup.sh
#
# Env (sourced from /etc/forex-bot/backup.env, chmod 600 root:root):
#   R2_BUCKET           e.g. forex-bot-backups
#   R2_ACCESS_KEY
#   R2_SECRET_KEY
#   R2_ENDPOINT         e.g. https://<accountid>.r2.cloudflarestorage.com
#   POSTGRES_USER
#   POSTGRES_PASSWORD
#   POSTGRES_DB
#   POSTGRES_HOST       (default: localhost)
#   POSTGRES_PORT       (default: 5432)
#   GPG_RECIPIENT       (optional — if set, encrypt before upload)
#   SLACK_WEBHOOK_URL   (optional — for alerts)
#
# Retention: 7 daily + 4 weekly + 12 monthly (managed by R2 lifecycle policy
# AND by this script's prune step as belt-and-suspenders).
#
# Exit codes:
#   0  = success
#   1  = config error
#   2  = pg_dump failed
#   3  = upload failed
#   4  = verification (size check) failed
# ============================================================================

set -euo pipefail
IFS=$'\n\t'

readonly SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
readonly CONFIG_FILE="${BACKUP_ENV_FILE:-/etc/forex-bot/backup.env}"
readonly LOCK_FILE="/var/lock/forex-bot-backup.lock"
readonly LOG_FILE="/var/log/forex-bot/backup.log"
readonly TMP_DIR="$(mktemp -d -t forex-bot-backup-XXXXXX)"
trap 'cleanup' EXIT INT TERM

cleanup() {
    local exit_code=$?
    rm -rf "$TMP_DIR"
    if [[ -f "$LOCK_FILE" ]]; then
        rm -f "$LOCK_FILE"
    fi
    exit $exit_code
}

log() {
    local level="$1"; shift
    local msg="[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [$level] $*"
    echo "$msg" | tee -a "$LOG_FILE" >&2
}

notify_slack() {
    local level="$1" msg="$2"
    [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && return 0
    local color="good"
    case "$level" in
        ERROR) color="danger" ;;
        WARN)  color="warning" ;;
    esac
    curl -fsS -X POST -H 'Content-Type: application/json' \
        --data "{\"attachments\":[{\"color\":\"$color\",\"title\":\"forex-bot backup: $level\",\"text\":\"$msg\"}]}" \
        "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
}

die() {
    log "ERROR" "$*"
    notify_slack "ERROR" "$*"
    exit "${2:-1}"
}

# --- Pre-flight ---------------------------------------------------------------

mkdir -p "$(dirname "$LOG_FILE")"

[[ -r "$CONFIG_FILE" ]] || die "config not readable: $CONFIG_FILE"
# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${R2_BUCKET:?R2_BUCKET not set}"
: "${R2_ACCESS_KEY:?R2_ACCESS_KEY not set}"
: "${R2_SECRET_KEY:?R2_SECRET_KEY not set}"
: "${R2_ENDPOINT:?R2_ENDPOINT not set}"
: "${POSTGRES_USER:?POSTGRES_USER not set}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD not set}"
: "${POSTGRES_DB:?POSTGRES_DB not set}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

# Single-instance lock (prevent overlapping runs)
if [[ -f "$LOCK_FILE" ]]; then
    pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        die "another backup already running (pid=$pid)"
    fi
    log "WARN" "stale lock removed (pid=$pid)"
fi
echo $$ > "$LOCK_FILE"

# Check required tools
for cmd in pg_dump gzip aws sha256sum; do
    command -v "$cmd" >/dev/null 2>&1 || die "missing required command: $cmd"
done

# Configure AWS CLI for R2
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_KEY"
export AWS_DEFAULT_REGION="auto"

# --- Determine tier ----------------------------------------------------------
# daily, weekly (Sunday), monthly (1st of month)
TODAY="$(date -u +'%Y-%m-%d')"
DAY_OF_WEEK="$(date -u +'%u')"   # 1..7 (1=Mon)
DAY_OF_MONTH="$(date -u +'%d')"

TIER="daily"
[[ "$DAY_OF_WEEK" == "7" ]]   && TIER="weekly"     # Sunday weekly
[[ "$DAY_OF_MONTH" == "01" ]] && TIER="monthly"    # 1st of month overrides

BACKUP_NAME="forex-bot-${TIER}-${TODAY}.sql.gz"
BACKUP_PATH="$TMP_DIR/$BACKUP_NAME"
R2_KEY="postgres/${TIER}/${BACKUP_NAME}"

log "INFO" "starting backup: tier=$TIER name=$BACKUP_NAME"

# --- Dump --------------------------------------------------------------------
START_TS=$(date +%s)

export PGPASSWORD="$POSTGRES_PASSWORD"
# Use --clean --if-exists so restore.sh works against an existing DB.
# --no-owner / --no-privileges so the dump is portable across environments.
# Format = plain SQL gz, easier to inspect than custom.
if ! pg_dump \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --no-owner \
        --no-privileges \
        --clean --if-exists \
        --format=plain \
        --verbose \
        2>"$TMP_DIR/pg_dump.log" \
    | gzip -9 > "$BACKUP_PATH"; then
    log "ERROR" "pg_dump failed; log follows:"
    tail -50 "$TMP_DIR/pg_dump.log" >&2
    die "pg_dump failed" 2
fi
unset PGPASSWORD

DUMP_TS=$(date +%s)
DUMP_SECONDS=$((DUMP_TS - START_TS))
DUMP_SIZE=$(stat -c %s "$BACKUP_PATH" 2>/dev/null || stat -f %z "$BACKUP_PATH")
log "INFO" "dump complete: ${DUMP_SIZE} bytes in ${DUMP_SECONDS}s"

# Sanity check — empty backup means something is wrong
if [[ "$DUMP_SIZE" -lt 10240 ]]; then
    die "dump suspiciously small (${DUMP_SIZE} bytes)" 4
fi

# Compute checksum
CHECKSUM=$(sha256sum "$BACKUP_PATH" | awk '{print $1}')
echo "$CHECKSUM  $BACKUP_NAME" > "$BACKUP_PATH.sha256"
log "INFO" "sha256=$CHECKSUM"

# --- Optional GPG encryption -------------------------------------------------
if [[ -n "${GPG_RECIPIENT:-}" ]]; then
    log "INFO" "encrypting with gpg recipient=$GPG_RECIPIENT"
    gpg --batch --yes --trust-model always \
        --recipient "$GPG_RECIPIENT" \
        --output "$BACKUP_PATH.gpg" \
        --encrypt "$BACKUP_PATH"
    BACKUP_PATH="$BACKUP_PATH.gpg"
    BACKUP_NAME="$BACKUP_NAME.gpg"
    R2_KEY="$R2_KEY.gpg"
fi

# --- Upload to R2 ------------------------------------------------------------
log "INFO" "uploading to r2://$R2_BUCKET/$R2_KEY"
if ! aws s3 cp "$BACKUP_PATH" "s3://$R2_BUCKET/$R2_KEY" \
        --endpoint-url "$R2_ENDPOINT" \
        --no-progress \
        --storage-class STANDARD \
        --metadata "tier=$TIER,date=$TODAY,sha256=$CHECKSUM,dump_seconds=$DUMP_SECONDS,size=$DUMP_SIZE"; then
    die "R2 upload failed" 3
fi

# Upload checksum file as well
aws s3 cp "$BACKUP_PATH.sha256" "s3://$R2_BUCKET/$R2_KEY.sha256" \
    --endpoint-url "$R2_ENDPOINT" --no-progress >/dev/null

# Verify upload (HEAD then size compare)
REMOTE_SIZE=$(aws s3api head-object \
    --bucket "$R2_BUCKET" --key "$R2_KEY" \
    --endpoint-url "$R2_ENDPOINT" --query 'ContentLength' --output text)
if [[ "$REMOTE_SIZE" != "$DUMP_SIZE" ]] && [[ -z "${GPG_RECIPIENT:-}" ]]; then
    die "remote size mismatch local=$DUMP_SIZE remote=$REMOTE_SIZE" 4
fi
log "INFO" "upload verified: $REMOTE_SIZE bytes"

# --- Prune old backups (belt-and-suspenders to R2 lifecycle) ----------------
prune_tier() {
    local tier="$1" keep="$2"
    log "INFO" "pruning $tier (keep newest $keep)"
    # List, sort newest-first, drop the first $keep, delete the rest
    aws s3api list-objects-v2 \
        --bucket "$R2_BUCKET" \
        --prefix "postgres/$tier/" \
        --endpoint-url "$R2_ENDPOINT" \
        --query 'Contents[?Size>`0`].[Key,LastModified]' \
        --output text 2>/dev/null \
    | sort -k2 -r \
    | tail -n "+$((keep + 1))" \
    | awk '{print $1}' \
    | while read -r key; do
        [[ -z "$key" ]] && continue
        log "INFO" "deleting old backup: $key"
        aws s3 rm "s3://$R2_BUCKET/$key" \
            --endpoint-url "$R2_ENDPOINT" --no-progress >/dev/null || true
        aws s3 rm "s3://$R2_BUCKET/${key}.sha256" \
            --endpoint-url "$R2_ENDPOINT" --no-progress >/dev/null 2>&1 || true
    done
}

prune_tier daily 7
prune_tier weekly 4
prune_tier monthly 12

# --- Metrics emission --------------------------------------------------------
# Drop a textfile for node-exporter to scrape (collector.textfile enabled)
NODE_TEXTFILE_DIR="${NODE_TEXTFILE_DIR:-/var/lib/node_exporter/textfile_collector}"
if [[ -d "$NODE_TEXTFILE_DIR" ]]; then
    cat > "$NODE_TEXTFILE_DIR/forex_bot_backup.prom.tmp" <<EOF
# HELP forex_bot_backup_last_success_timestamp_seconds Unix time of last successful backup.
# TYPE forex_bot_backup_last_success_timestamp_seconds gauge
forex_bot_backup_last_success_timestamp_seconds{tier="$TIER"} $(date +%s)
# HELP forex_bot_backup_size_bytes Size of last backup.
# TYPE forex_bot_backup_size_bytes gauge
forex_bot_backup_size_bytes{tier="$TIER"} $DUMP_SIZE
# HELP forex_bot_backup_duration_seconds Wall clock seconds for pg_dump.
# TYPE forex_bot_backup_duration_seconds gauge
forex_bot_backup_duration_seconds{tier="$TIER"} $DUMP_SECONDS
EOF
    mv "$NODE_TEXTFILE_DIR/forex_bot_backup.prom.tmp" "$NODE_TEXTFILE_DIR/forex_bot_backup.prom"
fi

END_TS=$(date +%s)
TOTAL_SECONDS=$((END_TS - START_TS))
SUMMARY="tier=$TIER size=$(numfmt --to=iec --suffix=B "$DUMP_SIZE" 2>/dev/null || echo "${DUMP_SIZE}B") duration=${TOTAL_SECONDS}s key=$R2_KEY"
log "INFO" "backup complete: $SUMMARY"
notify_slack "INFO" "Backup succeeded: $SUMMARY"

exit 0
