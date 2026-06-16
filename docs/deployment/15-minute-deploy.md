# 15-Minute Deploy — Vercel + Railway (paper mode)

> Opinionated cookbook. Copy-paste the commands. The literal goal is
> "browser → login screen" in 15 minutes, paper-only. MT5 bridge (real
> trading) is a separate 30-minute step covered in
> [mt5-bridge-setup.md](../../mt5-bridge/README.md).

## Time budget

| Step | Time |
|---|---|
| Pre-reqs | 5 min (one-time) |
| 1. Generate secrets | 3 min |
| 2. Railway: project + 4 services | 3 min |
| 3. Railway: migrate + seed | 2 min |
| 4. Vercel: import + env + deploy | 3 min |
| 5. Wire Vercel ↔ Railway | 1 min |
| 6. Stripe webhook + price IDs | 3 min |
| **Total** | **~15 min** (after pre-reqs) |

---

## Pre-requisites (5 min — do these once)

```bash
# 1. Push the repo to GitHub.
cd projects/forex-bot
git remote add origin https://github.com/<you>/forex-bot.git
git push -u origin main

# 2. Create accounts (free tier OK on all three).
open https://vercel.com/signup     # SSO with GitHub
open https://railway.app/login     # SSO with GitHub — credit card required for free credit
open https://dashboard.stripe.com  # test-mode is fine to start

# 3. Verify openssl on your laptop (macOS ships with it).
openssl version
```

---

## Step 1 — Generate secrets (3 min)

Run this on your laptop and **keep the output in a password manager**. You will
paste each one into Railway / Vercel dashboards in the next steps.

```bash
echo "JWT_SECRET_KEY        = $(openssl rand -base64 32)"
echo "ENCRYPTION_KEK_BASE64 = $(openssl rand -base64 32)"
echo "INTERNAL_API_SECRET   = $(openssl rand -base64 32)"
echo "NEXTAUTH_SECRET       = $(openssl rand -base64 32)"
echo "SEED_ADMIN_PASSWORD   = $(openssl rand -base64 18)"
```

> All five are independent — never reuse them. `ENCRYPTION_KEK_BASE64` must
> be exactly the output of `openssl rand -base64 32` (which is a 44-char
> base64 string of 32 raw bytes — the validator in `app/core/config.py`
> enforces this).

---

## Step 2 — Railway: project + 4 services (3 min)

1. https://railway.app/new → **Deploy from GitHub Repo** → pick your `forex-bot` fork.
2. Railway creates the project + first service (it picks the first `nixpacks.toml` it sees — adjust below).
3. **Service A — backend:**
   - Settings → Source → **Root Directory: `/backend`**
   - Settings → Networking → **Generate Domain** → note the URL: `backend-production-xxxx.up.railway.app`
4. **Add Postgres:** Click **+ New** → Database → **PostgreSQL**. Wait for "Active".
5. **Add Redis:** Click **+ New** → Database → **Redis**. Wait for "Active".
6. **Service B — trading-engine:** Click **+ New** → GitHub Repo → same repo → Settings → **Root Directory: `/trading-engine`**.
7. **Set shared variables** (Project → Variables → **Shared**). Paste the secrets from Step 1 plus:

   ```
   DATABASE_URL          = ${{Postgres.DATABASE_URL}}
   REDIS_URL             = ${{Redis.REDIS_URL}}
   JWT_SECRET_KEY        = <from step 1>
   ENCRYPTION_KEK_BASE64 = <from step 1>
   INTERNAL_API_SECRET   = <from step 1>
   APP_ENV               = production
   LOG_LEVEL             = INFO
   EMAIL_PROVIDER        = console
   STRIPE_API_KEY        =                       # leave blank for now → offline mode
   SEED_ADMIN_EMAIL      = admin@yourdomain.com
   SEED_ADMIN_PASSWORD   = <from step 1>
   ```

