# Environment Variables — Hybrid Deploy Mapping

> Every env var the platform reads, where it's set, and how to generate it.
> Pin this page open when running through `DEPLOY.md`.

Legend:
- **dev** = your laptop (`.env`)
- **railway-backend** = Railway backend service
- **railway-worker** = email-worker + backtest-worker (inherit from backend via shared vars)
- **railway-engine** = trading-engine service
- **vercel** = Vercel frontend

---

## Core

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `APP_ENV` | `development` | `production` | `production` | (n/a) | literal | you |
| `NODE_ENV` | `development` | (n/a) | (n/a) | `production` (auto) | literal | Vercel auto |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `INFO` | (n/a) | literal | you |
| `IMAGE_TAG` | `local` | (n/a — Railway manages) | (n/a) | (n/a) | git sha | CI |

## Database

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://forexbot:forexbot@postgres:5432/forexbot` | `postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}` | same | (n/a) | Railway plugin auto-resolves; for Neon copy from dashboard | you |
| `POSTGRES_USER` | `forexbot` | (auto via plugin) | (auto) | (n/a) | plugin | Railway |
| `POSTGRES_PASSWORD` | `forexbot` | (auto via plugin) | (auto) | (n/a) | plugin | Railway |
| `POSTGRES_DB` | `forexbot` | (auto via plugin) | (auto) | (n/a) | plugin | Railway |

## Redis

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `REDIS_URL` | `redis://redis:6379/0` | `${{Redis.REDIS_URL}}` | same | (n/a) | plugin; Upstash uses `rediss://` | you |

## Secrets (generate with `openssl rand -base64 32`)

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `JWT_SECRET_KEY` | auto by `dev.sh` | `<rand>` | (n/a) | (n/a) | `openssl rand -base64 32` | you, once |
| `JWT_ALGORITHM` | `HS256` | `HS256` | (n/a) | (n/a) | literal | you |
| `ENCRYPTION_KEK_BASE64` | auto | `<rand 32 bytes b64>` | (n/a) | (n/a) | `openssl rand -base64 32` | you, once |
| `ENCRYPTION_KEY_VERSION` | `1` | `1` | (n/a) | (n/a) | literal | you |
| `INTERNAL_API_SECRET` | auto | `<rand>` | **same value** | (n/a) | `openssl rand -base64 32` | you, once — must match across backend + engine |
| `NEXTAUTH_SECRET` | auto | (n/a) | (n/a) | `<rand>` | `openssl rand -base64 32` | you |
| `MT5_BRIDGE_TOKEN` | `PLACEHOLDER...` | `<from install.ps1>` | **same value** | (n/a) | Printed once by mt5-bridge `install.ps1` on Windows | you, copy once |

## URLs (cross-reference)

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `FRONTEND_URL` | `http://localhost:3000` | Vercel URL (with `https://`, no trailing `/`) | (n/a) | (n/a) | from Vercel dashboard | you, step 4 |
| `BACKEND_PUBLIC_URL` | `http://localhost:8000` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | (n/a) | (n/a) | Railway auto | Railway |
| `CORS_ORIGINS` | `http://localhost:3000` | Vercel URL (comma-sep if multiple) | (n/a) | (n/a) | from Vercel | you, step 4 |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | (n/a) | (n/a) | Railway backend URL + `/api/v1` | from Railway | you, step 4 |
| `NEXTAUTH_URL` | `http://localhost:3000` | (n/a) | (n/a) | Vercel URL | from Vercel | you |
| `BACKEND_INTERNAL_URL` | `http://backend:8000` | (n/a) | `http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000` | (n/a) | Railway private DNS | Railway |

## Trading engine

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `ENGINE_MODE` | `paper` | (n/a) | `paper` (start), `live` (after gate) | (n/a) | literal | you |
| `MT5_BRIDGE_URL` | `http://mt5-bridge-stub:8500` | (n/a) | `https://bridge.yourdomain.com` or `http://100.x.y.z:8500` | (n/a) | Cloudflare Tunnel or Tailscale IP | you |
| `MT5_BRIDGE_MODE` | `stub` | (n/a) | `proxy` | (n/a) | literal | you |
| `BACKTEST_DATA_DIR` | `/app/data` | (n/a) | `/app/data` | (n/a) | literal | you |
| `DEFAULT_RISK_PCT` | `1.0` | (n/a) | `1.0` | (n/a) | literal | you |
| `DEFAULT_RR` | `1.5` | (n/a) | `1.5` | (n/a) | literal | you |

## Stripe

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `STRIPE_API_KEY` | empty (offline) | `sk_live_xxx` or `sk_test_xxx` | (n/a) | (n/a) | Stripe Dashboard → Developers → API Keys | you |
| `STRIPE_WEBHOOK_SECRET` | empty | `whsec_xxx` | (n/a) | (n/a) | Stripe → Webhooks → Reveal | you, after webhook created |
| `STRIPE_PRICE_PRO_MONTHLY` | empty | `price_xxx` | (n/a) | (n/a) | `python -m scripts.stripe_setup` | you |
| `STRIPE_PRICE_PRO_YEARLY` | empty | `price_xxx` | (n/a) | (n/a) | same | you |
| `STRIPE_PRICE_LIFETIME` | empty | `price_xxx` | (n/a) | (n/a) | same | you |
| `STRIPE_TRIAL_DAYS` | `14` | `14` | (n/a) | (n/a) | literal | you |

