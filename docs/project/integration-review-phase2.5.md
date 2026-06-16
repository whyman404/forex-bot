# Integration Review — Phase 2.5 (Vercel + Railway hybrid deploy)

> Reviewer: Hephaestus Takumi (匠), Senior Developer.
> Date: 2026-06-15.
> Scope: Round-3 (final) cross-agent contract verification for the hybrid
> Vercel + Railway deploy path added by Hestia R3 + Atlas R4 + Eos R4.
> Predecessors: `integration-review.md` (Phase 1), `integration-review-phase2.md` (Phase 2).

## TL;DR

**Verdict: SHIP IT** for Vercel + Railway paper mode.
**Verdict: SHIP IT (with caveats)** for live trading — same caveats as Phase 2
(MT5 setup is manual; gate-checklist sign-off required before flipping
`ENGINE_MODE=live`).

One BLOCKER found and fixed (Procfile referenced a non-existent module).
Three NITs fixed (DEPLOY.md outdated, railway-services.md inconsistent).
Three deferred items documented (rq queue plumbing, partition cron, hard-purge cron).

The user can now go from `git push` → live Vercel URL in ~15 minutes following
`docs/deployment/15-minute-deploy.md`.

---

## A. Checks performed

| # | Check | Method | Result |
|---|---|---|---|
| A1 | `frontend/vercel.json` valid JSON | `python3 -m json.tool` | PASS |
| A2 | `backend/railway.json` valid JSON | `python3 -m json.tool` | PASS |
| A3 | `trading-engine/railway.json` valid JSON | `python3 -m json.tool` | PASS |
| A4 | All recently-changed Python compiles | `python3 -m py_compile` on `main.py`, `config.py`, `billing.py`, `engine.py`, etc. | PASS |
| A5 | DEPLOY.md internal links resolve | grep verified | PASS |
| A6 | `NEXT_PUBLIC_API_URL` includes `/api/v1` in all docs | grep in `DEPLOY.md`, `15-minute-deploy.md`, `.env.example`, `frontend/.env.vercel.example` | PASS |
| A7 | Stripe webhook URL `/api/v1/billing/webhook` matches Atlas's mounted route | confirmed: `api_router.include_router(billing.router, prefix="/billing")` + `app.include_router(api_router, prefix="/api/v1")` + `@router.post("/webhook")` | PASS |
| A8 | CORS regex `^https://([a-z0-9-]+\.)*vercel\.app$` matches preview URLs like `forex-bot-frontend-git-main-username.vercel.app` | regex check — matches because `.vercel.app` is the suffix and any number of subdomains pass `([a-z0-9-]+\.)*` | PASS |
| A9 | `cors_allow_origin_regex` middleware uses `regex or None` pattern (not the bare string) | line 199 of `main.py` confirmed | PASS |
| A10 | Atlas's `_normalize_database_url` accepts Railway `postgres://` and Neon `postgresql://` | verified in `config.py` lines 32-54 | PASS |
| A11 | Atlas's `db_is_neon` detects `.neon.tech` host and auto-enables SSL | `config.py` lines 249-268 | PASS |
| A12 | Atlas's `redis_uses_tls` detects Upstash `rediss://` | `config.py` lines 270-273 | PASS |
| A13 | Healthcheck path `/healthz` exists on backend | `health_router_module` mounted at app root, `main.py` line 281-284 | PASS |
| A14 | Healthcheck path `/healthz` exists on trading-engine | `server.py` line 108 | PASS |
| A15 | Procfile `live_engine` entrypoint exists | `python -m live.engine_runner` — module not found | **FAIL → fixed** |
| A16 | Backend Procfile entries map to actual code (email_worker, backtest_worker) | `app.workers.email_worker` exists; `rq` is in deps but no queue producers wired — backtest_worker will idle. Documented. | PARTIAL |
| A17 | `INTERNAL_API_SECRET` shared semantics documented | `.env.example` line 111, `railway-services.md` step 4 | PASS |
| A18 | `FRONTEND_URL` used for Stripe success_url + email links | grep in `billing_service.py` and `email_service.py` — both consume `settings.effective_frontend_url` | PASS |
| A19 | `NEXTAUTH_URL` vs `VERCEL_URL` distinction documented | `frontend/src/lib/env.ts` lines 10-14 + `.env.vercel.example` lines 28-31 | PASS |
| A20 | Build command `pnpm build` in `frontend/vercel.json` | verified | PASS |
| A21 | Python 3.12 pinned in both nixpacks.toml | verified backend + trading-engine | PASS |
| A22 | Migration policy in DEPLOY.md — manual run | section 3 updated to make policy explicit | PASS |
| A23 | Graceful shutdown documented | Atlas R4 implemented; `shutdown_grace_seconds: 10.0` in config | PASS |
| A24 | Stripe Caddy (self-host) and Railway (cloud) routes consistent | both = `/api/v1/billing/webhook` | PASS |
| A25 | Cost estimate accurate vs reality | reviewed component table; $25–31/mo is correct lower bound with Neon+Upstash; $36/mo upper bound with all-Railway plugins | PASS |
| A26 | Architecture diagram in DEPLOY.md correct | reflects 4 Railway services + 2 plugins + Vercel + Windows VPS | PASS |
| A27 | `RUN_MIGRATIONS_ON_BOOT` env defaults to false | `config.py` line 170 | PASS |
| A28 | `INTERNAL_TRUSTED_PROXY_CIDRS` env split validator handles CSV | `config.py` lines 201-206 | PASS |
| A29 | `MT5_BRIDGE_URL` reachability options (Tailscale vs Cloudflare Tunnel) documented | `DEPLOY.md` section 6 | PASS |
| A30 | `numReplicas=1` on trading-engine to avoid in-process registry split | `trading-engine/railway.json` line 14 | PASS |
| A31 | `frontend/next.config.ts` `output: "standalone"` keeps build portable | verified line 98 | PASS |
| A32 | CSP `connect-src` includes API origin (`apiOrigin`) | `next.config.ts` lines 19-26 + 46 | PASS |
| A33 | Server Action allowed origins include `*.vercel.app` + `VERCEL_URL` | `next.config.ts` lines 87-93 | PASS |