8. **Backend service vars** (Project → backend → Variables):
   ```
   CORS_ORIGINS       = https://placeholder.vercel.app    # update in Step 5
   FRONTEND_URL       = https://placeholder.vercel.app    # update in Step 5
   BACKEND_PUBLIC_URL = https://${{RAILWAY_PUBLIC_DOMAIN}}
   ```
9. **Trading-engine service vars** (Project → trading-engine → Variables):
   ```
   BACKEND_INTERNAL_URL = http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000
   ENGINE_MODE          = paper
   MT5_BRIDGE_URL       = http://mt5-bridge-stub:8500   # placeholder until you do MT5 setup
   MT5_BRIDGE_TOKEN     = paper-mode-no-bridge-needed
   ```
10. Wait ~3 min for both services to reach **Active**. (Builds typically 90–180s once Nixpacks is warm.)
11. Smoke: open `https://<backend-railway-url>/healthz` → expect `{"status":"ok"}`.

---

## Step 3 — Railway: migrate + seed (2 min)

Railway dashboard → backend service → top-right **"…"** → **Open in Terminal**:

```bash
alembic upgrade head            # runs migrations 0001..0004
python -m scripts.seed_admin    # creates admin user, prints credentials ONCE
```

Copy the email + password from the output. You will use them to log in in
Step 6.

---

## Step 4 — Vercel: import + env + deploy (3 min)

1. https://vercel.com/new → **Import** → pick your GitHub repo.
2. Configure:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Next.js (auto-detected)
   - Build / Install commands: leave default (uses `frontend/vercel.json`).
3. **Environment Variables** (Production scope):
   ```
   NEXT_PUBLIC_API_URL  = https://<backend-railway-url>/api/v1
   NEXT_PUBLIC_WS_URL   = wss://<backend-railway-url>/ws
   NEXT_PUBLIC_BASE_URL = https://<your-vercel-url-after-deploy>
   NEXTAUTH_URL         = https://<your-vercel-url-after-deploy>
   NEXTAUTH_SECRET      = <from step 1>
   NEXT_PUBLIC_DEV_MODE = false
   ```
   > Don't worry — you don't know the Vercel URL yet. Use a placeholder and update in Step 5.
   >
   > **Critical:** the `/api/v1` suffix on `NEXT_PUBLIC_API_URL` is required.
   > Forgetting it = every API call returns 404.

4. Click **Deploy**. Wait ~2 min.
5. Note the production URL: `https://forex-bot-frontend-xxx.vercel.app`.

---

## Step 5 — Wire Vercel ↔ Railway (1 min)

Now that both URLs exist, link them together:

1. **Vercel** → Project → Settings → Environment Variables → edit:
   - `NEXT_PUBLIC_BASE_URL = https://<your-vercel-url>`
   - `NEXTAUTH_URL = https://<your-vercel-url>`
   - → Deployments → latest → **"…"** → Redeploy.
2. **Railway** → backend service → Variables → edit:
   - `CORS_ORIGINS = https://<your-vercel-url>`
   - `FRONTEND_URL = https://<your-vercel-url>`
   - Railway redeploys automatically.

> The CORS regex in Atlas accepts ANY `*.vercel.app` URL (preview branches
> included) by default. The exact CORS_ORIGINS is the canonical primary;
> the regex covers previews.

---

## Step 6 — Stripe webhook + price IDs (3 min)

Skip this section if you're not enabling billing yet — the backend boots fine
with `STRIPE_API_KEY=""` (offline mode).

1. **Stripe Dashboard** → Developers → **Webhooks** → Add endpoint.
   - URL: `https://<backend-railway-url>/api/v1/billing/webhook`
   - Listen for: `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`
   - Copy the **Signing secret** (`whsec_*`).
2. **Railway** → backend → Variables → add:
   ```
   STRIPE_API_KEY        = sk_test_...   # or sk_live_... once you go live
   STRIPE_WEBHOOK_SECRET = whsec_...
   ```
