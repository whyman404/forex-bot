# Deploying Forex Bot frontend to Vercel

Self-contained, 5-minute first deploy. Everything you need is in this file
plus `.env.vercel.example` and `vercel.json`.

## TL;DR (first time)

1. Push the repo to GitHub.
2. In Vercel → **Add New… → Project** → select the repo.
3. **Root Directory:** `projects/forex-bot/frontend`.
4. **Framework Preset:** Next.js (auto-detected from `vercel.json`).
5. **Environment Variables:** copy each line from `.env.vercel.example` into
   the dashboard. At minimum set: `NEXT_PUBLIC_API_URL`, `NEXTAUTH_SECRET`,
   `NEXT_PUBLIC_BASE_URL`, `NEXT_PUBLIC_DEV_MODE=false`.
6. Click **Deploy**. First build takes ~3 minutes. Done.

---

## Required env vars

| Key                                  | Scope                    | Notes                                                                    |
| ------------------------------------ | ------------------------ | ------------------------------------------------------------------------ |
| `NEXT_PUBLIC_API_URL`                | Production + Preview     | Railway backend URL e.g. `https://api.forex-bot.app/api/v1`              |
| `NEXT_PUBLIC_WS_URL`                 | Production + Preview     | Same host as API, `wss://` scheme                                        |
| `NEXT_PUBLIC_BASE_URL`               | Production               | Canonical site URL. Leave blank on preview → falls back to `VERCEL_URL`. |
| `NEXTAUTH_SECRET`                    | Production + Preview     | `openssl rand -base64 32` — never reuse                                  |
| `NEXTAUTH_URL`                       | Production (optional)    | Falls back to `VERCEL_URL` on previews                                   |
| `NEXT_PUBLIC_DEV_MODE`               | Production = `false`     | `true` only in local dev                                                 |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | Production               | When live billing is on                                                  |
| `NEXT_PUBLIC_SENTRY_DSN`             | Production (optional)    | Lazy-loaded — leave blank to disable                                     |

Vercel auto-injects these — **never set them yourself**:

- `VERCEL=1`
- `VERCEL_URL` — host of the current deploy (no scheme)
- `VERCEL_ENV` — `production` | `preview` | `development`
- `VERCEL_GIT_COMMIT_SHA`

---

## TradingView Signal strategy (`tv_signal`)

Round 5 introduces the 7th strategy — TradingView Signal Follow. It depends on
three backend endpoints exposed under `NEXT_PUBLIC_API_URL`:

| Endpoint              | Method | Purpose                                  |
| --------------------- | ------ | ---------------------------------------- |
| `/tv/symbols`         | GET    | List supported TV-mapped symbols         |
| `/tv/preview`         | POST   | Multi-timeframe consensus snapshot       |
| `/tv/health`          | GET    | Integration health (polled every 30s)    |

For full functionality the backend must run with `TV_ENABLED=true`. When the
flag is `false` (or the endpoint returns HTTP 503), the frontend **gracefully
degrades**:

- The strategies grid still renders the 7th card with the "Informational
  signals — not financial advice" chip.
- The `/strategies/tv_signal` detail page renders a non-blocking warning banner
  and disables the **Preview** button.
- The live-trading modal's extra TV gate fails closed — users with `tv_signal`
  instances cannot go live until the backend recovers.

No additional Vercel env vars are required for the frontend — all behavior is
driven by the backend's `TV_ENABLED` flag and standard graceful-degradation
patterns in `use-tradingview.ts`.

---

## Admin panel (`/admin/*`)

The admin route group ships in Round 6. Operational notes:

- **Authorization:** middleware enforces `token.isAdmin === true` at the edge
  for `/admin/:path*`. The admin `layout.tsx` double-checks client-side and
  redirects non-admins to `/dashboard?admin_denied=1`. The backend also
  validates the Bearer token role server-side — this is defence in depth.
- **TOTP step-up:** destructive actions (impersonate, ban, delete, kill-all,
  global kill, large broadcasts) call `POST /admin/auth/step-up` first and
  attach the returned token as `X-Step-Up-TOTP` on the next request. The token
  is never persisted client-side. Argus R4 owns the backend logic.
- **Audit log export:** `GET /admin/audit-log/export.csv` is streamed via
  authenticated `fetch` and downloaded with a synthetic `<a download>` so we
  don't leak the token through a static URL the browser might cache.
- **Health probes:** `/admin/system/dependencies` is polled every 30 seconds.
  We DO NOT retry on failure — failures are the signal we want surfaced.
- **Impersonation:** opens a new tab at `/impersonate#token=…` so the access
  token rides the URL hash (never sent to the server, not stored in history).
- **No special env vars** required for the admin panel itself.

---

## Region selection

`vercel.json` pins to `["sin1", "iad1"]`:

- **sin1** (Singapore) — closest to Thailand / Atlas's primary user base.
- **iad1** (US East) — fallback + global reach.

To change regions, edit `vercel.json` and redeploy. The functions automatically
deploy to all listed regions; Vercel routes each request to the nearest.

---

## Custom domain

1. Vercel → Project → **Settings → Domains** → Add `forex-bot.app`.
2. Vercel gives you either:
   - **Nameservers** (point your registrar to Vercel DNS — easiest), or
   - **CNAME / A records** (keep your DNS, add `cname.vercel-dns.com.`).