---

## B. Issues found

### B1. BLOCKER — `trading-engine/Procfile` referenced missing module

**Severity:** blocker (would crash the live_engine service on first start).

**Symptom:** `Procfile` line 7 reads `live_engine: python -m live.engine_runner`,
but `trading-engine/live/engine_runner.py` does not exist. The `live/engine.py`
file defines a `LiveEngine` class with no `__main__` entrypoint.

**Root cause:** Conceptual mismatch with the actual architecture. The
trading-engine `web` service already hosts `LiveEngine` instances **in-process**
via `live/router.py` — Atlas's `/live/start` endpoint instantiates a
`LiveEngine` and stores it in `_REGISTRY: dict[str, LiveEngine]`. A separate
worker process would have its own (empty) registry — the two would diverge.

**Fix applied:**
1. Removed the `live_engine:` Procfile line. `trading-engine/Procfile` now
   only declares `web:`.
2. Added a multi-line comment explaining the architecture (in-process registry,
   one supervisor process, `numReplicas=1`).
3. Removed Service-5 (`trading-engine-live`) from `railway-services.md`.
4. Updated `railway-services.md` project layout to "4 services + 2 plugins".

**Verification:**
- `python3 -m py_compile trading-engine/live/engine.py` — passes (unchanged).
- `trading-engine/railway.json` already pins `numReplicas: 1` — defends the
  in-process registry assumption.

**File touched:** `trading-engine/Procfile`, `railway-services.md`.

---

### B2. NIT — DEPLOY.md instructed redundant DATABASE_URL rewrite

**Severity:** nit (not blocking but wasted user time).

