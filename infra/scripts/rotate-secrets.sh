#!/usr/bin/env bash
# ============================================================================
# infra/scripts/rotate-secrets.sh — Rotate JWT / HMAC / KEK
# ============================================================================
# Owner: Hestia Kaoru
#
# Quarterly rotation procedure. Use from your laptop; SSH to prod and update.
#
# Usage:
#   ./infra/scripts/rotate-secrets.sh --secret=JWT_SECRET_KEY      --host=ops@vps
#   ./infra/scripts/rotate-secrets.sh --secret=NEXTAUTH_SECRET     --host=ops@vps
#   ./infra/scripts/rotate-secrets.sh --secret=INTERNAL_HMAC_SECRET --host=ops@vps
#   ./infra/scripts/rotate-secrets.sh --secret=ENCRYPTION_KEK       --host=ops@vps --rewrap
#       (KEK rotation requires the rewrap step — see below)
#   ./infra/scripts/rotate-secrets.sh --secret=GRAFANA_PASSWORD     --host=ops@vps
#
# Source of truth: 1Password vault "forex-bot-ops". This script updates the
# server-side .env and triggers a service reload.
#
# JWT rotation requires graceful handling: tokens issued with old key remain
# valid for JWT_ACCESS_TOKEN_TTL_MIN minutes — we accept either old or new
# during a 30-min overlap window. App code reads KEY_PREVIOUS in addition to
# KEY_CURRENT. See backend/app/security/key_ring.py.
# ============================================================================

set -euo pipefail
IFS=$'\n\t'

SECRET=""
HOST=""
REMOTE_ENV="/etc/forex-bot/.env"
REWRAP=0

log() { printf "[%s] [%s] %s\n" "$(date -u +'%H:%M:%SZ')" "$1" "${*:2}" >&2; }
die() { log ERROR "$*"; exit 1; }

for arg in "$@"; do
    case "$arg" in
        --secret=*) SECRET="${arg#*=}" ;;
        --host=*) HOST="${arg#*=}" ;;
        --remote-env=*) REMOTE_ENV="${arg#*=}" ;;
        --rewrap) REWRAP=1 ;;
        --help|-h) sed -n '2,30p' "$0"; exit 0 ;;
        *) die "unknown arg: $arg" ;;
    esac
done

[[ -n "$SECRET" && -n "$HOST" ]] || die "--secret and --host required"

# --- Generate ---------------------------------------------------------------
case "$SECRET" in
    JWT_SECRET_KEY|NEXTAUTH_SECRET|INTERNAL_HMAC_SECRET)
        NEW=$(openssl rand -base64 48 | tr -d '\n=' | head -c 48)
        ;;
    GRAFANA_PASSWORD|REDIS_PASSWORD|POSTGRES_PASSWORD)
        NEW=$(openssl rand -base64 32 | tr -d '\n=/+' | head -c 32)
        ;;
    ENCRYPTION_KEK_BASE64|ENCRYPTION_KEK)
        # 32 bytes of raw random, base64 encoded
        NEW=$(openssl rand -base64 32 | tr -d '\n')
        ;;
    *)
        die "unsupported secret: $SECRET"
        ;;
esac

# Show last 4 chars as a confirmation footprint
log INFO "generated new $SECRET (...${NEW: -4})"

# --- Confirm ----------------------------------------------------------------
cat <<EOF >&2

============================================================================
  ROTATING SECRET ON $HOST
============================================================================
  Secret  : $SECRET
  File    : $REMOTE_ENV
  Strategy: dual-key overlap (current → previous) for app-code-aware secrets

  This will:
    1) Read current value from $REMOTE_ENV
    2) Write current as ${SECRET}_PREVIOUS, new as ${SECRET}
    3) Trigger service reload (compose up -d --no-deps backend frontend)

  Are you sure? (yes/no)
EOF
read -r confirmation
[[ "$confirmation" == "yes" ]] || die "aborted"