3. Once active, set `NEXT_PUBLIC_BASE_URL=https://forex-bot.app` and
   `NEXTAUTH_URL=https://forex-bot.app` on the **Production** scope. Redeploy.
4. Vercel auto-provisions a Let's Encrypt cert (~30 seconds).

---

## Preview branches

- Every PR auto-deploys to `<branch>-<hash>.vercel.app`.
- Branch deploys read **Preview** scope env vars (set them separately in the dashboard).
- Convention: keep `main` always-deployable; develop in feature branches.
- For staging, set `NEXT_PUBLIC_API_URL=https://api-staging.forex-bot.app/api/v1`
  on the Preview scope.

---

## Performance targets

| Metric                         | Target  | Where to check                          |
| ------------------------------ | ------- | --------------------------------------- |
| First Load JS (shared)         | < 200KB | Build output `First Load JS shared`     |
| Per-route JS                   | < 100KB | Build output `First Load JS` per page   |
| LCP                            | < 2.5s  | Vercel Speed Insights / Web Vitals tab  |
| INP                            | < 200ms | Vercel Speed Insights                   |
| CLS                            | < 0.1   | Vercel Speed Insights                   |
| Lighthouse perf (landing)      | ≥ 90    | `lighthouse https://forex-bot.app`      |
| Lighthouse a11y (landing)      | ≥ 95    | Same                                    |

### Bundle analysis

Optional `@next/bundle-analyzer` is wired via the `analyze` script:

```sh
pnpm analyze
# Opens .next/analyze/client.html in a tab
```

Install it lazily (not committed by default) with:

```sh
pnpm add -D @next/bundle-analyzer
```

Then wrap `nextConfig` in `next.config.ts` with `withBundleAnalyzer({ enabled: process.env.ANALYZE === 'true' })`.

---

## ISR vs SSR per route

| Route                          | Rendering | Why                                                           |
| ------------------------------ | --------- | ------------------------------------------------------------- |
| `/` (marketing)                | SSG       | Pure static content; no per-user data                         |
| `/login`, `/signup`            | SSG       | Client-side form, no SSR data                                 |
| `/<strategy-code>` (marketing) | ISR (1h)  | Catalog rarely changes; SEO matters                           |
| `/(app)/*`                     | SSR/CSR   | Auth-gated. Mostly client-side after first paint via TanStack |
| `/api/*`                       | Edge      | Lightweight wrappers (auth callbacks)                         |

Override per page with `export const dynamic = "force-static"` /
`export const revalidate = 3600` etc.

---

## CSP (Content Security Policy)

The CSP lives in **two** places that must stay in sync:

1. `next.config.ts` `headers()` — dev server + defense in depth
2. `vercel.json` `headers[]` — edge-level (overrides on Vercel)

Allowed origins (see `next.config.ts` for the full string):

- `'self'` — the app
- `https://*.stripe.com`, `https://js.stripe.com`, `https://hooks.stripe.com` — Stripe Checkout
- `https://fonts.googleapis.com`, `https://fonts.gstatic.com` — Google Fonts
- `https://*.sentry.io` — Sentry browser SDK (only when DSN set)
- `https://*.vercel-insights.com` — Vercel Analytics
- `https://<railway-host>` — auto-derived from `NEXT_PUBLIC_API_URL`
- `wss:` — WebSocket fallback for live data

If you add a third-party (e.g. PostHog, Intercom), update both files.

---

## Cache headers

Defined in `vercel.json`:

- `/_next/static/(.*)` → `public, max-age=31536000, immutable`
- `/fonts/(.*)` → `public, max-age=31536000, immutable`
- `/api/(.*)` → `no-store, max-age=0`
- everything else → no override (Next's defaults)

---

## Cold-start mitigation

- `output: "standalone"` in `next.config.ts` keeps the runtime image small.
- `experimental.optimizePackageImports` tree-shakes heavy packages
  (lucide-react, date-fns, recharts).
- OG image route uses `runtime = "edge"` for sub-100ms cold starts.

---

## Troubleshooting

| Symptom                                 | Fix                                                                  |
| --------------------------------------- | -------------------------------------------------------------------- |
| Build fails: `Invalid public env vars`  | Missing required env — check the dashboard against `.env.vercel.example` |
| 401 on every API call                   | NEXTAUTH_SECRET mismatch between deploys → set per-scope, redeploy   |
| CORS error from Railway                 | Atlas's API must allow `https://forex-bot.app` AND credentials       |
| Stripe redirect lands on wrong host     | `NEXT_PUBLIC_BASE_URL` unset on production scope                     |
| Demo admin@local prefilled in prod      | `NEXT_PUBLIC_DEV_MODE` is `true` — set to `false`                    |
| Sentry "no events"                      | Install `@sentry/browser` AND set `NEXT_PUBLIC_SENTRY_DSN`            |

---

## What we deliberately did NOT enable

- **Vercel Cron** — hobby plan limits + our scheduling lives in the backend (Celery beat on Railway).
- **Edge Middleware for auth** — NextAuth's JWT works fine at the node runtime; edge adds complexity.
- **Image Optimization for backend assets** — equity-curve PNGs are already optimized server-side.
- **i18n routing** — single-locale (EN) until i18n stub graduates in a later phase.