## Email

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `EMAIL_PROVIDER` | `console` | `resend` (or `smtp`) | (n/a) | (n/a) | literal | you |
| `EMAIL_FROM` | `noreply@forex-bot.local` | `noreply@yourdomain.com` | (n/a) | (n/a) | your domain | you |
| `RESEND_API_KEY` | empty | `re_xxx` | (n/a) | (n/a) | Resend Dashboard | you |
| `SMTP_HOST` | empty | `smtp.example.com` | (n/a) | (n/a) | your SMTP provider | you |
| `SMTP_PORT` | `587` | `587` | (n/a) | (n/a) | literal | you |
| `SMTP_USER` | empty | `<user>` | (n/a) | (n/a) | provider | you |
| `SMTP_PASSWORD` | empty | `<pass>` | (n/a) | (n/a) | provider | you |

## Observability

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://prometheus:9090` | empty (or Better Stack) | empty | (n/a) | OTLP collector URL | you |
| `OTEL_SERVICE_NAME` | `forex-bot` | `forex-bot-backend` | `forex-bot-engine` | (n/a) | literal | you |
| `SENTRY_DSN` | empty | `https://...@sentry.io/...` | same | (n/a) | Sentry Dashboard → Settings → Client Keys | you |
| `DISCORD_WEBHOOK_URL` | empty | webhook URL | (n/a) | (n/a) | Discord channel → Edit → Integrations | you |

## Rate limits

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `RATE_LIMIT_FREE_PER_MIN` | `30` | `30` | (n/a) | (n/a) | literal | you |
| `RATE_LIMIT_PRO_PER_MIN` | `120` | `120` | (n/a) | (n/a) | literal | you |
| `RATE_LIMIT_PRO_YEARLY_PER_MIN` | `240` | `240` | (n/a) | (n/a) | literal | you |
| `RATE_LIMIT_LIFETIME_PER_MIN` | `240` | `240` | (n/a) | (n/a) | literal | you |

## Misc

| Variable | dev | railway-backend | railway-engine | vercel | How to get it | Set by |
|---|---|---|---|---|---|---|
| `SEED_ADMIN_EMAIL` | `admin@local` | `admin@yourdomain.com` | (n/a) | (n/a) | literal (rotate after first login) | you |
| `SEED_ADMIN_PASSWORD` | `changeme123` | `<rand 24+>` | (n/a) | (n/a) | `openssl rand -base64 18` | you |
| `RISK_DISCLAIMER_VERSION` | `1.0.0` | `1.0.0` | (n/a) | (n/a) | bump when copy changes | you |
| `NEXT_TELEMETRY_DISABLED` | `1` | (n/a) | (n/a) | `1` | literal | you |

---

## Quick-copy template for Railway (paste into "Shared Variables")

```bash
APP_ENV=production
LOG_LEVEL=INFO
JWT_SECRET_KEY=REPLACE_ME_32_BYTES_B64
ENCRYPTION_KEK_BASE64=REPLACE_ME_32_BYTES_B64
ENCRYPTION_KEY_VERSION=1
INTERNAL_API_SECRET=REPLACE_ME_32_BYTES_B64
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_TTL_MIN=15
JWT_REFRESH_TOKEN_TTL_DAYS=14
CORS_ORIGINS=https://YOUR-APP.vercel.app
FRONTEND_URL=https://YOUR-APP.vercel.app
EMAIL_PROVIDER=resend
EMAIL_FROM=noreply@yourdomain.com
RESEND_API_KEY=re_REPLACE_ME
STRIPE_API_KEY=sk_test_REPLACE_ME
STRIPE_WEBHOOK_SECRET=whsec_REPLACE_ME_LATER
STRIPE_TRIAL_DAYS=14
RATE_LIMIT_FREE_PER_MIN=30
RATE_LIMIT_PRO_PER_MIN=120
RATE_LIMIT_PRO_YEARLY_PER_MIN=240
RATE_LIMIT_LIFETIME_PER_MIN=240
SENTRY_DSN=
RISK_DISCLAIMER_VERSION=1.0.0
ENGINE_MODE=paper
MT5_BRIDGE_MODE=proxy
MT5_BRIDGE_URL=https://bridge.yourdomain.com
MT5_BRIDGE_TOKEN=REPLACE_ME_FROM_INSTALL_PS1
DEFAULT_RISK_PCT=1.0
DEFAULT_RR=1.5
```

## Quick-copy template for Vercel (Production scope)

```
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1
NEXTAUTH_SECRET=REPLACE_ME_32_BYTES_B64
NEXTAUTH_URL=https://app.yourdomain.com
NEXT_TELEMETRY_DISABLED=1
```

---

## Rotation cadence

| Secret | Cadence | Trigger |
|---|---|---|
| `JWT_SECRET_KEY` | every 90 days | calendar; invalidates all sessions |
| `NEXTAUTH_SECRET` | every 90 days | calendar; invalidates all NextAuth sessions |
| `ENCRYPTION_KEK_BASE64` | every 365 days | calendar; requires re-encrypting broker creds (see `scripts/rotate_kek.py`) |
| `INTERNAL_API_SECRET` | every 90 days | calendar; rotate backend + engine together |
| `MT5_BRIDGE_TOKEN` | every 90 days | calendar; rotate Windows + Railway together |
| `STRIPE_API_KEY` | on compromise only | incident |
| `STRIPE_WEBHOOK_SECRET` | when endpoint URL changes | move/scale |
| `RESEND_API_KEY` | every 180 days | calendar |
| `SENTRY_DSN` | never (rotates with project) | n/a |
