# Forex Bot — Honest Status

> Last review: 2026-06-15 (Hephaestus Takumi, Phase 2.5 hybrid-deploy review)
> Audience: project sponsor + first prod operator
> Previous: see `docs/project/integration-review.md` (Phase 1),
> `docs/project/integration-review-phase2.md` (Phase 2), and
> `docs/project/integration-review-phase2.5.md` (this round).

## Deploy targets supported

| Target | Status | When to use | Doc |
|---|---|---|---|
| Local Docker (`./scripts/dev.sh`) | OK | Trying it out, dev loop | `QUICKSTART.md` § Phase 1 |
| Vercel + Railway (paper) | OK | First cloud deploy in 15 min | `docs/deployment/15-minute-deploy.md` |
| Vercel + Railway + Windows MT5 (live) | OK | First live trading deploy | `DEPLOY.md` |
| Self-host Linux VPS (Docker Compose + Caddy) | OK | Full control / lower cost at scale | `QUICKSTART.md` § Phase 2 + `make deploy-prod` |

## What Works End-to-End (Phase 1 + Phase 2 wiring)

### Phase 1 (dev, paper-only)

| Flow | Status | Notes |
|---|---|---|
| `./scripts/dev.sh` boots stack | OK | First build 3-8 min, restart ~30s. Now includes `email-worker`. |
| User signup / login / refresh | OK | Argon2id, refresh rotation, Redis denylist. |
| TOTP 2FA | OK | Envelope-encrypted secret per ADR-005. |
| Dashboard / strategy catalog / settings | OK | All routes wired to backend. |
| Backtest (XAUUSD / BTCUSDT sample data) | OK | Worker writes canonical metric columns. |
| Backtest result UI (chart + DD) | OK | lightweight-charts + recharts. |
| Broker account form + envelope encryption | OK | AES-256-GCM via KEK. |
| MT5 connection test (mock) | OK | Stub returns `{success:true, mock:true}` in dev. |
| Strategy instance lifecycle (paper) | OK | start/stop/kill, audit-logged. |
| Kill switch (3 scopes) | OK | per-instance / per-strategy / global. |
| Migrations (0001 → 0004) | OK | linear chain; duplicate 0003 removed. |
| Rate limiting | OK | Redis-backed sliding window. |
| Audit log (HTTP writes) | OK | per-request middleware. |
| Email verify + password reset | OK (console) | `EMAIL_PROVIDER=console` logs the link; `email-worker` drains the Redis queue. |

### Phase 2 (production additions)

| Capability | Status | Notes |
|---|---|---|
| Stripe Checkout + Customer Portal | OK (offline-safe) | `BillingService` runs in offline mode when `STRIPE_API_KEY=""`. With a real key, runs full Checkout → webhook → entitlement flip. |
| Stripe webhook idempotency | OK | `stripe_events.stripe_event_id UNIQUE` is the race-safe ledger. |
| Email worker | OK | Redis BRPOP loop in `app.workers.email_worker`. Compose service added in this review. |
| Onboarding wizard (4 steps) | OK | `frontend/.../onboarding-*`; backend reads `users.onboarding_step`. |
| Email verify + password reset pages | OK | Frontend pages exist; backend `auth_service` emits jobs to the email queue. |
| Live trading modal (typed confirmation) | OK | `LiveTradingModal` requires literal "I UNDERSTAND". |
| Live monitoring tab | OK | Polls `/strategy-instances/{id}/health`, `/signals`, `/trades`. |
| GDPR settings page | OK | UI + endpoints `POST /users/me/export`, `DELETE /users/me`, `PUT /users/me/consent`. |
| Pricing tiers on landing | OK | Reads `/billing/plans` (public). |
| Risk disclaimer modal (versioned) | OK | Constant in component; consent persisted with version. |
| MT5 bridge (Windows) | OK | Real service in `mt5-bridge/`; Bearer-token auth, constant-time compare. |
| Live engine (paper → live) | OK | `trading-engine/live/engine.py`; uses HMAC-canonical internal API. |
| Circuit breakers | OK | Daily loss, consecutive loss, max DD, slippage, latency. |
| OMS integration (`/internal/signals|trades|health`) | OK | Canonical HMAC contract aligned in this review (was a blocker). |
| Tier rate limits | OK | `RATE_LIMIT_{FREE,PRO,PRO_YEARLY,LIFETIME}_PER_MIN`. |
| Docker compose prod | OK (post-fix) | `make deploy-prod` validates. Includes Caddy, Loki, Promtail, Alertmanager, exporters. |
| Caddy + Let's Encrypt | OK | HTTP/3, HSTS, CSP, security headers. |
| Cloudflare-in-front trusted_proxies | OK | Real-IP from `cf-connecting-ip`. |
| Backup scripts (R2) | OK on disk | Not yet time-tested in this review env. |
| Observability stack | OK | Prometheus + Grafana + Loki + Alertmanager + cAdvisor + node-exporter. |
| Deploy / rollback scripts | OK | `infra/scripts/deploy.sh`, `rollback.sh`. |
| Secrets rotation runbook | OK | `infra/scripts/rotate-secrets.sh`. |
| GitHub Actions: deploy-release.yml | OK | image build + push + ssh-deploy. |

