# Runbook — Forex Bot Platform

> Owner: Hestia Kaoru
> Last updated: 2026-06-15
> For use at 3am. If not, fix the doc.

Use this for routine ops and known incidents. Links inline to dedicated
incident playbooks where they exist.

---

## Conventions

- All commands run from project root (`/opt/forex-bot` on VPS, repo root in dev).
- "VPS" = Linux VPS unless stated.
- `make ...` works in dev; on VPS use the explicit `docker compose -f
  infra/docker-compose.yml -f infra/docker-compose.prod.yml --project-directory .`.

---

## 1. Routine ops

### 1.1 Restart a single service

Dev:
```bash
make restart                                          # all
docker compose -f infra/docker-compose.yml restart backend
```

Prod:
```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
  --project-directory . restart backend
```

Health check after restart:
```bash
./scripts/smoke.sh
```

### 1.2 View logs

```bash
make logs                       # all (dev)
make logs-backend
make logs-engine
docker compose logs -f --tail=200 --since 30m backend
```

Prod log shipping → Loki → Grafana → Explore → `{service="backend"}`.

### 1.3 Container status

```bash
make ps
docker compose ps
docker stats --no-stream
```

### 1.4 Reload config without restart (Prometheus)

```bash
curl -X POST http://localhost:9090/-/reload
```

---

## 2. Database

### 2.1 Connect to DB

```bash
make shell-db                                # dev
docker compose exec postgres psql -U forexbot -d forexbot
```

### 2.2 Run migrations

```bash
make migrate                                 # dev
docker compose exec -T backend alembic upgrade head
```

### 2.3 Manual backup

```bash
docker compose exec -T postgres pg_dump -U forexbot -F c -d forexbot \
  > backup-$(date +%Y%m%d-%H%M%S).dump
```

### 2.4 Restore from dump

**STOP traffic first.** Put Caddy in maintenance mode or drain via Cloudflare.

```bash
# 1. drop + recreate (DESTROYS DATA)
docker compose exec -T postgres psql -U forexbot -d postgres \
  -c "DROP DATABASE forexbot WITH (FORCE);" \
  -c "CREATE DATABASE forexbot OWNER forexbot;"

# 2. restore
docker compose exec -T postgres pg_restore -U forexbot -d forexbot \
  --clean --if-exists < backup-20260615-030000.dump

# 3. verify row counts
docker compose exec -T postgres psql -U forexbot -d forexbot \
  -c "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 20;"

# 4. resume traffic
```

### 2.5 Vacuum / analyze

```bash
docker compose exec -T postgres psql -U forexbot -d forexbot \
  -c "VACUUM ANALYZE;"
```

---

## 3. Deploy

### 3.1 Deploy via GitHub Actions

1. Go to **Actions → deploy → Run workflow**.
2. Pick environment (`staging` or `production`).
3. Optional: pin `image_tag` (default = current commit SHA).
4. Confirm. Pipeline:
   - builds images → pushes to GHCR
   - SSH → VPS → pulls images → migrates → swaps services
   - runs `./scripts/smoke.sh`
   - notifies Discord

### 3.2 Manual deploy (SSH on VPS)

```bash
ssh forex-bot@<vps-host>
cd /opt/forex-bot
git fetch && git reset --hard origin/main
echo "IMAGE_TAG=<new-tag>" >> .env  # or edit IMAGE_TAG line
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
  --project-directory . pull
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
  --project-directory . run --rm backend alembic upgrade head
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
  --project-directory . up -d --remove-orphans
./scripts/smoke.sh
```

### 3.3 Rollback

```bash
# 1. find previous good tag
docker images --format '{{.Repository}}:{{.Tag}}' | grep forex-bot/backend

# 2. set tag and bring services back
ssh forex-bot@<vps-host>
cd /opt/forex-bot
sed -i.bak "s/^IMAGE_TAG=.*/IMAGE_TAG=<previous-good-tag>/" .env
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
  --project-directory . up -d --remove-orphans
./scripts/smoke.sh
```

**If migrations were applied** and incompatible with the older image:
restore DB from the most recent pre-deploy dump (§2.4) before rolling images
back. Always take a `pg_dump` snapshot **before** running migrations in prod
(`deploy.yml` does this in Phase 2 — Phase 1, do it manually).

---

## 4. MT5 bridge

### 4.1 Bridge unhealthy

Symptom: backend `/healthz/deep` reports `mt5_bridge: down`.

