# forex-bot-web

> Trading bot SaaS web UI — Next.js 15 (App Router) + TypeScript strict + Tailwind + shadcn-style components.

## Quickstart (dev)

```bash
# 1. Install deps
pnpm install

# 2. Copy env (defaults point at http://localhost:8000)
cp .env.example .env.local

# 3. Run the backend on :8000 first (see ../backend/README.md)

# 4. Run the web app
pnpm dev          # http://localhost:3000

# 5. Open http://localhost:3000/login
#    Dev mode prefills:  email = admin@local   password = changeme123
```

The dashboard, strategies list, backtest runner, broker connection page, and 2FA
enrollment are all wired against the API contract in
`../docs/api/openapi.yaml`.

## Scripts

| Command | Purpose |
|---|---|
| `pnpm dev` | Local dev server |
| `pnpm build` | Production build (standalone output) |
| `pnpm start` | Run production build |
| `pnpm lint` | ESLint |
| `pnpm typecheck` | `tsc --noEmit` strict mode |
| `pnpm test` | Vitest (unit + component) |
| `pnpm test:e2e` | Playwright E2E |
| `pnpm format` | Prettier write |

## Structure

```
src/
├── app/
│   ├── (marketing)/        public landing (+ pricing tiers + risk disclaimer)
│   ├── (auth)/             login / signup / forgot-password
│   ├── (app)/              authenticated app (middleware-gated)
│   │   ├── dashboard/
│   │   ├── strategies/     incl. Go Live modal + live monitoring tab
│   │   ├── backtest/
│   │   ├── broker/
│   │   ├── billing/        Stripe Checkout + Customer Portal + invoices
│   │   ├── onboarding/     4-step wizard (first-login)
│   │   └── settings/       account + security + notifications + privacy/GDPR
│   ├── verify-email/       ?token= POST /auth/verify-email
│   ├── reset-password/     ?token= POST /auth/reset-password
│   ├── api/                route handlers (NextAuth)
│   ├── globals.css
│   └── layout.tsx
├── components/             shadcn-style + project-specific
│   ├── pricing-card.tsx
│   ├── live-trading-modal.tsx
│   ├── gate-check-list.tsx
│   ├── health-badge.tsx
│   ├── onboarding-stepper.tsx
│   └── risk-disclaimer-modal.tsx
├── hooks/                  TanStack Query hooks (one per resource)
│   ├── use-billing.ts          plans / me / checkout / portal
│   ├── use-live-trading.ts     eligibility / consent / go-live / revert / health
│   ├── use-onboarding.ts       step state (server + localStorage fallback)
│   └── use-account.ts          GDPR export / delete / resend-verification
├── lib/
│   ├── api.ts              typed fetch wrapper
│   ├── auth.ts             NextAuth Credentials
│   ├── env.ts              zod-validated public env
│   └── i18n.ts             stub t(key) — English only for MVP
├── store/                  Zustand stores (UI + kill-switch banner)
└── types/                  Domain types mirroring openapi.yaml
```

## Phase 2 features

### Billing (Stripe Checkout redirect)
The billing page renders four pricing cards (Free Trial / Pro Monthly / Pro Yearly / Lifetime) from `GET /billing/plans` (falls back to an in-memory catalogue while Atlas is still wiring the endpoint). Clicking *Subscribe* posts `{ price_id, success_url, cancel_url }` to `POST /billing/checkout-session` and redirects to the returned Stripe-hosted URL. After return at `/billing?session_id=…` we poll `GET /billing/me` every 2s for up to 60s to confirm activation. *Manage billing* hits `POST /billing/customer-portal`.

We **never** mount Stripe Elements client-side — checkout is fully hosted. `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` therefore stays optional (kept in `.env.example` for future Elements migration).

### Live trading flow
- A paper instance grows a *Go Live* button on the strategy detail page once the user has a matching strategy instance.
- The button opens `<LiveTradingModal>` which loads `GET /strategy-instances/{id}/live-eligibility` and renders ✓/✗ per gate.
- All gates must pass **and** the user must type the exact phrase `GO LIVE` **and** check the risk-acceptance box — only then is the *Enable live trading* button clickable.
- On submit we first POST `/live-consents` (so the signed consent is auditable even if go-live fails), then POST `/strategy-instances/{id}/go-live`.
- Live instances render a prominent red `LIVE TRADING — REAL MONEY` badge and a *Revert to paper* button.

### Live monitoring tab
- `GET /strategy-instances/{id}/health` is polled every 10s; status renders via `<HealthBadge>` (green / yellow / red).
- Two tables render `/signals` and `/trades` for the instance.
- A two-click emergency stop calls `POST /strategy-instances/{id}/kill`.

### Onboarding wizard
- Auto-routes to `/onboarding` for first-login users.
- 4 steps: verify email → enable 2FA → connect broker (skippable to paper mode) → pick strategy + create paper instance.
- Persists step on the backend (`PATCH /users/me/onboarding`) and on `localStorage` as fallback.

### Email / password ops
- `/verify-email?token=…` POSTs `/auth/verify-email` and renders success / failed states.
- `/reset-password?token=…` shows a password form and POSTs `/auth/reset-password`.
- `/forgot-password` already shipped — kept under the `(auth)` group.

### GDPR
The Settings → Privacy tab adds:
- *Export my data* → `POST /users/me/export` (we tell the user we will email a download link).
- *Delete account* (typed `DELETE MY ACCOUNT` confirmation) → `DELETE /users/me`.
- Consent log placeholder (rendered from a versioned list — wired once `/users/me/consents` ships).

### Risk disclaimer modal
`<RiskDisclaimerModal triggerOnMount />` auto-opens once per consent version (tracked in `localStorage`). Mounted in `(app)/layout.tsx` so every first-time signin must acknowledge.

## Adding a new language (i18n)
The current stub in `src/lib/i18n.ts` serves English only. To add another language:
1. Copy the `messages.en` object, translate values, expose as `messages.<locale>`.
2. Surface a locale switcher and call `setLocale("th")` (or read from cookie / `Accept-Language`).
3. Wrap the app in a context provider if you need re-rendering on locale change.
4. Replace the keys-as-strings type with a generated `MessageKey` union (e.g. with `lingui` or `paraglide`).

## Auth flow

NextAuth Credentials provider posts `/auth/login` to the backend and stores the
returned access/refresh tokens in a JWT session.

* Access tokens last ~15 minutes. The JWT callback automatically calls
  `/auth/refresh` when fewer than 60 seconds remain.
* If refresh fails (`session.error === "RefreshAccessTokenError"`),
  `useSessionToken` triggers a sign-out and bounces back to `/login`.
* Hooks call `api.get/post/...({ token })` — the wrapper attaches `Authorization: Bearer`.

## Performance budget

- LCP < 2.5s, INP < 200ms, CLS < 0.1
- Initial JS < 180KB gz on `/dashboard`
- All pages keyboard-navigable, axe-clean

## Docker

```bash
docker build -t forex-bot-web .
docker run --rm -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=https://api.example.com/api/v1 \
  -e NEXTAUTH_URL=https://app.example.com \
  -e NEXTAUTH_SECRET=$(openssl rand -base64 32) \
  forex-bot-web
```

The image uses Next.js `output: "standalone"` and runs `node server.js` on port 3000 as the non-root `nextjs` user.

## Coordination

- Backend contract: `../docs/api/openapi.yaml` (Atlas Goro)
- Wireframes: `../docs/design/wireframes/` (Iris Kaguya)
- Strategy semantics: `../docs/strategies/` (Kairos Toki)