## What is Stub / Mock

| Component | Behavior |
|---|---|
| **MT5 bridge stub** (dev) | Canned responses on port 8500. Real MT5 only runs on Windows via `mt5-bridge/` package — see QUICKSTART § Phase-2 step 7. |
| **`POST /test-mt5-connection` on dev** | Returns `success=true, mock=true`. Real verification on prod via Tailscale to Windows VPS. |
| **Email in dev** | `EMAIL_PROVIDER=console` logs the rendered email. Prod uses Resend/SMTP — set `EMAIL_PROVIDER=resend` and `RESEND_API_KEY`. |
| **Sample OHLCV data** | 4 generated CSVs (XAUUSD M5/H1, BTCUSDT H1/H4) for backtests. Real broker historical data is fetched from MT5 in prod. |
| **Stripe in dev** | `STRIPE_API_KEY=""` → offline mode; UI shows "Connect billing in prod". |
| **R2 backups in dev** | No-op; `R2_*` empty → script logs "R2 not configured, skipping". |
| **SMS notifications** | Not implemented — all alerts go via email + Slack + PagerDuty. |
| **Multi-language UI** | English only at MVP. |

## What is NOT Yet Implemented (Phase 2.1 / 3)

- **Plan-tier count limits** — `subscription_guard` checks plan status but NOT `max_strategy_instances` / `max_concurrent_live`. Documented in `integration-review-phase2.md` § H-PHASE2-1. ETA: half a day.
- **Risk-disclaimer version centralization** — frontend hardcodes `1.0.0`; backend trusts client. Mitigation: `RISK_DISCLAIMER_VERSION` documented in `.env.example`.
- **Signal idempotency** — no UNIQUE on `(strategy_instance_id, ts)` in `signals`. Two POSTs from a retrying engine would double-insert. Add partial-unique in 0005.
- **CLI walk-forward + retro** — Kairos added; not exercised in this review.
- **Backup restore drill** — scripts exist, never executed end-to-end.
- **Legal review of disclaimer text** — Argus drafted; pending counsel.
- **Multi-tenant scaling beyond 2 replicas** — base compose ready; Postgres HA / Redis Sentinel are Phase 3.
- **PWA / WebPush** — notifications table exists; no PWA worker.
- **Hard-purge cron for `account_deletions`** — `scheduled_purge_at` column populated; no worker drains it yet.
- **OWASP ZAP baseline scan** — not run.
- **Lighthouse mobile ≥ 85** — not measured.
- **Load test (100 concurrent users)** — not run.

## Known Limitations + Caveats

