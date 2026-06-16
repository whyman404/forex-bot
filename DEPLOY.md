# DEPLOY — Hybrid Cloud (Vercel + Railway + MT5 Bridge)

> 30-minute deploy: Vercel frontend + Railway backend + managed Postgres/Redis
> + Windows VPS for MT5. Total cost ~$25–40/mo for the first 50 users.
>
> Alternative self-host on a single Linux box: see `QUICKSTART.md` → Phase 2.
> Both paths use the same code and `.env` — only the infra differs.

---

## One-click deploy buttons

### Frontend on Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/whyman404/forex-bot&project-name=forex-bot-frontend&framework=nextjs&root-directory=frontend&env=NEXT_PUBLIC_API_URL,NEXTAUTH_SECRET,NEXTAUTH_URL&envDescription=Railway%20backend%20URL%20%2B%20%2Fapi%2Fv1%2C%2032-char%20random%20secret%2C%20same%20as%20Vercel%20URL&envLink=https://github.com/whyman404/forex-bot/blob/main/docs/deployment/env-variables.md)

### Backend on Railway

Railway doesn't publish public "deploy templates" for monorepos with multiple services. Use **"Deploy from GitHub Repo"** instead:

1. https://railway.app/new → "Deploy from GitHub Repo" → pick `forex-bot`.
2. After project is created, add 3 more services from same repo (backend-worker x2, trading-engine) — see `railway-services.md` for the full template.

---

## Architecture

```
        ┌────────────────────────┐
        │  Vercel (Edge + SSR)   │   Next.js 15 + NextAuth
        │  *.vercel.app          │
        └────────────┬───────────┘
                     │ HTTPS (NEXT_PUBLIC_API_URL)
                     ▼
        ┌────────────────────────┐
        │       Railway          │
        │  ┌──────────────────┐  │
        │  │ backend (web)    │  │   FastAPI ─ /api/v1/*
        │  │ email-worker     │  │   APScheduler / rq
        │  │ backtest-worker  │  │   rq worker
        │  │ trading-engine   │  │   FastAPI /healthz, signals
        │  └──────────────────┘  │
        │  ┌──────────────────┐  │
        │  │ Postgres plugin  │  │   (or Neon)
        │  │ Redis plugin     │  │   (or Upstash)
        │  └──────────────────┘  │
        └───────────┬────────────┘
                    │ HTTPS via Tailscale (100.x.y.z)
                    ▼
        ┌────────────────────────┐
        │  Windows VPS (Contabo) │   MT5 bridge :8500
        │  - MetaTrader 5        │   + Tailscale node
        │  - mt5-bridge service  │
        └────────────────────────┘
```

---

## Cost summary

| Component | Provider | $/mo |
|---|---|---|
| Frontend | Vercel Hobby | **$0** (≤ 100 GB BW) |
| Backend (4 services) | Railway Hobby | $15–20 |
| Postgres | Railway plugin **or** Neon | $5 / $0 free tier |
| Redis | Railway plugin **or** Upstash | $5 / $0 free tier |
| Windows VPS | Contabo "Windows VPS S" | $14.50 |
| Domain | Cloudflare Registrar | ~$1 (annual ÷ 12) |
| **Total** (all Railway) | | **~$36/mo** |
| **Total** (Neon+Upstash) | | **~$30/mo** |

> Railway gives $5 free credit each month → effective cost ~$25–31/mo.

---

## What you need ready before clicking deploy

- [ ] GitHub account + repo pushed to `main`
- [ ] Vercel account (free, GitHub SSO)
- [ ] Railway account (free, GitHub SSO) + a credit card on file (required even for free credit)
- [ ] Stripe account (test mode is fine to start)
- [ ] Resend or SES account for email
- [ ] Contabo (or Windows VPS provider) — purchase Windows VPS in advance
- [ ] MT5 broker login (Exness, IC Markets, etc.)
- [ ] Tailscale account (free)
- [ ] Cloudflare account if you want a custom domain (free)
- [ ] `openssl` installed locally to generate secrets

---

## The 7-step deploy order (target: 30 min, excluding Windows VPS provisioning)

1. **Frontend on Vercel** (5 min) — get a placeholder URL
2. **Railway backend + DB + Redis** (10 min) — get a backend URL
3. **Migrations + seed** (3 min) — via Railway shell
4. **Wire backend URL back into Vercel** (2 min) — set `NEXT_PUBLIC_API_URL` + redeploy
5. **Stripe webhook URL** (2 min)
6. **(Optional) Windows MT5 bridge + Tailscale** (30 min — can be done after launch if running paper-only)
7. **Smoke test + first login** (5 min)