**Symptom:** Section 2 step 5 of `DEPLOY.md` told users to manually rebuild
the DATABASE_URL as
`postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@...`
because "backend expects asyncpg dialect".

**Root cause:** Atlas's R4 work added `_normalize_database_url()` which
auto-converts `postgres://` and `postgresql://` to `postgresql+asyncpg://`.
The doc didn't reflect this improvement.

**Fix applied:** Simplified DEPLOY.md section 2 step 5 to just
`DATABASE_URL = ${{Postgres.DATABASE_URL}}` with a comment that Atlas
normalizes the scheme. Same fix in `railway-services.md` Plugin 1 section.

**File touched:** `DEPLOY.md`, `railway-services.md`.

---

### B3. NIT — DEPLOY.md missing CORS regex callout

**Severity:** nit (would confuse a user during preview-branch debugging).

**Symptom:** Step 5 told users to set `CORS_ORIGINS = https://forex-bot-frontend-xxx.vercel.app`
but didn't mention the regex that also accepts ANY `*.vercel.app` preview URL.

**Fix applied:** Added a comment next to `CORS_ORIGINS` documenting the regex
fallback. Same callout added to `15-minute-deploy.md` Step 5.

**File touched:** `DEPLOY.md`.

---

### B4. NIT — DEPLOY.md missing migration policy + cron schedule

**Severity:** nit (operations footgun if not documented).

**Symptom:** DEPLOY.md section 3 told users to run `alembic upgrade head` in
Railway shell, but didn't (a) state policy on the alternative
`RUN_MIGRATIONS_ON_BOOT` env, or (b) explain how to schedule recurring jobs
(partition maintenance, GDPR purge).

**Fix applied:** Section 3 of DEPLOY.md now opens with an explicit "Migration
policy: manual, NOT auto-on-boot" callout. Added a Scheduled Jobs subsection
covering Railway's "Cron schedule" service field, with concrete schedules for
partition maintenance and (Phase 2.1) hard-purge.

**File touched:** `DEPLOY.md`.

---

### B5. NIT — trading-engine variables in DEPLOY.md missing placeholder values

**Severity:** nit.

**Symptom:** DEPLOY.md section 2 step 7 listed `INTERNAL_API_SECRET`,
`DATABASE_URL`, `REDIS_URL` as variables to set but didn't show how to wire
them as cross-service references.

**Fix applied:** Step 7 now uses explicit `${{Service.VAR}}` syntax for each
reference and lists ALL required envs (including `MT5_BRIDGE_URL`/`TOKEN`
placeholders for paper mode). Also added the `numReplicas=1` note.

**File touched:** `DEPLOY.md`.

---

## C. Fixes applied (summary)

| # | File | Change | Severity |
|---|---|---|---|
| C1 | `trading-engine/Procfile` | Removed missing `live_engine:` entry, added architecture comment | BLOCKER |
| C2 | `railway-services.md` | Removed Service-5, simplified DB URL, updated total count | BLOCKER+NIT |
| C3 | `DEPLOY.md` § 2 step 5 | Simplified DATABASE_URL to plugin reference + CORS regex callout | NIT |
| C4 | `DEPLOY.md` § 2 step 7 | Trading-engine vars use `${{backend.X}}` references + numReplicas note | NIT |
| C5 | `DEPLOY.md` § 3 | Migration policy explicit + scheduled jobs subsection | NIT |
| C6 | `docs/deployment/15-minute-deploy.md` (new) | Opinionated 15-minute cookbook from `git push` to login | new doc |
| C7 | `.env.deploy-checklist.md` (new) | Printable env-var worksheet keyed to Vercel/Railway dashboards | new doc |
| C8 | `QUICKSTART.md` | Top-of-file "Pick your path" 4-row table | doc |
| C9 | `STATUS.md` | "Deploy targets supported" row at top | doc |
| C10 | `PROJECT-STATUS.md` | Deploy-options table at top | doc |

Lines changed: ~250 across 7 existing files; 2 new docs (~550 lines).