3. **Provision price IDs** (Railway shell):
   ```bash
   python -m scripts.stripe_setup
   ```
   Copy the printed `STRIPE_PRICE_*` IDs back into Railway variables.

---

## You are live (paper mode)

Open `https://<your-vercel-url>`. Click **Login** → email = `admin@yourdomain.com` (or whatever you set), password = the one printed in Step 3.

**Immediately:**
1. Settings → **Change password** (the seed one is now in your terminal scrollback).
2. Settings → **Email verification** → click the verify link (in `console` mode, it'll be in `email-worker` logs on Railway).
3. Settings → **Enable 2FA** (TOTP).

Try a backtest:
- Strategies → London Breakout → Create backtest → XAUUSD H1, 2026-05-01 → 2026-06-01.
- Results appear in ~10s. Confirms backend + DB + sample-data pipeline is alive.

---

## What's still manual

| Step | When | Where |
|---|---|---|
| Custom domain on Vercel | Optional | Vercel → Settings → Domains |
| Custom domain on Railway | Optional | Railway → backend → Settings → Networking |
| MT5 bridge on Windows VPS | Before live trading | `mt5-bridge/install.ps1` on Windows |
| Tailscale or Cloudflare Tunnel for MT5 | Before live trading | See `docs/deployment/cloudflare-setup.md` § Tunnel |
| Real email provider (`EMAIL_PROVIDER=resend`) | Before opening to users | Railway → Variables |
| Real Stripe products + prices | Before opening to users | `python -m scripts.stripe_setup` (Railway shell) |
| Sentry DSN | Before opening to users | `SENTRY_DSN=...` in Railway variables |
| Backups beyond Railway's 7-day plugin retention | Before going live | `R2_*` env vars + nightly cron |
| Partition maintenance cron | After first month | Railway → backend service → Cron schedule |
| Going-live gate sign-off | Before flipping `ENGINE_MODE=live` | `docs/security/live-trading-launch-checklist.md` |

---

## Total cost (after these 15 minutes)

| Component | Cost/mo |
|---|---|
| Vercel Hobby | $0 |
| Railway 4 services + 2 plugins | ~$15–25 |
| Stripe | $0 + 2.9% per transaction |
| Domain (optional) | ~$1 |
| **You're paying** | **$15–26/mo** for the SaaS, paper-only. |

MT5 bridge on Contabo Windows VPS adds **$14.50/mo** when you're ready for real
trading. See `DEPLOY.md` § Section 6.

---

## Troubleshooting the deploy

**"Application error: a client-side exception"** on the Vercel page → Open
DevTools Console. Most likely `NEXTAUTH_SECRET` is unset for the current
deployment scope.

**Every API call returns 404** → Did you forget `/api/v1` on
`NEXT_PUBLIC_API_URL`? Open DevTools → Network → inspect the URL.

**"CORS error: blocked by CORS policy"** → `CORS_ORIGINS` on Railway must
match the Vercel URL exactly (no trailing slash). The default regex covers
`*.vercel.app` previews automatically.

**"Database connection failed"** → Confirm Postgres plugin is **Active**, not
just present. Click into the plugin → Status should be green.

**Backend boots but `/healthz` returns 500** → Open backend service Logs in
Railway. Most likely missing required env var like `JWT_SECRET_KEY`.

**Stripe webhook returns 401** → `STRIPE_WEBHOOK_SECRET` doesn't match what
Stripe is signing with. Re-fetch from Stripe Dashboard → Webhooks → reveal.

---

## Next steps

- [DEPLOY.md](../../DEPLOY.md) — full Vercel + Railway + MT5 deploy with
  custom domains and live trading.
- [docs/security/live-trading-launch-checklist.md](../security/live-trading-launch-checklist.md)
  — mandatory before flipping `ENGINE_MODE=live`.
- [.env.deploy-checklist.md](../../.env.deploy-checklist.md) — printable
  worksheet listing every variable and where to set it.