---

## Section 1 — Vercel frontend (5 min)

1. Push repo to GitHub.
2. https://vercel.com/new → Import Git Repository → pick `forex-bot`.
3. Vercel auto-detects Next.js. Set:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Next.js (auto)
   - **Build Command:** leave default (uses `vercel.json` → `pnpm build`)
   - **Install Command:** leave default (`pnpm install --frozen-lockfile`)
4. Environment Variables (Production scope):

   | Key | Value | Notes |
   |---|---|---|
   | `NEXT_PUBLIC_API_URL` | `https://example.com/api/v1` | placeholder — you'll update in step 4 |
   | `NEXTAUTH_SECRET` | `<openssl rand -base64 32>` | 32-char minimum |
   | `NEXTAUTH_URL` | `https://your-app.vercel.app` | use the URL Vercel will give you |
   | `NEXT_TELEMETRY_DISABLED` | `1` | privacy |

5. Click Deploy. Wait ~2 min.
6. Note the production URL: `https://forex-bot-frontend-xxx.vercel.app`.

> The frontend will boot but API calls will fail until step 2.

---

## Section 2 — Railway backend (10 min)

1. https://railway.app/new → Deploy from GitHub Repo → `forex-bot`.
2. **Add Postgres plugin:** `+ New` → Database → PostgreSQL. Wait until status = Active.
3. **Add Redis plugin:** `+ New` → Database → Redis.
4. **Edit backend service:**
   - Settings → Service → **Root Directory:** `/backend`
   - Settings → Service → **Watch Paths:** `/backend/**` (only redeploy on backend changes)
   - Settings → Networking → **Generate Domain** → `backend-production-xxxx.up.railway.app`
5. **Set shared variables** (Project → Variables → "Shared"):
   ```
   DATABASE_URL          = ${{Postgres.DATABASE_URL}}
   # Atlas normalizes postgres:// → postgresql+asyncpg:// at startup, so the
   # plugin reference Just Works. SSL is auto-enabled for Neon hosts.
   REDIS_URL             = ${{Redis.REDIS_URL}}
   JWT_SECRET_KEY        = <openssl rand -base64 32>
   ENCRYPTION_KEK_BASE64 = <openssl rand -base64 32>
   INTERNAL_API_SECRET   = <openssl rand -base64 32>
   CORS_ORIGINS          = https://forex-bot-frontend-xxx.vercel.app
   # The backend ALSO accepts any *.vercel.app preview URL via the built-in
   # cors_allow_origin_regex — no extra config needed for branch previews.
   FRONTEND_URL          = https://forex-bot-frontend-xxx.vercel.app
   APP_ENV               = production
   LOG_LEVEL             = INFO
   EMAIL_PROVIDER        = resend
   RESEND_API_KEY        = re_xxx
   EMAIL_FROM            = noreply@yourdomain.com
   STRIPE_API_KEY        = sk_live_xxx   # or sk_test_xxx
   ```
