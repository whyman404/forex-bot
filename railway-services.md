# Railway Services Template — Forex Bot

> Monorepo on Railway: 4 services + 2 plugins, single project.
> Owner: Hestia Kaoru (DevOps).
> All env vars are inheritable via "Shared Variables" at the project level.

---

## Project layout

```
forex-bot-prod (Railway project)
├── backend                 [service]  Nixpacks → Procfile web
├── backend-email-worker    [service]  Same repo, Procfile email_worker
├── backend-backtest-worker [service]  Same repo, Procfile backtest_worker
├── trading-engine          [service]  Nixpacks → server.py (hosts LiveEngine threads in-process)
├── postgres                [plugin]   Railway-managed Postgres 16
└── redis                   [plugin]   Railway-managed Redis 7
```

Total: **4 services + 2 plugins = ~$5–25/month** depending on traffic.

> **Why no separate live-engine worker?** The trading-engine web service hosts
> `LiveEngine` instances in-process via `live/router.py` (one thread per
> running strategy instance). A second worker process would diverge from
> the in-process registry. Pin `trading-engine` to `numReplicas=1` (already
> set in `trading-engine/railway.json`). Phase 3 will split this out.

---

## Service 1 — `backend` (web)

| Setting | Value |
|---|---|
| Source | GitHub repo |
| Root directory | `/backend` |
| Builder | Nixpacks (auto-detected from `nixpacks.toml`) |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (from `Procfile` web) |
| Custom start (override) | leave blank — Procfile wins |
| Healthcheck path | `/healthz` |
| Restart policy | ON_FAILURE, 10 retries |
| Region | `asia-southeast1` (Singapore) — closest to MT5 Bridge if in Asia |
| Public networking | Generate domain → `backend-production-xxxx.up.railway.app` |

### Required env vars (mark as "shared" so workers inherit)
```
DATABASE_URL          = ${{Postgres.DATABASE_URL}}   # reference plugin
REDIS_URL             = ${{Redis.REDIS_URL}}
JWT_SECRET_KEY        = <openssl rand -base64 32>
ENCRYPTION_KEK_BASE64 = <openssl rand -base64 32>
NEXTAUTH_SECRET       = <openssl rand -base64 32>
INTERNAL_API_SECRET   = <openssl rand -base64 32>
CORS_ORIGINS          = https://<your-app>.vercel.app
FRONTEND_URL          = https://<your-app>.vercel.app
BACKEND_PUBLIC_URL    = https://${{RAILWAY_PUBLIC_DOMAIN}}
APP_ENV               = production
LOG_LEVEL             = INFO
STRIPE_API_KEY        = sk_live_xxx
STRIPE_WEBHOOK_SECRET = whsec_xxx
EMAIL_PROVIDER        = resend
RESEND_API_KEY        = re_xxx
MT5_BRIDGE_URL        = http://<tailscale-ip>:8500
MT5_BRIDGE_TOKEN      = <from Windows install.ps1>
```

---

## Service 2 — `backend-email-worker`

Same repo + same root directory. Override the start command:

```
python -m app.workers.email_worker
```

- No healthcheck (worker, not HTTP)
- No public networking
- Inherits all shared env vars from `backend`
- 1 replica is fine for ≤ 1000 emails/day

---

## Service 3 — `backend-backtest-worker`

Same repo + same root directory. Override the start command:

```
rq worker backtest --url $REDIS_URL
```

- No healthcheck
- No public networking
- Can scale to 2–3 replicas if users run many backtests
- Inherits shared env

---

## Service 4 — `trading-engine` (web)

| Setting | Value |
|---|---|
| Source | Same GitHub repo |
| Root directory | `/trading-engine` |
| Builder | Nixpacks |
| Start | `uvicorn server:app --host 0.0.0.0 --port $PORT` |
| Healthcheck | `/healthz` |
| Internal port | exposed via `$PORT` |

### Required env vars
```
DATABASE_URL          = ${{Postgres.DATABASE_URL}}
REDIS_URL             = ${{Redis.REDIS_URL}}
INTERNAL_API_SECRET   = ${{backend.INTERNAL_API_SECRET}}
BACKEND_INTERNAL_URL  = http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000
ENGINE_MODE           = paper                # paper until gate passes
MT5_BRIDGE_URL        = http://<tailscale-ip>:8500
MT5_BRIDGE_TOKEN      = ${{backend.MT5_BRIDGE_TOKEN}}
DEFAULT_RISK_PCT      = 1.0
DEFAULT_RR            = 1.5
```

> Use `${{backend.VAR}}` to reference another service's env var — Railway resolves this automatically.

---

## Plugin 1 — Postgres

Railway dashboard → **+ New** → Database → **PostgreSQL**.
- Plan: Hobby ($5/mo) is fine for first 1000 users.
- Auto-injects `DATABASE_URL`, `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`, `PGPORT`.
- Connection format: `postgresql://user:pass@host:port/db` — Atlas's `_normalize_database_url()` auto-converts to `postgresql+asyncpg://...`.
  - In the backend service, simply set: `DATABASE_URL=${{Postgres.DATABASE_URL}}`

### Daily backup
Railway plugin does daily backups automatically (7-day retention on Hobby). For longer retention or off-Railway copy, add a cron job that runs `pg_dump | gzip | aws s3 cp -` to R2.

---

## Plugin 2 — Redis

Railway dashboard → **+ New** → Database → **Redis**.
- Plan: Hobby ($5/mo).
- Auto-injects `REDIS_URL` and `REDIS_PRIVATE_URL`.
- Use `REDIS_PRIVATE_URL` for internal service-to-service (no egress cost).

---

## Variable inheritance + linking

Railway has 3 levels (highest precedence first):
1. **Service variables** — set per service
2. **Shared variables** — set at project level, all services see them
3. **Reference variables** — `${{Service.VAR}}` cross-service references

### Best practice
- Put secrets (`JWT_SECRET_KEY`, `STRIPE_*`, `RESEND_API_KEY`) as **shared** so workers automatically inherit
- Use `${{Postgres.DATABASE_URL}}` style for plugin URLs — auto-rotates if plugin restarts
- Set `RAILWAY_RUN_UID=0` on backend if you need to write to non-standard paths (default is unprivileged)

---

## Deploy order

1. Create project + Postgres plugin + Redis plugin.
2. Create `backend` service from GitHub (root `/backend`).
3. Set shared env vars at project level.
4. Wait for first build to succeed, run release: `railway run alembic upgrade head` (or use Railway's release-phase script).
5. Create `backend-email-worker` + `backend-backtest-worker` from same repo (clone the backend service in dashboard, override start command).
6. Create `trading-engine` service (root `/trading-engine`).
7. Generate public domain on `backend` → copy URL → put into Vercel's `NEXT_PUBLIC_API_URL`.
8. Update `CORS_ORIGINS` on backend with the Vercel URL.

---

## Cost estimate (Hobby plan)

| Service | Resource | $/mo |
|---|---|---|
| backend web | 0.5 vCPU / 512 MB / always-on | ~$5 |
| email worker | 0.25 vCPU / 256 MB | ~$2 |
| backtest worker | 0.5 vCPU / 512 MB (bursts) | ~$2–5 |
| trading-engine | 0.5 vCPU / 512 MB | ~$5 |
| Postgres plugin | Hobby (1 GB) | $5 |
| Redis plugin | Hobby (100 MB) | $5 |
| **Total** | | **~$24–27/mo** |

> Tip: Railway gives $5 free credit each month — first ~$20/month is effectively your actual spend.