# --- Apply ------------------------------------------------------------------
log INFO "fetching current $SECRET from $HOST"
CURRENT=$(ssh "$HOST" "sudo grep -E '^${SECRET}=' $REMOTE_ENV | head -1 | cut -d= -f2-" || echo "")

# Atomic update via temp file
log INFO "updating $REMOTE_ENV (atomic)"
ssh "$HOST" "sudo bash -s" <<REMOTE_EOF
set -euo pipefail
ENVF=$REMOTE_ENV
TMPF=\$(mktemp)
cp "\$ENVF" "\$TMPF"
chmod --reference="\$ENVF" "\$TMPF"
# Remove any existing _PREVIOUS line for this secret
sed -i "/^${SECRET}_PREVIOUS=/d" "\$TMPF"
# Append _PREVIOUS with current value
if [ -n "$CURRENT" ]; then
    echo "${SECRET}_PREVIOUS=$CURRENT" >> "\$TMPF"
fi
# Replace current value
if grep -qE "^${SECRET}=" "\$TMPF"; then
    sed -i "s|^${SECRET}=.*|${SECRET}=$NEW|" "\$TMPF"
else
    echo "${SECRET}=$NEW" >> "\$TMPF"
fi
mv "\$TMPF" "\$ENVF"
chown root:root "\$ENVF"
chmod 600 "\$ENVF"
REMOTE_EOF

# --- KEK rewrap (special case) ---------------------------------------------
if [[ "$SECRET" == "ENCRYPTION_KEK_BASE64" ]] || [[ "$SECRET" == "ENCRYPTION_KEK" ]]; then
    if [[ "$REWRAP" -eq 1 ]]; then
        log INFO "running KEK rewrap — re-encrypts all DEKs in DB"
        # Bump ENCRYPTION_KEY_VERSION too
        ssh "$HOST" "sudo bash -c '
            ENVF=$REMOTE_ENV
            cur=\$(grep ENCRYPTION_KEY_VERSION \$ENVF | cut -d= -f2)
            new=\$((cur + 1))
            sed -i \"s|^ENCRYPTION_KEY_VERSION=.*|ENCRYPTION_KEY_VERSION=\$new|\" \$ENVF
        '"
        ssh "$HOST" "cd /srv/forex-bot && docker compose --env-file .env.production -f infra/docker-compose.yml -f infra/docker-compose.prod.yml run --rm backend python -m app.scripts.rewrap_keys"
    else
        log WARN "KEK rotated without --rewrap. Old DEKs are still wrapped under old KEK!"
        log WARN "Run with --rewrap to re-encrypt user secrets under the new KEK."
    fi
fi

# --- Reload services -------------------------------------------------------
log INFO "reloading services on $HOST"
case "$SECRET" in
    GRAFANA_PASSWORD)
        ssh "$HOST" "cd /srv/forex-bot && docker compose --env-file .env.production -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d --no-deps --force-recreate grafana"
        ;;
    REDIS_PASSWORD|POSTGRES_PASSWORD)
        die "REDIS/POSTGRES password rotation requires a maintenance window. Use a separate runbook."
        ;;
    *)
        # Backend reads JWT/HMAC/KEK/NEXTAUTH from env — needs restart.
        # NextAuth: frontend reads NEXTAUTH_SECRET from env at boot — needs restart.
        ssh "$HOST" "cd /srv/forex-bot && docker compose --env-file .env.production -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d --no-deps backend frontend"
        ;;
esac

# --- Verify ----------------------------------------------------------------
log INFO "smoke check"
ssh "$HOST" "curl -fsS https://api.forexbot.example.com/healthz" \
    | grep -q '"status":"ok"' \
    && log INFO "smoke ok" \
    || die "smoke FAILED — rollback (restore previous $REMOTE_ENV from 1Password)"

# --- 1Password reminder ----------------------------------------------------
log INFO "REMEMBER: update 1Password vault 'forex-bot-ops' with the new value"
log INFO "the new $SECRET ends in: ...${NEW: -4}"
log INFO "after JWT_ACCESS_TOKEN_TTL_MIN (default 15m), remove the _PREVIOUS entry"

exit 0
