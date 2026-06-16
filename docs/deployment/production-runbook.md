# Production Runbook — Forex Bot

> Owner: Hestia Kaoru
> Last updated: 2026-06-15
> Audience: On-call engineer at 3am.

---

## TL;DR — common operations

```bash
# Tail backend logs
ssh ops@vps "cd /srv/forex-bot && docker compose --env-file .env.production -f infra/docker-compose.yml -f infra/docker-compose.prod.yml logs --tail 200 -f backend"

# Restart one service (zero-downtime — uses rolling)
ssh ops@vps "cd /srv/forex-bot && docker compose ... up -d --no-deps --wait backend"

# Run a one-off DB query
ssh ops@vps "cd /srv/forex-bot && docker compose ... exec postgres psql -U forex -d forex_bot -c 'SELECT count(*) FROM users;'"

# Manual deploy
make deploy-prod

# Manual rollback
./scripts/rollback.sh --env=production --host=ops@vps

# Trigger global kill switch
ssh ops@vps "cd /srv/forex-bot && docker compose ... exec backend python -m app.scripts.kill_all --confirm"
```

---

## Section 1 — First-time deploy

### Pre-requisites

- [ ] Linux VPS provisioned (Hetzner CX31 or larger).
- [ ] `infra/scripts/setup-vps.sh` run as root → deploy user `forex` exists.
- [ ] Windows VPS provisioned (Contabo VPS M) → `infra/scripts/setup-windows-mt5-vps.md` complete → bridge `/healthz` returns 200 via Cloudflare Tunnel.
- [ ] Cloudflare zone created → DNS records per `docs/deployment/cloudflare-setup.md`.
- [ ] `.env.prod` populated from `.env.prod.example` (use 1Password).
- [ ] `.env.prod` rsynced to `/etc/forex-bot/.env` on Linux VPS, chmod 600 root:root.
- [ ] R2 bucket `forex-bot-backups` created in Cloudflare, lifecycle policy applied.
- [ ] Slack `#alerts-critical`, `#alerts-warning`, `#alerts-audit` channels created with webhook.
- [ ] `make test` green locally.

### Steps

1. `make deploy-prod` from your laptop.
2. Watch deploy.sh output for any FAIL messages.
3. After "DONE", verify:
   - https://forexbot.example.com → renders.
   - https://api.forexbot.example.com/healthz → 200.
   - Grafana dashboards populate with data within 60s.
   - First scheduled backup runs at 02:00 UTC next morning.

### Post-deploy

- [ ] Seed admin user (one-time): `ssh ops@vps "cd /srv/forex-bot && docker compose ... run --rm backend python -m app.scripts.seed_admin"`.
- [ ] Login at https://forexbot.example.com/login → change admin password.
- [ ] Set `last_known_good=$(git rev-parse HEAD)` in `/etc/forex-bot/last_known_good`.
- [ ] Update status page (better-stack.com or uptimerobot).

---

## Section 2 — Incident response

### General flow

1. **Acknowledge** — Slack reaction `:eyes:` within 5 min.
2. **Triage** — read alert annotation + runbook URL. Check dashboards.
3. **Mitigate** — rollback if a deploy was recent; otherwise see specific runbook.
4. **Communicate** — post in `#incidents` channel with TL;DR every 15 min.
5. **Resolve** — close alert in alertmanager; verify on dashboard.
6. **Postmortem** — write within 48h using `docs/deployment/postmortem-template.md`.

### Severity matrix

| Sev | Definition | Response time | Examples |
|---|---|---|---|
| SEV-1 | Trading broken (live engines down, MT5 unreachable) | 5 min | mt5_bridge_unreachable, live_engine_heartbeat_missing |
| SEV-2 | App down for >50% of users | 15 min | BackendDown all instances, PostgresDown |
| SEV-3 | Degraded performance | 1h | BackendHighLatencyP95, RedisMemoryHigh |
| SEV-4 | Single-user issue | next business day | individual user billing problem |

### Backend down

→ see `runbooks/backend-down.md`.

Quick triage:
1. `docker ps` — backend containers running?
2. `docker logs forex-bot-backend-1 --tail 200` — Python exception?
3. `docker stats` — CPU/RAM exhausted?
4. Recent deploy? → rollback.

### Database emergency

→ see `runbooks/db-failover.md`.

If postgres won't start: do NOT delete `/srv/forex-bot/data/postgres/`. That
is your data. Stop, snapshot at the host level (Hetzner snapshot), then debug.

### MT5 bridge disconnected

→ see `runbooks/mt5-disconnect.md`.

This is SEV-1 — live engines have no order path. Kill switch will auto-engage
within 90s. Verify via Grafana `trading` dashboard.

Common causes:
- Cloudflare Tunnel cert expired (auto-renews, but check).
- Windows VPS rebooted by provider.
- Exness server maintenance (check broker status page).

---

## Section 3 — Routine ops

### Daily

- Glance at Grafana Overview dashboard.
- Skim `#alerts-warning` channel for new warnings.

### Weekly

- Review `#incidents` for postmortem completeness.
- Review WAF events in Cloudflare for false-positives.
- Check disk usage on host: `df -h /srv`.
- Verify backup completed: `tail /var/log/forex-bot/backup.log`.

### Monthly

- Patch host: `apt update && apt upgrade -y` (or rely on unattended-upgrades).
- Patch images: `docker pull` all images, redeploy.
- Rotate Slack incident channel report.
- Review on-call schedule.

### Quarterly

- Rotate all secrets via `infra/scripts/rotate-secrets.sh`.
- DR drill — provision a throwaway VPS, restore latest backup, validate.
- Cost review (see `docs/deployment/cost-tracking.md`).

---

## Section 4 — Scaling

| Trigger | Action |
|---|---|
| CPU > 70% sustained on backend | `docker compose ... scale backend=4` (current limit is 2 in prod.yml) |
| DB connections >70% sustained | Deploy PgBouncer (Phase 3 task) |
| Disk > 70% on /srv | Add Hetzner volume, mount at `/srv/forex-bot/data` |
| 50 active live users | Provision second Windows VPS for MT5 |
| 100 active users | Move from CX31 to CX41 (1 CPU step up) |

### Vertical first, horizontal second

Hetzner makes vertical scaling cheap (one click in the panel + reboot).
Horizontal Postgres is complex (Citus, partitioning) — postpone until we
have >500 paying users.

---

## Section 5 — Communication

- **Incident channel:** `#incidents` (Slack)
- **Status page:** https://status.forexbot.example.com (better-stack.com)
- **On-call rotation:** PagerDuty schedule "forex-bot-oncall"
- **User-facing notice for >10 min outage:** post in app banner via
  `feature_flags.outage_banner_enabled = true` in admin panel.