| Limitation | Impact |
|---|---|
| Two `docker-compose.yml` files (root vs `infra/`) | Confusing; `dev.sh` and `deploy-prod` both use `infra/`. Root one is dead; safe to delete in a follow-up. |
| Audit middleware opens a fresh DB session per write | Extra connection per write request; fine for MVP. Pool exhaustion possible at high traffic. |
| In-memory backtest job state in `trading-engine/server.py` | Lost on restart. Disk fallback covers most cases. |
| `trading_engine_url` config dead-pointing to `:8200` (Dockerfile binds 8500) | Not called from backend today; latent footgun if someone wires synchronous calls. |
| `seed_admin.py` default password `changeme123` | Below the API's 12-char min; uses raw SQL UPSERT to bypass. **Rotate at first login** in any environment. |
| Legacy HMAC fallback in `/internal/*` | Kept for back-compat with R2 stub. Remove after Phase-2 stable + stub retired. |
| Migration tested only statically | Linear chain verified; `alembic upgrade head` against fresh Postgres recommended before first prod deploy. |
| Engine and backend gate.py have overlapping but non-identical checks | Backend is authoritative per Kairos's module docstring; engine `gate.py` is read-only advisor. |
| `live_consents.version` trusts client-side `"1.0.0"` constant | Frontend = source of truth at MVP. Centralize in Phase 2.1. |

## Test Coverage Summary

Static review + py_compile + docker compose validate. No `pytest` run because
no Python venv was provisioned in the review environment.

| Suite | Files | What they cover |
|---|---|---|
| `backend/tests/` | 7+ | Health, auth flows, backtest create, strategies, billing |
| `trading-engine/tests/` | 2+ | Strategies smoke, backtest API; live engine tests TBD |
| `mt5-bridge/tests/` | 5 | auth, config, safety, server, conftest |
| `frontend/` | 0 | None visible. TS type-checking is the floor. Playwright recommended. |

Coverage threshold not enforced. Recommend `--cov-fail-under=70` for backend
before declaring "done".

## Quality Gates Not Yet Passed

- [ ] End-to-end Playwright suite
- [ ] Backend `pytest` with coverage ≥ 70%
- [ ] OWASP ZAP baseline scan against staging
- [ ] Lighthouse mobile score ≥ 85
- [ ] Load test: 100 concurrent users, 5-min sustained
- [ ] Production database backup + restore drill
- [ ] Postmortem template tested with a real incident
- [ ] Live-trading-launch-checklist signed by Argus + legal

## Performance Budget — Targets vs Actual

| Metric | Target | Actual (estimated) |
|---|---|---|
| Backend `/users/me` p95 | < 100 ms | < 50 ms (no joins, indexed PK) |
| Backend cold start | < 5 s | ~3 s |
| Backtest M5 30-day | < 60 s | < 30s vectorbt, ~90s pandas fallback |
| Frontend cold reload | < 8 s | ~6 s |
| Postgres healthy | < 15 s | 8–12 s |
| Memory ceiling (all containers, dev) | < 4 GB | ~2.5 GB |
| Internal HMAC round trip | < 30 ms | < 10 ms (local Redis-less) |
| MT5 bridge `/quote` p95 | < 200 ms | depends on broker; ~150 ms Exness LDN |

These are estimates. Run a real load profile after first user smoke session.

## Verdict for User

> **Phase 1: ship.** Run `./scripts/dev.sh`. Smoke flow works:
> signup → login → dashboard → backtest → results → broker form → mock MT5 test.
>
> **Phase 2: conditional ship.** Stack now wires together end-to-end (compose
> validates, contracts aligned, migrations linear, secrets documented), but
> first-time prod deploy requires the operator to do the manual work spelled
> out in `QUICKSTART.md § Phase 2` (provision VPSes, DNS, Stripe, Resend,
> Tailscale, MT5 install on Windows). No part of this is automated yet, and
> the live-trading-launch-checklist MUST be signed before real money flows.
>
> If something fails to start, attach
> `docker compose -f infra/docker-compose.yml logs` output to a bug report.
> Reference `docs/project/integration-review-phase2.md` for the contract
> verification matrix.