6. **Clone backend to make workers** (Service menu → Duplicate):
   - `backend-email-worker` → Settings → Start Command = `python -m app.workers.email_worker`
   - `backend-backtest-worker` → Start Command = `rq worker backtest --url $REDIS_URL`
   - Both: turn OFF healthcheck (workers don't serve HTTP).
7. **Add trading-engine service:** `+ New` → GitHub Repo → same repo → Settings → Root Directory = `/trading-engine`.
   - Variables: `INTERNAL_API_SECRET=${{backend.INTERNAL_API_SECRET}}`, `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `REDIS_URL=${{Redis.REDIS_URL}}`, `BACKEND_INTERNAL_URL=http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000`, `ENGINE_MODE=paper`, `MT5_BRIDGE_URL=<placeholder-until-section-6>`, `MT5_BRIDGE_TOKEN=<placeholder>`
   - **Pin numReplicas=1** (already set in `trading-engine/railway.json`). The
     in-process LiveEngine registry would diverge across replicas.
8. Wait for all services to deploy (~5 min total).
9. Verify: open `https://backend-production-xxxx.up.railway.app/healthz` → should return `{"status":"ok"}`.

---

## Section 3 — Migrations + seed (3 min)

> **Migration policy:** Run **manually** via Railway shell (this section), NOT
> auto-on-boot. Atlas exposes `RUN_MIGRATIONS_ON_BOOT=true` for emergencies,
> but it makes failures harder to diagnose and turns every cold-start into a
> migration attempt. Visibility > convenience.

Railway dashboard → backend service → top right "..." → **Open in Terminal** (browser shell).

```bash
alembic upgrade head
python -m scripts.seed_admin
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade -> 0004, ...
seed_admin: created admin@yourapp.com  (pw printed once — copy it)
```

Alternative: use Railway CLI from your laptop:
```bash
brew install railwayapp/railway/railway
railway login
railway link
railway run --service backend alembic upgrade head
railway run --service backend python -m scripts.seed_admin
```

### Scheduled jobs (partition maintenance, GDPR purge)

Railway has built-in cron via the **"Cron schedule"** field on a service. Two
maintenance jobs need scheduling once the deploy is stable:

| Job | Command | Cadence | Why |
|---|---|---|---|
| Partition maintenance | `python -m scripts.maintain_partitions` | `0 2 * * *` (02:00 UTC daily) | Pre-create next-month partitions for audit_log / trades |
| GDPR hard-purge | `python -m scripts.hard_purge_account_deletions` | `0 3 * * *` (03:00 UTC daily) | Drain `account_deletions.scheduled_purge_at` queue (Phase 2.1 — script TBD) |

Set up: Railway → backend service → Settings → **Cron schedule** field. (Or
add an external cron-job.org webhook calling an internal admin endpoint.)

---

## Section 4 — Wire Vercel ↔ Railway (2 min)

1. Back in Vercel → Project → Settings → Environment Variables → edit `NEXT_PUBLIC_API_URL`:
   ```
   NEXT_PUBLIC_API_URL = https://backend-production-xxxx.up.railway.app/api/v1
   ```
2. Deployments → latest → "..." → Redeploy (or push any commit to main).
3. Visit `https://your-app.vercel.app` → login screen should appear.

Common pitfall: **forgetting `/api/v1` suffix**. Backend mounts routers under this prefix.

---

## Section 5 — Stripe webhook URL (2 min)

1. Stripe Dashboard → Developers → Webhooks → **Add endpoint**.
2. URL: `https://backend-production-xxxx.up.railway.app/api/v1/billing/webhook`
3. Listen for: `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`.
4. Copy the **Signing secret** (`whsec_...`).
5. Railway → backend → Variables → `STRIPE_WEBHOOK_SECRET=whsec_...`.
6. Provision price IDs:
   ```bash
   railway run --service backend python -m scripts.stripe_setup
   ```
   Paste the printed `STRIPE_PRICE_PRO_MONTHLY`, etc. into Railway variables.

---

## Section 6 — Windows MT5 bridge (30 min — optional until going live)

> Skip this section if you're staying paper-only for the first 14 days.
> The going-live gate requires 14 days of paper trading anyway.

### Provision Contabo Windows VPS

1. https://contabo.com → Windows VPS S ($14.50/mo, 2 vCPU, 8 GB RAM, Windows Server 2022).
2. After ~10 min, you'll receive RDP credentials by email.

### Install MT5 + bridge

1. RDP into the Windows VPS.
2. Install **MetaTrader 5** from your broker's website (Exness, IC Markets, etc.). Log in to your broker account inside MT5.
3. Install Git for Windows + Python 3.12 + Tailscale Windows client.
4. Clone the repo:
   ```powershell
   git clone https://github.com/whyman404/forex-bot.git C:\forex-bot
   cd C:\forex-bot\mt5-bridge
   ```
5. Run as **Administrator** in PowerShell:
   ```powershell
   .\install.ps1 -BrokerLogin <your-mt5-login> -BrokerServer <your-broker-server>
   ```
6. The script prints `BRIDGE_TOKEN=...` **once** — copy it.
7. Sign into Tailscale on the Windows machine → note its Tailscale IP (e.g. `100.64.5.10`).

### Wire Tailscale into Railway

Railway services don't run Tailscale directly. Two options:

**Option A — Cloudflare Tunnel (recommended):**
1. On the Windows VPS, install `cloudflared`.
2. `cloudflared tunnel create mt5-bridge` → `cloudflared tunnel route dns mt5-bridge bridge.yourdomain.com`.
3. Run as Windows service.
4. Railway env: `MT5_BRIDGE_URL=https://bridge.yourdomain.com`.

**Option B — Tailscale on Railway (requires Tailscale userspace networking, beta):**
1. In Railway trading-engine service → Variables → `TS_AUTHKEY=tskey-auth-...` (from Tailscale admin → Auth keys → Create reusable, ephemeral).
2. Add `nixPkgs = ["tailscale"]` to `trading-engine/nixpacks.toml` + a start wrapper that runs `tailscaled --tun=userspace-networking --socks5-server=localhost:1055 &` before `uvicorn`.
3. Railway env: `MT5_BRIDGE_URL=http://100.64.5.10:8500`.

**Set the shared secret** in Railway:
```
MT5_BRIDGE_TOKEN = <token printed by install.ps1>
MT5_BRIDGE_MODE  = proxy
```

Verify:
```bash
railway run --service trading-engine curl -H "Authorization: Bearer $MT5_BRIDGE_TOKEN" $MT5_BRIDGE_URL/healthz
# → {"status":"ok","mt5":"connected"}
```

---

## Section 7 — Cloudflare DNS (5 min, optional)

### Vercel custom domain
1. Vercel → Project → Settings → Domains → Add `app.yourdomain.com`.
2. Cloudflare DNS → CNAME `app` → `cname.vercel-dns.com`. Set proxy = **DNS only** (grey cloud).

### Railway custom domain
1. Railway → backend service → Settings → Networking → Custom Domain → `api.yourdomain.com`.
2. Cloudflare DNS → CNAME `api` → the value Railway prints. Set proxy = DNS only.
3. Update Vercel `NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1`.
4. Update backend `CORS_ORIGINS=https://app.yourdomain.com`.
5. Update Stripe webhook URL to use the new domain.

---

## Section 8 — Smoke test + first login (5 min)

1. Open `https://your-app.vercel.app` (or custom domain).
2. Click **Login** → email = the one from `seed_admin`, password = the one printed.
3. Settings → change password.
4. Settings → Email Verification → click the verify link (check `email-worker` logs on Railway if it didn't send).
5. Settings → Enable 2FA (TOTP).
6. Dashboard → should show empty backtests list.
7. Create a backtest → wait ~10s → results should appear. Confirms backtest-worker is alive.
8. Optional: Settings → Broker Account → Add → fill MT5 creds → Test Connection → expect "Connected".

---

## Section 9 — Going live checklist

Before flipping `ENGINE_MODE=live`, complete every box in:
**`docs/security/live-trading-launch-checklist.md`**

Pointer summary:
- All 8 gate checks green (email_verified, totp_enabled, paid_subscription, qualifying_backtest, paper_track_record ≥ 14 days, live_consent_signed, broker_min_balance, kill_switch_clear)
- Argus sign-off on threat model + DR drill
- Hestia sign-off on observability (Grafana dashboard live, PagerDuty paging)
- Smallest-lot-first for first 24h
- Kill switch tested in paper mode

---

## Health check / uptime monitoring (free tier)

Sign up at **https://betterstack.com** or **https://uptimerobot.com** (both have free tiers covering 5–10 endpoints, 1-min checks).

Configure 4 monitors:
| Name | URL | Expected |
|---|---|---|
| Frontend | `https://your-app.vercel.app` | 200 |
| Backend API | `https://api.yourdomain.com/healthz` | 200 |
| Trading Engine | `https://trading-engine-xxx.up.railway.app/healthz` | 200 |
| MT5 Bridge | `https://bridge.yourdomain.com/healthz` (with auth header) | 200 |

Page to your phone via PagerDuty (free for 1 user) or Telegram/Discord webhook.

---

## Cost optimization tips

1. **Vercel:** stay on Hobby. The Pro upgrade ($20/mo) is only worth it past ~100 GB bandwidth/month (≈ tens of thousands of users).
2. **Railway:**
   - Run only `backend (web)` + `email-worker` at first. Skip `backtest-worker` until users actually queue backtests.
   - Use `sleepApplication: true` on the trading-engine if you're not yet running live trades (saves ~$5/mo).
   - Pin services to 0.5 vCPU / 512 MB until metrics show you need more.
3. **Neon:** stay on Free until 0.5 GB exceeded. Branch only when needed.
4. **Upstash:** the 10k commands/day free tier covers the first 50 users easily. The bot caches signals — be sure it's not chatty.
5. **Contabo:** the $14.50 Windows VPS is the absolute minimum. Cheaper alternatives exist (FXVM trial $0 for first week) but pay-as-you-go gets expensive.
6. **Total under $30/mo target** for first 50 users:
   - Vercel: $0
   - Railway: $10–15 (3 services + small Postgres/Redis)
   - Contabo: $14.50
   - Domain: $1
   - **Total: $25.50–30.50/mo**

---

## Production readiness checklist (Vercel + Railway specific)

Before announcing the URL to users:

### Frontend (Vercel)
- [ ] Custom domain attached
- [ ] `NEXTAUTH_URL` matches the custom domain (not `*.vercel.app`)
- [ ] CSP header in `next.config.ts` includes the Railway URL in `connect-src`
- [ ] Preview deployments disabled for `develop` branch (don't leak unpolished features)
- [ ] Vercel Analytics enabled (free Web Vitals)
- [ ] Source maps disabled in prod (`productionBrowserSourceMaps: false`)

### Backend (Railway)
- [ ] All workers showing "Active" — no crash-loop
- [ ] `/healthz` returns 200 in < 200ms
- [ ] `/metrics` Prometheus endpoint protected (require auth or IP allowlist)
- [ ] Alembic head = `0004` confirmed
- [ ] CORS_ORIGINS does NOT include `*` — must be the exact Vercel URL
- [ ] Stripe webhook secret is the LIVE one (not test) if you process real payments
- [ ] Sentry DSN set, errors flowing
- [ ] Rate limits in `RATE_LIMIT_*` env vars match tier expectations

### MT5 Bridge
- [ ] BRIDGE_TOKEN ≥ 32 chars, never logged
- [ ] Tailscale or Cloudflare Tunnel — never expose `:8500` directly to internet
- [ ] Windows VPS auto-update enabled, weekly reboot scheduled outside trading hours
- [ ] MT5 set to auto-login + auto-reconnect

### Data
- [ ] Daily Postgres backup configured (Railway plugin does it automatically; Neon → PITR enabled)
- [ ] Backup restore drill completed at least once (read `infra/scripts/restore-from-r2.sh`)
- [ ] No PII or secrets in CI logs

### Compliance
- [ ] Risk disclaimer modal version matches `RISK_DISCLAIMER_VERSION` env
- [ ] Privacy policy + ToS pages live
- [ ] Audit log retention configured (default 7 years for trading records)

---

## Troubleshooting

### Vercel build fails: "Cannot find module 'next'"
The `installCommand` in `vercel.json` is `pnpm install --frozen-lockfile`. Confirm `frontend/pnpm-lock.yaml` is committed. Run `pnpm install` locally and recommit if needed.

### Vercel: "Application error: a client-side exception has occurred"
Usually missing env var. Check Browser DevTools → Console. Most often `NEXTAUTH_SECRET` is unset — Vercel preview branches don't inherit production env vars by default.

### Railway: build OOM (out of memory)
Nixpacks build phase tries to install vectorbt + backtrader which need C compilation. The Hobby build worker has 8 GB which is enough, but if it OOMs:
1. Add to `nixpacks.toml`: `NIXPACKS_NO_CACHE=1` to avoid double-caching.
2. Or move heavy ML deps to `[project.optional-dependencies]` and install only what `live` mode needs.

### Railway: backend boots but returns 500 on every request
Check logs for `Could not connect to database`. The `DATABASE_URL` from Postgres plugin uses `postgresql://` scheme, but SQLAlchemy async expects `postgresql+asyncpg://`. Override per Section 2 step 5.

### CORS error in browser: "blocked by CORS policy"
Backend's `CORS_ORIGINS` must include the **exact** frontend origin (https + domain, no trailing slash). Check:
```bash
railway run --service backend python -c "from app.core.config import settings; print(settings.CORS_ORIGINS)"
```

### Stripe webhook returns 401
The `STRIPE_WEBHOOK_SECRET` in Railway doesn't match what Stripe is signing with. Re-fetch from Stripe Dashboard → Webhooks → click the endpoint → Reveal signing secret.

### Migration fails on Railway
Railway runs the start command before release-phase tasks. Add `alembic upgrade head` to the `release:` line in `Procfile` and Railway will run it before each deploy. Or run manually via shell (Section 3).

### Trading engine can't reach MT5 bridge
1. Test from a Railway shell: `curl -v $MT5_BRIDGE_URL/healthz`
2. If using Tailscale: confirm both nodes are online (`tailscale status` on Windows).
3. If using Cloudflare Tunnel: confirm `cloudflared` service is running on Windows.
4. Token mismatch? `MT5_BRIDGE_TOKEN` on Railway must equal `BRIDGE_TOKEN` on Windows.

---

## Self-host alternative (not deprecated)

If you prefer a single $20/mo Linux VPS instead of the hybrid setup, the `docker-compose.prod.yml` + `QUICKSTART.md` Phase 2 path still works exactly as before. Choose:

| Path | Pros | Cons |
|---|---|---|
| **Hybrid (this doc)** | Auto-scale, no server admin, free TLS, preview deploys | Vendor coupling, costs grow with traffic |
| **Self-host (QUICKSTART)** | Predictable $25/mo flat, full control | You patch the OS, you debug Caddy, you take pages |

Both paths share 100% of the application code. Switching takes ~1 day of migration.
