#!/usr/bin/env bash
# ============================================================================
# infra/backup/restore.sh — Download + restore a Postgres backup from R2
# ============================================================================
# Owner: Hestia Kaoru
#
# Usage:
#   ./restore.sh                                 # interactive — pick latest
#   ./restore.sh --key postgres/daily/forex-bot-daily-2026-06-15.sql.gz
#   ./restore.sh --tier weekly --date 2026-06-08
#   ./restore.sh --target-db forex_bot_restore   # restore to a fresh DB
#   ./restore.sh --yes                           # skip confirmation (DANGEROUS)
#
# Will:
#   1. Download from R2 to a temp file.
#   2. Verify sha256 against the .sha256 sidecar.
#   3. (Optional) gpg-decrypt.
#   4. Prompt for confirmation (production = HEAVY warnings).
#   5. Restore via psql.
#
# DESTRUCTIVE — overwrites the target database. The dump uses
# `--clean --if-exists` so existing tables WILL be dropped.
# ============================================================================

set -euo pipefail
IFS=$'\n\t'

CONFIG_FILE="${BACKUP_ENV_FILE:-/etc/forex-bot/backup.env}"
TMP_DIR="$(mktemp -d -t forex-bot-restore-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

# --- Arg parse ---------------------------------------------------------------
KEY=""
TIER=""
DATE_OVERRIDE=""
TARGET_DB=""
YES=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --key) KEY="$2"; shift 2 ;;
        --tier) TIER="$2"; shift 2 ;;
        --date) DATE_OVERRIDE="$2"; shift 2 ;;
        --target-db) TARGET_DB="$2"; shift 2 ;;
        --yes|-y) YES=1; shift ;;
        --help|-h)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 1 ;;
    esac
done

log() { echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [$1] ${*:2}" >&2; }
die() { log ERROR "$*"; exit 1; }

# --- Load config -------------------------------------------------------------
[[ -r "$CONFIG_FILE" ]] || die "config not readable: $CONFIG_FILE"
# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${R2_BUCKET:?R2_BUCKET not set}"
: "${R2_ENDPOINT:?R2_ENDPOINT not set}"
: "${POSTGRES_USER:?POSTGRES_USER not set}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD not set}"
: "${POSTGRES_DB:?POSTGRES_DB not set}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
TARGET_DB="${TARGET_DB:-$POSTGRES_DB}"

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_KEY"
export AWS_DEFAULT_REGION="auto"

# --- Determine key -----------------------------------------------------------
if [[ -z "$KEY" ]]; then
    TIER="${TIER:-daily}"
    log INFO "no --key given; finding latest in tier=$TIER"

    if [[ -n "$DATE_OVERRIDE" ]]; then
        KEY="postgres/${TIER}/forex-bot-${TIER}-${DATE_OVERRIDE}.sql.gz"
    else
        KEY=$(aws s3api list-objects-v2 \
            --bucket "$R2_BUCKET" \
            --prefix "postgres/$TIER/" \
            --endpoint-url "$R2_ENDPOINT" \
            --query 'sort_by(Contents,&LastModified)[-1].Key' \
            --output text 2>/dev/null) || die "no backups found in tier=$TIER"
        [[ "$KEY" == "None" || -z "$KEY" ]] && die "no backups found in tier=$TIER"
    fi
fi

log INFO "selected key: $KEY"

# --- Download ----------------------------------------------------------------
LOCAL_PATH="$TMP_DIR/$(basename "$KEY")"
log INFO "downloading r2://$R2_BUCKET/$KEY"
aws s3 cp "s3://$R2_BUCKET/$KEY" "$LOCAL_PATH" \
    --endpoint-url "$R2_ENDPOINT" --no-progress \
    || die "download failed"

# --- Verify checksum --------------------------------------------------------
SHA_KEY="${KEY}.sha256"
SHA_LOCAL="$TMP_DIR/$(basename "$SHA_KEY")"
if aws s3 cp "s3://$R2_BUCKET/$SHA_KEY" "$SHA_LOCAL" \
        --endpoint-url "$R2_ENDPOINT" --no-progress 2>/dev/null; then
    EXPECTED=$(awk '{print $1}' "$SHA_LOCAL")
    ACTUAL=$(sha256sum "$LOCAL_PATH" | awk '{print $1}')
    [[ "$EXPECTED" == "$ACTUAL" ]] || die "checksum mismatch! expected=$EXPECTED actual=$ACTUAL"
    log INFO "checksum verified ($ACTUAL)"
else
    log WARN "no checksum sidecar found — skipping integrity check"
fi

# --- Optional gpg decrypt ----------------------------------------------------
if [[ "$LOCAL_PATH" == *.gpg ]]; then
    log INFO "gpg-decrypting"
    gpg --batch --yes --decrypt --output "${LOCAL_PATH%.gpg}" "$LOCAL_PATH"
    LOCAL_PATH="${LOCAL_PATH%.gpg}"
fi

# --- Pre-flight: target connection -------------------------------------------
export PGPASSWORD="$POSTGRES_PASSWORD"
psql --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" \
     --username="$POSTGRES_USER" --dbname="postgres" \
     --tuples-only --no-align \
     --command="SELECT 1" >/dev/null \
    || die "cannot connect to postgres at $POSTGRES_HOST:$POSTGRES_PORT"

# --- Confirmation prompt ----------------------------------------------------
if [[ "$YES" -ne 1 ]]; then
    cat <<EOF >&2

=============================================================================
  DESTRUCTIVE OPERATION: DATABASE RESTORE
=============================================================================
  Host       : $POSTGRES_HOST:$POSTGRES_PORT
  User       : $POSTGRES_USER
  Target DB  : $TARGET_DB
  Source     : r2://$R2_BUCKET/$KEY
  Size       : $(numfmt --to=iec --suffix=B "$(stat -c %s "$LOCAL_PATH" 2>/dev/null || stat -f %z "$LOCAL_PATH")")
=============================================================================

  The dump uses --clean --if-exists. Existing tables in '$TARGET_DB' will
  be DROPPED and recreated. All data not in the backup will be LOST.

  Type the database name '$TARGET_DB' to confirm:
EOF
    read -r confirmation
    [[ "$confirmation" == "$TARGET_DB" ]] || die "confirmation mismatch — aborting"
fi

# --- Restore ----------------------------------------------------------------
# Create target DB if it doesn't exist
DB_EXISTS=$(psql --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" --dbname="postgres" \
    --tuples-only --no-align \
    --command="SELECT 1 FROM pg_database WHERE datname = '$TARGET_DB'")

if [[ "$DB_EXISTS" != "1" ]]; then
    log INFO "creating database $TARGET_DB"
    psql --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" \
         --username="$POSTGRES_USER" --dbname="postgres" \
         --command="CREATE DATABASE \"$TARGET_DB\""
fi

log INFO "restoring..."
START_TS=$(date +%s)

if ! gunzip -c "$LOCAL_PATH" \
    | psql --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" \
           --username="$POSTGRES_USER" --dbname="$TARGET_DB" \
           --single-transaction \
           --set ON_ERROR_STOP=on \
           --quiet \
           2> "$TMP_DIR/restore.log"; then
    log ERROR "restore failed; tail of error log:"
    tail -50 "$TMP_DIR/restore.log" >&2
    die "psql restore failed"
fi

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

# --- Post-restore sanity checks ---------------------------------------------
ROW_USERS=$(psql --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" --dbname="$TARGET_DB" \
    --tuples-only --no-align \
    --command="SELECT COUNT(*) FROM users" 2>/dev/null || echo "?")

log INFO "restore complete in ${DURATION}s — users count: $ROW_USERS"
log INFO "next steps:"
log INFO "  1) verify schema: psql -d $TARGET_DB -c '\\dt'"
log INFO "  2) run alembic upgrade head if app is newer than backup"
log INFO "  3) smoke test: curl /healthz"
log INFO "  4) if this was a DR drill, drop target db: DROP DATABASE $TARGET_DB"

unset PGPASSWORD
exit 0
