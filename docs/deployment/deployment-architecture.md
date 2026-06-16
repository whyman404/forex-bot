# Deployment Architecture

> Owner: Hestia Kaoru (DevOps / SRE)
> Last updated: 2026-06-15
> Related ADR: [ADR-004 Deployment Topology](../architecture/adr/ADR-004-deployment-topology.md)

---

## Overview

Forex Bot Platform splits across two planes:

- **App plane** — Linux VPS — Next.js, FastAPI, Postgres, Redis, observability
- **Trading plane** — Windows VPS — MT5 Bridge + MT5 terminal pool (terminal is Windows-only)

dev runs everything in docker compose with `mt5-bridge-stub` standing in for the
Windows bridge.

---

## Topology (Phase 1–2)

```
                              Internet
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │ Cloudflare (free tier)       │
                   │ - DNS                        │
                   │ - DDoS protection            │
                   │ - WAF basic rules            │
                   │ - Proxied (orange cloud)     │
                   └──────────────┬───────────────┘
                                  │ HTTPS (Cloudflare TLS)
                                  ▼
┌──────────────────────────────────────────────────────────────┐
│ Linux VPS — Hetzner CX31 (Falkenstein, DE)                   │
│ 2 vCPU / 8 GB RAM / 80 GB SSD / ~$15/mo                      │
│                                                              │
│  Caddy (80,443) ─▶ Next.js (3000)                            │
│                 ─▶ FastAPI uvicorn × 4 (8000)                │
│                                                              │
│  Postgres 16, Redis 7, RQ worker, backtest runner            │
│  Prometheus, Grafana, Loki, Promtail                         │
│  pg_dump nightly → Backblaze B2 (~$2/mo)                     │
└──────────────────────┬───────────────────────────────────────┘
                       │ WireGuard tunnel (10.42.0.0/24)
                       │ + mTLS at app layer
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ Windows VPS — Contabo VPS M (DE)                             │
│ 6 vCPU / 16 GB RAM / 400 GB SSD / ~$20/mo                    │
│                                                              │
│  MT5 Bridge (FastAPI, port 9100, VPN-only)                   │
│  MT5 terminal pool — up to ~50 instances (NSSM-managed)      │
│  Trading engine worker (collocated for latency)              │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
                 Exness MT5 server (EU)
```

---

## VPS sizing (Phase 1–4)

| Phase | Linux VPS | Windows VPS | Backup | DNS/CDN | Total / mo |
|-------|-----------|-------------|--------|---------|-----------|
| 1 (<10 users) | Hetzner CX31 $15 | Contabo VPS M $20 | B2 $2 | CF free | **$37** |
| 2 (10–20)     | CX31 $15         | VPS M $20         | B2 $3 | CF free | **$38** |
| 3 (20–100)    | CX41 $30         | 2× VPS M $40      | B2 $5 | CF free | **$75** |
| 4 (100–500)   | Dedicated $80    | 2–3× $120+        | $20   | CF Pro $20 | **$240+** |

**Region:** EU (Falkenstein + Düsseldorf) — Exness server is EU/Cyprus.
Linux ↔ Windows ping should be < 10ms.

---

## DNS plan

Hosted on Cloudflare (Zeus owns the account: `whyman404@gmail.com`):

| Record         | Type  | Target                            | Proxy |
|----------------|-------|-----------------------------------|-------|
| `app.<domain>` | A     | Linux VPS public IP               | yes   |
| `api.<domain>` | A     | Linux VPS public IP               | yes   |
| `grafana.<domain>` | A | Linux VPS public IP               | yes   |
| `<domain>`     | A     | Linux VPS public IP (redir → app) | yes   |
| `_acme-challenge.*` | TXT | Caddy LE DNS-01 if needed       | no    |

The Windows VPS has **no public DNS** — accessed only via WireGuard.

TLS certs: Caddy auto via Let's Encrypt (HTTP-01) — Cloudflare in DNS-only mode
during cert issue, then back to proxied.

---

## Cloudflare config