---

## D. Deferred (will not block ship)

| # | Item | Why deferred | When |
|---|---|---|---|
| D1 | `rq` queue producers in `backtest_service.py` | The Procfile launches `rq worker backtest` but no code enqueues yet. Worker idles harmlessly; backtests run synchronously in the web process. | Phase 2.1 (when backtest load justifies offloading) |
| D2 | `scripts/hard_purge_account_deletions.py` | GDPR `account_deletions.scheduled_purge_at` is populated; no drainer. | Phase 2.1 (already in STATUS.md NOT-YET list) |
| D3 | Tailscale-on-Railway recipe | Beta path documented in DEPLOY.md § 6 Option B; Cloudflare Tunnel (Option A) is the recommended path. | When Tailscale ships userspace networking GA on Railway |
| D4 | Sentry source maps upload | `productionBrowserSourceMaps: false` in `next.config.ts`; for Sentry, add the Sentry Vercel integration. Documented in `.env.deploy-checklist.md` § I. | When user enables Sentry |
| D5 | Vercel Analytics + Web Vitals dashboards | One-click enable in Vercel UI; not coded. | When traffic appears |
| D6 | OWASP ZAP scan against the Railway URL | Same status as Phase 2 — not run. | Pre-launch QA gate |

---

## E. Smoke-test commands the user can run

These ran clean in this review (~/forex-bot tree):

```bash
# JSON validity
for f in frontend/vercel.json frontend/package.json frontend/tsconfig.json \
         frontend/.eslintrc.json backend/railway.json trading-engine/railway.json; do
  python3 -m json.tool < "$f" > /dev/null && echo "OK: $f"
done

# Python compiles
python3 -m py_compile \
  backend/app/main.py \
  backend/app/core/config.py \
  backend/app/api/billing.py \
  backend/scripts/seed_admin.py \
  backend/scripts/stripe_setup.py \
  backend/app/workers/email_worker.py \
  trading-engine/server.py \
  trading-engine/live/engine.py
echo "all python compiles"

# Procfile sanity (after fix)
grep -c '^[a-z_]\+:' trading-engine/Procfile  # expect 1 (just web:)
grep -c '^[a-z_]\+:' backend/Procfile          # expect 4 (web/email_worker/backtest_worker/release)

# Env-var documentation cross-check — every var the app references must exist in .env.example
grep -oE 'process\.env\.[A-Z_]+' frontend/src/lib/env.ts | sed 's/process.env.//' | sort -u
grep -oE 'os\.getenv\("[A-Z_]+"' backend/app -r | sed 's/os.getenv("//' | sort -u
# diff against:
grep -oE '^[A-Z_]+=' .env.example | sed 's/=//' | sort -u
```

The user cannot actually `pnpm build` in this review (no pnpm install run),
nor `uvicorn app.main:app` boot (no Postgres reachable), but the static
checks above are the deterministic floor.

For the on-Railway smoke test after deploy, see `15-minute-deploy.md` step 6.

---

## F. Verification of contract alignment

