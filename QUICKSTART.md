# Forex Bot — Quickstart

## Pick your path

| I want to... | Time | Cost | Where |
|---|---|---|---|
| **Try it on my laptop** | 5 min | $0 | This file, [Phase 1](#phase-1--dev) below |
| **Deploy to Vercel + Railway (cloud, paper)** | 15 min | $15–25/mo | [15-Minute Deploy](docs/deployment/15-minute-deploy.md) |
| **Deploy to Vercel + Railway + Windows VPS (cloud, live)** | 45 min | $30–40/mo | [DEPLOY.md](DEPLOY.md) |
| **Self-host on a single Linux VPS** | half-day | $20–30/mo | [Phase 2](#phase-2--production-deploy) below + `make deploy-prod` |

All four paths share 100% of the application code — only the infrastructure
differs. The "honest status" of every feature is in [STATUS.md](STATUS.md).

**Strategy catalog (as of Phase 3): 7 strategies** —
`london_breakout`, `ny_killzone`, `ema_adx`, `ema_rsi`, `donchian`, `grid`,
plus `tv_signal` (TradingView multi-TF follow). `tv_signal` is **paper-only by
default** and requires the Argus "Section TV launch checklist" sign-off before
any instance can be flipped live. Set `TV_ENABLED=false` to hide the strategy
entirely.

---

### Path 1 details — Laptop dev

```bash
cd projects/forex-bot
./scripts/dev.sh
open http://localhost:3000
```

Login `admin@local / changeme123` for a generic dev account, **or** copy `.env.admin.example` → `.env.admin` (gitignored) with your own `ADMIN_EMAIL` + `ADMIN_PASSWORD`; `scripts/dev.sh` reads it and runs `python -m scripts.seed_admin --from-env` idempotently. **Admin panel** is at `/admin` and is role-gated — set TOTP first via `/settings/security` because destructive ops require step-up TOTP. Full guide: [docs/admin-setup.md](docs/admin-setup.md). Continue reading [Phase 1 below](#phase-1--dev) for prereqs and troubleshooting.

### Path 2 details — Vercel + Railway (15 min)

Push to GitHub, click deploy on Railway, click deploy on Vercel, paste env vars. The whole walkthrough is in [docs/deployment/15-minute-deploy.md](docs/deployment/15-minute-deploy.md). Use [.env.deploy-checklist.md](.env.deploy-checklist.md) as a printable worksheet.

**Admin bootstrap on Railway:** set `ADMIN_EMAIL` + `ADMIN_PASSWORD` + `ADMIN_FULL_NAME` + `ADMIN_COUNTRY` in the Railway env panel, then in the Railway shell run `python -m scripts.seed_admin --from-env`. Sign in, rotate password at `/settings/security`, enable TOTP. Full guide: [docs/admin-setup.md](docs/admin-setup.md).

### Path 3 details — Cloud + live trading

[DEPLOY.md](DEPLOY.md) covers the full hybrid setup: Vercel frontend + Railway backend + Windows VPS for MT5 + Tailscale/Cloudflare Tunnel + Stripe + Resend + custom domain.

### Path 4 details — Self-host

Phase 2 below. Single Linux VPS, Docker Compose + Caddy + Let's Encrypt + observability stack. See also [docs/deployment/deployment-architecture.md](docs/deployment/deployment-architecture.md).

---

---

## Phase 1 — Dev

### Prerequisites

- **Docker Desktop** (4.x or newer) — running before you start.
- **~4 GB RAM free** for the Docker engine.
- **openssl** on your PATH (macOS/Linux ship with it; on Windows use WSL).
- **Free ports** on localhost:
  - `3000` Next.js
  - `8000` FastAPI
  - `8500` MT5 bridge stub
  - `5432` PostgreSQL
  - `6379` Redis
  - `9090` Prometheus
  - `3001` Grafana

If any are occupied, stop the conflicting service or change ports in
`infra/docker-compose.override.yml`.

### Three commands

```bash
git clone <repo>            # or just cd into the existing checkout
cd forex-bot
./scripts/dev.sh            # one-shot: env, build, migrate, seed, smoke
```

That's it.

### What to expect after `dev.sh`

After 3–8 min on first build, ~30 s on subsequent runs:

```
  Open:        http://localhost:3000
  Login:       admin@local / changeme123
  API:         http://localhost:8000/docs   (OpenAPI Swagger)
  Grafana:     http://localhost:3001        (admin / admin-dev)
  Prometheus:  http://localhost:9090
```

The default admin password is dev-only. Change it from Settings on first login.

### Phase 1 troubleshooting

#### "Port already in use"
```bash
lsof -i :3000        # find the culprit
# stop the offender, or change the port in infra/docker-compose.override.yml
```

#### "docker daemon not running"
Open Docker Desktop and wait until the whale icon settles. Then re-run
`./scripts/dev.sh`.

#### First build very slow
Normal — backend pulls Python wheels for numpy/pandas/vectorbt; trading-engine
downloads scientific stack. Subsequent builds are cached.

#### "postgres did not become healthy within 90s"
```bash
make logs SVC=postgres
docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml down -v
./scripts/dev.sh              # try again with a clean volume
```

#### Migration failed
```bash
make logs SVC=backend
# Look for "alembic upgrade head" output
make down                     # tears down, keeps volumes
make down-volumes             # destructive: wipes data — use only in dev
./scripts/dev.sh
```

#### "401 Unauthorized" after login
Token may have expired during a slow first compile. Sign out, sign in again.
If it persists, check `make logs SVC=backend` for `decode_token` errors and
verify `.env` has matching `JWT_SECRET_KEY`.

#### Email link in console doesn't work
Phase 1 default is `EMAIL_PROVIDER=console` — the worker logs rendered emails
instead of sending. Copy the verify link from `make logs SVC=email-worker`.

---

## Phase 2 — Production deploy

> Read this whole section before running any commands. Going live with real
> money requires every step.

### Pre-requisites

| What | Why | Cost (USD) |
|---|---|---|
| **Linux VPS** (4 vCPU, 8 GB RAM, 80 GB SSD, Ubuntu 24.04) | Backend / DB / observability | $20–40 / mo |
| **Windows VPS** (2 vCPU, 4 GB RAM, RDP access) | MT5 terminal + bridge — **MetaTrader 5 does not run on Linux** | $15–25 / mo |
| **Domain name** | Caddy needs a hostname for Let's Encrypt | $10 / yr |
| **Cloudflare account (free)** | DNS, R2 (backups), Access (Grafana SSO) | $0 |
| **Stripe account** | Billing | $0 + per-tx fee |
| **Resend / SES / Postmark** | Transactional email | ~$0 at MVP volume |
| **Tailscale account (free)** | Private mesh between Linux and Windows VPS | $0 |
| **Time** | First setup, end-to-end | ~6–8 hours |

### Step 1 — Provision the Linux VPS

```bash
# On your laptop, ssh into the freshly-spun VPS as root, then:
bash infra/scripts/setup-vps.sh
```

The script installs Docker, configures the firewall, creates the deploy user
(uid 1000), and writes `/srv/forex-bot/data/{postgres,redis,prometheus,...}`
with correct ownership.

### Step 2 — DNS + Cloudflare

1. Point `A` records for `forexbot.example.com`, `api.forexbot.example.com`,
   `grafana.forexbot.example.com` to the Linux VPS IP.
2. Set Cloudflare SSL/TLS mode to **Full (strict)**.
3. (Optional but recommended) enable **Cloudflare Access** in front of
   `grafana.forexbot.example.com` for SSO admin login.

### Step 3 — Secrets

```bash
cd /srv/forex-bot
cp .env.example .env.prod
chmod 600 .env.prod

# Edit .env.prod and fill in:
# DOMAIN, API_DOMAIN, ACME_EMAIL
# POSTGRES_PASSWORD, REDIS_PASSWORD, NEXTAUTH_SECRET, JWT_SECRET_KEY,
#   ENCRYPTION_KEK_BASE64, INTERNAL_API_SECRET, MT5_BRIDGE_TOKEN
#   → generate with: openssl rand -base64 32
# STRIPE_API_KEY, STRIPE_WEBHOOK_SECRET (after step 5)
# EMAIL_PROVIDER=resend (or smtp), RESEND_API_KEY
# CLOUDFLARE_API_TOKEN, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY (after step 4)
# SLACK_WEBHOOK_URL or PAGERDUTY_ROUTING_KEY
```

### Step 4 — Cloudflare R2 for backups

1. R2 dashboard → create bucket `forex-bot-backups`.
2. Account → API Tokens → create token with `Object Read & Write` for the bucket.
3. Paste into `.env.prod`.

### Step 5 — Stripe

1. Stripe dashboard → enable test mode, then live mode.
2. Run on the VPS:
   ```bash
   docker compose -f infra/docker-compose.yml exec backend \
     python -m scripts.stripe_setup
   ```
   It creates Products + Prices and prints the IDs.
3. Paste the IDs into `.env.prod` (`STRIPE_PRICE_PRO_MONTHLY`, etc.).
4. Stripe dashboard → Webhooks → add endpoint
   `https://api.forexbot.example.com/api/v1/billing/webhook` listening for
   `checkout.session.completed`, `invoice.paid`, `customer.subscription.*`.
   Copy the signing secret into `STRIPE_WEBHOOK_SECRET`.

### Step 6 — Deploy

```bash
make deploy-prod        # = docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Caddy will request Let's Encrypt certs on first boot. Watch:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml logs -f caddy
# wait for: "certificate obtained successfully" for each domain
```

Open `https://forexbot.example.com` → you should see the landing page.

### Step 7 — Connect your real MT5 (Windows VPS)

1. RDP into the Windows VPS.
2. Install MetaTrader 5 (your broker's installer — Exness, IC Markets, etc.).
3. Open PowerShell **as Administrator** in the project's `mt5-bridge/` directory
   (clone the repo on the Windows VPS or sync only this folder):
   ```powershell
   .\install.ps1 -BrokerLogin <your-mt5-login> -BrokerServer <your-broker-server>
   ```
   The script:
   - Installs Python 3.12 + `mt5-bridge` package
   - Generates a random `BRIDGE_TOKEN` and prints it ONCE
   - Registers a Windows service `forex-bot-mt5-bridge` listening on `:8500`
4. **Copy the printed token** and paste it into `MT5_BRIDGE_TOKEN` on the
   Linux side (`.env.prod`). Restart: `docker compose ... restart trading-engine`.
5. Install Tailscale on **both** VPSes; verify they can ping each other on
   the Tailscale IP (`100.x.y.z`). Set `MT5_BRIDGE_URL=http://100.x.y.z:8500`
   in `.env.prod`.

### Step 8 — Test the connection

From the Linux side:

```bash
curl -H "Authorization: Bearer $MT5_BRIDGE_TOKEN" \
     http://100.x.y.z:8500/healthz
# → {"status":"ok","mt5":"connected"}
```

In the UI: Settings → Broker Accounts → Add → fill in your MT5 creds → click
"Test Connection". You should see "Connected, balance $X.XX".

---

## Going live for the first time

> All of this is also documented (with sign-off boxes) in
> `docs/security/live-trading-launch-checklist.md`. **Do not skip the checklist.**

1. **Sign Argus's launch checklist.** This requires reviewing the threat model,
   incident-response plan, and regulatory acknowledgments. Block until done.
2. **Verify the gate passes.** UI: Strategy Instance → "Check Live Gate". All
   eight checks must be green:
   - email_verified
   - totp_enabled
   - active_paid_subscription
   - qualifying_backtest (PF > 1.3, MaxDD < 25%)
   - paper_track_record (≥ 14 days, ≥ 10 trades)
   - live_consent_signed
   - broker_min_balance (≥ $500 forex / $200 crypto)
   - kill_switch_clear (no killed instances in last 24h)
3. **Smallest lot first.** Use the UI risk param `lot_size_override = min_lot`
   for the first 24 hours. Watch every trade by hand.
4. **Monitor:** Grafana → Forex Bot Overview → "Live Engine Health". Watch:
   - Heartbeat ≤ 30s old
   - Daily loss < risk budget
   - Open positions ≤ 1 (until you trust the engine)
5. **First-trade procedure:**
   - Click "Start Live" → modal asks for typed confirmation ("I UNDERSTAND")
   - Engine connects to bridge, subscribes to ticks, sits idle until a signal fires.
   - When a signal fires, you see it in the UI within 2s. The engine sends it
     to the bridge; the bridge places the order on MT5; the fill comes back
     within ~500ms (depending on broker).
   - The audit log records: signal → order → fill → P/L.
6. **If anything looks wrong:** click "Kill Switch" in the top bar. The engine
   immediately closes every open position with that strategy's magic number,
   stops the loop, and emits `kill_switch_armed=true`. The instance stays
   killed for 24h before you can restart it.

---

## Phase 2 troubleshooting

### "Stripe webhook 404 / 410"
Caddy routes `/api/v1/billing/webhook` and rewrites `/stripe/webhook`. Make sure
the Stripe dashboard URL is exactly the path you configured. Check
`docker compose logs caddy` for the requested path; check `logs backend` for
`billing_webhook_received`.

### "Migrations did not run on prod"
By design — prod compose does not auto-migrate. Run explicitly:
```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
  exec backend alembic upgrade head
```
Use `alembic current` to confirm head is `0004`.

### "MT5 bridge unreachable"
Tailscale healthy? `tailscale status` on both ends.
Bridge service running on Windows? RDP in, Services.msc → `forex-bot-mt5-bridge`.
Token matches? The Linux `MT5_BRIDGE_TOKEN` must equal the Windows-side
`BRIDGE_TOKEN`.

### "Email not sending in prod"
1. `EMAIL_PROVIDER` set?
2. If SMTP, can the container reach `SMTP_HOST:SMTP_PORT`? Try
   `docker compose exec email-worker python -c "import smtplib; smtplib.SMTP('$SMTP_HOST', $SMTP_PORT)"`.
3. If Resend, is the domain verified in their dashboard? They reject unverified
   `EMAIL_FROM`.

### "401 from `/internal/*` in engine logs"
The HMAC contract uses canonical scheme: `method\npath\nts\nnonce\nbody_sha256`.
Both backend and engine must share `INTERNAL_API_SECRET`. Rotate together; do
NOT change only one side. The backend rejects requests > 60s old (clock skew).

### "I tried to go live but the gate fails on `paper_track_record`"
This is the gate doing its job. You need ≥ 14 days of paper trading on this
instance with ≥ 10 trades. Wait it out. The track record exists for a reason.

### "I want to roll back a bad deploy"
```bash
./infra/scripts/rollback.sh
# Pulls the previous image tag from the rollback marker file and restarts.
```

---

## Cookbook

### Change strategy params on the fly
UI: Dashboard → Strategy Instance → Edit Params. Hot-reload via the engine's
SIGHUP handler.

### Tail backend logs
```bash
make logs SVC=backend
# or in prod:
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml logs -f backend
```

### Restart a single service
```bash
docker compose -f infra/docker-compose.yml restart backend
```

### Run a backtest from the CLI (no UI)
```bash
curl -X POST http://localhost:8000/api/v1/backtests \
  -H "Authorization: Bearer <your token>" \
  -H "Content-Type: application/json" \
  -d '{"strategy_code":"london_breakout","asset_symbol":"XAUUSD",
       "timeframe":"H1","start_date":"2026-05-01","end_date":"2026-06-01"}'
```

### Open a psql shell
```bash
docker compose -f infra/docker-compose.yml exec postgres psql -U forexbot -d forexbot
```

### Run an ad-hoc migration
```bash
docker compose exec backend alembic revision -m "your message"
# edit the generated file
docker compose exec backend alembic upgrade head
```

### Trigger a manual backup
```bash
./infra/scripts/backup-now.sh
# Uploads to R2 bucket; check Cloudflare R2 dashboard.
```

### Restore from backup (drill before you need it)
```bash
./infra/scripts/restore-from-r2.sh <backup-date>
# Read the script first — it WILL wipe the current DB.
```

### Open OpenAPI / Swagger
- Dev: `http://localhost:8000/docs` or `/redoc`
- Prod: `https://api.forexbot.example.com/docs`

### Stop everything
```bash
make down
```

### Factory reset (dev only — destroys all data)
```bash
make down-volumes
./scripts/dev.sh
```

---

## Common Make targets

| Target | What it does |
|---|---|
| `make up` | Same as `./scripts/dev.sh` minus secret rotation |
| `make down` | Stop containers, keep volumes |
| `make down-volumes` | Stop + wipe data — **destructive, dev only** |
| `make logs` | Tail all services |
| `make logs SVC=<name>` | Tail one service |
| `make smoke` | Health checks |
| `make shell-backend` | Bash shell in backend container |
| `make psql` | psql against local Postgres |
| `make migrate` | `alembic upgrade head` |
| `make deploy-prod` | Run compose with the prod overlay |
| `make rollback` | Roll back to the previous image tag |

---

## Where to file a bug

Open an issue with:

```bash
docker --version
docker compose version
./scripts/smoke.sh 2>&1 | tail -50
docker compose -f infra/docker-compose.yml ps
```

…and the symptom. The team monitors `docs/project/risk-register.md` for triage.