- **SSL/TLS mode:** Full (Strict) — Caddy provides real cert, CF re-encrypts.
- **WAF:** managed rules on, OWASP core rule set, paranoia level 1.
- **Rate limit:** 100 req/min per IP on `/api/auth/*` (block 10 min).
- **Bot Fight Mode:** on.
- **Page rules:** static cache for `_next/static/*`, `/public/*`.
- **Cache TTL:** 1y for static, bypass for HTML and API.

---

## MT5 Bridge swap procedure (stub → real)

In dev, `mt5-bridge-stub` runs on port 8500 and returns canned responses. In
production we replace it with the real bridge on the Windows VPS:

1. Provision Windows VPS (Contabo) — install MT5, NSSM, Python 3.12.
2. Clone `infra/scripts/setup-windows-vps.md` runbook.
3. Configure WireGuard — Linux=`10.42.0.1`, Windows=`10.42.0.2`.
4. Generate mTLS client cert for backend, server cert for bridge.
5. On Linux VPS, edit `.env`:
   ```
   MT5_BRIDGE_MODE=proxy
   MT5_BRIDGE_URL=http://10.42.0.2:9100
   MT5_BRIDGE_MTLS_CERT=/etc/forex-bot/bridge-client.crt
   MT5_BRIDGE_MTLS_KEY=/etc/forex-bot/bridge-client.key
   ```
6. Remove `mt5-bridge-stub` service from compose (or override with `profiles:
   [dev]` so it does not start in prod compose).
7. Restart backend + trading-engine: `docker compose up -d --no-deps backend
   trading-engine-worker`.
8. Smoke: `curl --cacert ca.crt --cert client.crt --key client.key
   https://10.42.0.2:9100/healthz`.

---

## Backup plan

- **Postgres logical dump** — nightly 03:00 UTC → Backblaze B2 (encrypted).
  Cron on Linux VPS, `infra/scripts/pg-backup.sh` (Phase 2 deliverable).
- **Retention** — 7 daily, 4 weekly, 12 monthly.
- **Test restore** — quarterly DR drill, fresh VPS + last week's dump,
  documented runbook `infra/runbooks/dr-drill.md`.
- **WAL archive** — Phase 2, every 5 min → B2 → RPO 5 min.
- **Volumes** — Hetzner snapshot weekly ($0.012/GB/mo) — best-effort, not the
  primary recovery path.

**RPO:** 1 h (logical dump only) → 5 min once WAL shipping is live.
**RTO:** 4 h (manual VPS provision + restore).

---

## Observability

- **Metrics** — Prometheus scrapes backend `/metrics`, trading engine `:9000`,
  node-exporter, cAdvisor, postgres-exporter, redis-exporter.
- **Dashboards** — Grafana, provisioned from `infra/observability/`. Starter
  dashboard `forex-bot-overview` covers RED + business KPIs.
- **Logs** — Loki + Promtail; structured JSON from backend (structlog),
  Caddy access logs, container stdout.
- **Tracing** — OpenTelemetry SDK in backend + engine, exported via OTLP to
  Tempo (Phase 2). Dev: console exporter.
- **Alerts** — Phase 2; Prometheus → Alertmanager → Discord webhook.
- **Uptime** — UptimeRobot free tier (5 monitors) for `app.<domain>`,
  `api.<domain>/healthz`.

---

## CI/CD

- `.github/workflows/ci.yml` runs on push/PR: backend tests, frontend tests,
  engine tests, docker build, security scan.
- `.github/workflows/deploy.yml` is manually triggered, env: staging | prod.
  Pushes images to GHCR, SSH to VPS, runs migrations, blue-green swap, smoke.
- Rollback path: deploy.yml stores previous `IMAGE_TAG` in `.env.bak`. On
  failure, restore + `docker compose up -d`.

---

## Security posture

- Linux VPS firewall (ufw): allow 22 (admin IPs only), 80, 443; deny all else.
- Windows VPS firewall: RDP only from admin IP; bridge port 9100 only from
  WireGuard CIDR.