```bash
# 1. ping bridge from Linux VPS over WireGuard
ping -c3 10.42.0.2
curl --cacert ca.crt --cert client.crt --key client.key \
  https://10.42.0.2:9100/healthz

# 2. if no reply, RDP to Windows VPS, check NSSM service:
#    services.msc → "mt5-bridge" → status
#    or via PowerShell:
#    Get-Service mt5-bridge

# 3. restart bridge:
#    nssm restart mt5-bridge

# 4. verify
curl --cacert ca.crt --cert client.crt --key client.key \
  https://10.42.0.2:9100/healthz
```

### 4.2 MT5 terminal stuck (dev stub equivalent: restart stub container)

Dev:
```bash
docker compose restart mt5-bridge-stub
```

Prod (RDP):
- Open Task Manager → kill `terminal64.exe` for the affected `login`.
- NSSM watchdog will respawn.

---

## 5. Emergency

### 5.1 Kill all bots (stop new orders, leave open positions)

Backend exposes the kill switch:
```bash
curl -X POST -H "Authorization: Bearer <admin-token>" \
  https://api.<domain>/admin/kill-switch \
  -d '{"reason": "manual emergency stop", "actor": "hestia"}'
```

This sets a Redis flag `kill_switch:enabled=1`. Trading engine checks every
loop. Existing open positions are NOT closed automatically.

### 5.2 Close all open positions

```bash
curl -X POST -H "Authorization: Bearer <admin-token>" \
  https://api.<domain>/admin/positions/close-all \
  -d '{"confirm": true, "reason": "manual close-all"}'
```

This sends close orders to MT5 bridge for every open position across all users.
**Use sparingly** — broker may flag mass orders.

### 5.3 Take the whole platform down

```bash
ssh forex-bot@<vps-host>
cd /opt/forex-bot
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
  --project-directory . down
```

To bring back:
```bash
docker compose ... up -d
./scripts/smoke.sh
```

### 5.4 Cloudflare "Under Attack" mode

Cloudflare dashboard → app.<domain> → Overview → Quick Actions →
"Under Attack Mode: On". Or via API:
```bash
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/<zone-id>/settings/security_level" \
  -H "Authorization: Bearer <cf-token>" \
  -H "Content-Type: application/json" \
  -d '{"value":"under_attack"}'
```

---

## 6. Common errors

### 6.1 `address already in use` on 5432 / 6379 / 3000 / 8000

Another process is holding the port. Find it:
```bash
lsof -iTCP:5432 -sTCP:LISTEN
```
Then either kill it or change the host port in `docker-compose.override.yml`.

### 6.2 Backend keeps restarting

```bash
docker compose logs --tail=200 backend
```
Common causes:
- Postgres not ready when backend starts → check `depends_on.healthy`.
- Alembic migration mismatch → run `make migrate`.
- `JWT_SECRET` missing → check `.env`.

### 6.3 Frontend 500 errors on every page

```bash
docker compose logs --tail=200 frontend
```
Usually:
- `NEXTAUTH_SECRET` is `PLACEHOLDER` → run `./scripts/dev.sh` again.
- `NEXT_PUBLIC_API_URL` does not match where backend is reachable from
  the browser (dev: `http://localhost:8000`, prod: `https://api.<domain>`).

### 6.4 docker compose: `network forex-bot-internal not found`

```bash
docker compose down                     # full teardown
docker network prune
docker compose up -d
```

### 6.5 Disk full on VPS

```bash
df -h
docker system df
docker system prune -a --volumes        # NOTE: removes unused volumes
journalctl --vacuum-time=7d
```

---

## 7. Postmortem template

When an incident closes, file a postmortem in `docs/deployment/postmortems/`:

```markdown
# YYYY-MM-DD — short title

**Severity:** SEV-1/2/3
**Duration:** Xm
**Detection:** alert | user report | dashboard
**Author:** Hestia + ...

## TL;DR
1-2 sentences.

## Impact
who, what, how many, how much $$

## Timeline (UTC)
- HH:MM event
- HH:MM event

## Root cause
1-2 paragraphs. blameless.

## What went well
- ...

## What went poorly
- ...

## Action items
- [ ] owner — deadline — description
```

---

## 8. Escalation

| Tier | Owner | Reach |
|------|-------|-------|
| 1 | Hestia Kaoru (DevOps) | Discord `#oncall` |
| 2 | Daedalus Souta (Architect) | Discord DM |
| 3 | Zeus Ryujin (PM) | Phone if SEV-1 |

Always update `#status` channel every 15 min during SEV-1.