| Contract | Producer | Consumer | Aligned? |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` must end `/api/v1` | DEPLOY.md tells user | `frontend/src/lib/api.ts` `apiBaseUrl()` returns it verbatim, then prepends to `/auth/login`, `/me`, etc. — backend mounts at `/api/v1/*` | YES |
| Stripe webhook URL = `/api/v1/billing/webhook` | DEPLOY.md + 15-minute-deploy.md | `billing.py` mounts `@router.post("/webhook")` under `api_router.include_router(billing.router, prefix="/billing")` + `app.include_router(api_router, prefix="/api/v1")` → final path `/api/v1/billing/webhook` | YES |
| `FRONTEND_URL` matches Vercel deploy URL | DEPLOY.md + 15-minute-deploy.md | `billing_service.py` uses `settings.effective_frontend_url` for `success_url`; `email_service.py` uses same for verify-link base | YES |
| `INTERNAL_API_SECRET` shared between backend + trading-engine | Hestia railway-services.md, Atlas .env.example | `oms_client.py` (backend) and `internal_client.py` (engine) both read `os.getenv("INTERNAL_API_SECRET")` for HMAC signing | YES |
| Database URL accepts both Railway and Neon | Hestia DEPLOY.md mentions Neon | Atlas `_normalize_database_url` + `db_is_neon` + `db_requires_ssl` | YES |
| Redis URL accepts both Railway and Upstash | Hestia neon-upstash-setup.md | Atlas `redis_uses_tls` detects `rediss://` and Upstash auto-handled by `redis-py` | YES |
| CORS regex covers Vercel preview URLs | Atlas `cors_allow_origin_regex` default | Eos `frontend/vercel.json` deploys to `*.vercel.app` (production) and `*-git-*.vercel.app` (preview) — both match | YES |
| Trading-engine numReplicas = 1 | trading-engine/railway.json | LiveEngine in-process registry would diverge across replicas — single replica is correct | YES |
| Graceful shutdown drains traffic | Atlas R4 implementation + `shutdown_grace_seconds: 10.0` default | Railway SIGTERM → uvicorn → FastAPI lifespan shutdown → DB pool dispose | YES |
| `RUN_MIGRATIONS_ON_BOOT` off by default | Atlas `config.py` line 170 | DEPLOY.md § 3 now states "Migration policy: manual" | YES |

All contracts aligned.

---

## G. Verdict

### Vercel + Railway paper deploy
**SHIP IT.**
- User can go from `git push` to login screen in 15 minutes.
- All env vars documented in `.env.deploy-checklist.md`.
- All contracts (CORS, webhook, internal HMAC, DB driver) aligned.
- No code changes required from the user beyond pasting env values.

### Vercel + Railway + Windows MT5 live deploy
**SHIP IT WITH CAVEATS** (same caveats as Phase 2, unchanged):
- MT5 bridge installation is a manual 30-min step on the Windows VPS.
- Tailscale or Cloudflare Tunnel must be wired to bridge Linux↔Windows.
- Going-live gate must be checked off per `docs/security/live-trading-launch-checklist.md`.
- The 8 gate checks (email_verified, totp_enabled, paid_subscription,
  qualifying_backtest, paper_track_record≥14d, live_consent_signed,
  broker_min_balance, kill_switch_clear) MUST pass before flipping
  `ENGINE_MODE=live`.

### Self-host VPS deploy
**SHIP IT** (unchanged from Phase 2 review).

---

## H. Open follow-ups for the team

| # | Owner | Task |
|---|---|---|
| H1 | Atlas | Implement `rq` queue producers in `backtest_service.py` to actually use the `backtest_worker` Procfile entry. Until then, the worker idles harmlessly. |
| H2 | Atlas | Add `scripts/hard_purge_account_deletions.py` to drain GDPR queue. |
| H3 | Hestia | Once Tailscale userspace networking on Railway is GA, replace DEPLOY.md § 6 Option B with the GA recipe. |
| H4 | Themis | Run Playwright e2e against a Vercel preview URL pointing to a Railway preview environment. |
| H5 | Argus | OWASP ZAP baseline scan against `https://<railway-backend>/api/v1/*`. |

None of H1–H5 block the Phase-2.5 deploy. They are tracked for Phase 2.6.

---

## Appendix — files touched in this review

```
# Modified
trading-engine/Procfile
DEPLOY.md
railway-services.md
QUICKSTART.md
STATUS.md
PROJECT-STATUS.md       (in repo root one level up)

# New
docs/deployment/15-minute-deploy.md
.env.deploy-checklist.md
docs/project/integration-review-phase2.5.md   (this file)
```

Total: 6 files modified, 3 files created.

---

## Sign-off

> **Hephaestus Takumi (匠), Senior Developer.** Round-3 final hybrid-deploy
> review complete. Ship it.

— 2026-06-15