- SSH: ed25519 keys only, no password, fail2ban.
- Secrets: stored on VPS in `/etc/forex-bot/.env` (chmod 600, root:forex-bot).
  Rotated quarterly. KEK separate from DB password.
- Container users: all services run non-root (`uid 1000`).
- `JWT_SECRET`, `ENCRYPTION_KEK`, `NEXTAUTH_SECRET`, `STRIPE_SECRET_KEY`
  marked sensitive in GitHub env secrets.

---

## Runbook

See [runbook.md](./runbook.md) for common ops procedures (restart, logs, db
backup/restore, deploy, rollback, kill all bots).

---

## Open items

- [x] ~~Choose Backblaze B2 vs Cloudflare R2 for backup~~ → **R2 chosen** (Phase 2: 2026-06-15) — zero egress, lower TCO at our scale.
- [x] ~~Pick Contabo region~~ → **Düsseldorf**.
- [x] ~~Cloudflare account setup~~ → see `cloudflare-setup.md`.
- [x] ~~UptimeRobot account~~ → migrated to Better Stack (see `status-page.md`).
- [ ] Get Hetzner + Contabo invoices reimbursed under company card

---

## Phase 2 — Production hardening (2026-06-15)

Phase 2 deliverables — Hestia Kaoru:

| Area | Artifact | Path (absolute) |
|---|---|---|
| Compose overrides | prod compose with Caddy, exporters, AM | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/infra/docker-compose.prod.yml` |
| Reverse proxy | Caddyfile + xcaddy build | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/infra/caddy/` |
| Cloudflare | DNS, WAF, cache, tunnel setup | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/docs/deployment/cloudflare-setup.md` |
| Backups | backup/restore/verify scripts | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/infra/backup/` |
| Observability | prod prometheus, alerts, AM, 4 dashboards | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/infra/observability/` + `infra/grafana/dashboards/` |
| Deploy | deploy.sh + rollback.sh | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/scripts/` |
| VPS provisioning | Ubuntu setup + Windows MT5 setup | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/infra/scripts/` |
| Secrets | .env.prod.example + rotation | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/.env.prod.example` + `infra/scripts/rotate-secrets.sh` |
| Docs | runbook, DR, cost tracking, status | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/docs/deployment/` |
| CI | tag-triggered release deploy | `/Users/shinzo/Desktop/whyman404/projects/forex-bot/.github/workflows/deploy-release.yml` |

### Production topology (updated)

```
                              Internet
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │ Cloudflare                   │
                   │ - DNS / proxied              │
                   │ - WAF (managed + custom)     │
                   │ - Rate limit /auth/*         │
                   │ - Cache static               │
                   │ - Bot fight mode             │
                   └──────────────┬───────────────┘
                                  │ HTTPS (Full Strict)
                                  ▼
┌──────────────────────────────────────────────────────────────┐
│ Linux VPS — Hetzner CX31 (Falkenstein, DE)                   │
│                                                              │
│  Caddy (80,443,443/udp) ─▶ Next.js × 2 (3000)                │
│                         ─▶ FastAPI × 2 (8000)                │
│                                                              │
│  Postgres 16 (no host port) — Redis 7 (no host port)         │
│  trading-engine (singleton)                                  │
│  Prometheus + Grafana + Loki + Promtail + Alertmanager       │
│  node-exporter + cAdvisor + postgres/redis-exporter          │
│                                                              │
│  /srv/forex-bot/data/{postgres,redis,prometheus,grafana,loki}│
│  Cron: pg_dump → gzip → R2 (02:00 UTC)                       │
│         verify random backup → throwaway DB (Sunday 04:00)   │
└──────────────────────┬───────────────────────────────────────┘
                       │ Cloudflare Tunnel (recommended)
                       │  or WireGuard (alternate)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ Windows VPS — Contabo VPS M (Düsseldorf, DE)                 │
│ cloudflared service ─▶ MT5 bridge (127.0.0.1:9100)           │
│                     ─▶ MT5 terminal pool (NSSM-managed)      │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
                 Exness MT5 server (EU)
```
