#!/usr/bin/env bash
# ============================================================================
# scripts/smoke.sh — verify dev stack is up
# ============================================================================
# Returns 0 if all critical endpoints are reachable, non-zero otherwise.
# Use in dev.sh, CI smoke job, and as a Makefile target (make smoke).
# ============================================================================

set -euo pipefail

if [[ -t 1 ]]; then
  RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; NC=$'\033[0m'
else
  RED="" GREEN="" YELLOW="" CYAN="" NC=""
fi

PASS=0
FAIL=0

check() {
  local name="$1"
  local cmd="$2"
  printf "  %-30s " "$name"
  if eval "$cmd" >/dev/null 2>&1; then
    printf "%sok%s\n" "$GREEN" "$NC"
    PASS=$((PASS + 1))
  else
    printf "%sfail%s\n" "$RED" "$NC"
    FAIL=$((FAIL + 1))
  fi
}

printf "%s[smoke]%s checking forex-bot stack...\n" "$CYAN" "$NC"

check "backend /healthz"        "curl -sf -m 5 http://localhost:8000/healthz"
check "backend /docs"           "curl -sf -m 5 http://localhost:8000/docs"
check "frontend root"           "curl -sf -m 5 http://localhost:3000"
check "mt5-bridge-stub /healthz" "curl -sf -m 5 http://localhost:8500/healthz"
check "postgres TCP"            "docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml --project-directory . exec -T postgres pg_isready -U forexbot -d forexbot"
check "redis ping"              "docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml --project-directory . exec -T redis redis-cli ping | grep -q PONG"
check "prometheus /-/healthy"   "curl -sf -m 5 http://localhost:9090/-/healthy"
check "grafana /api/health"     "curl -sf -m 5 http://localhost:3001/api/health"

printf "\n%sresults:%s %s%d pass%s, %s%d fail%s\n" \
  "$CYAN" "$NC" "$GREEN" "$PASS" "$NC" "$RED" "$FAIL" "$NC"

if (( FAIL > 0 )); then
  printf "\n%s[hint]%s some services not ready — try:\n" "$YELLOW" "$NC"
  printf "  make logs        # see what's wrong\n"
  printf "  make ps          # container status\n"
  printf "  sleep 10 && %s   # retry after services warm up\n" "$0"
  exit 1
fi

printf "\n%sall green%s — open http://localhost:3000\n" "$GREEN" "$NC"
