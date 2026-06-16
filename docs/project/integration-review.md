# Integration Review — Forex Bot SaaS

> Reviewer: Hephaestus Takumi (Senior Developer)
> Date: 2026-06-15
> Scope: Final review before user can run `./scripts/dev.sh` and login.

## What I Checked

| Layer | Files | Outcome |
|---|---|---|
| ORM models vs schema.sql | `backend/app/models/*.py` against `docs/database/schema.sql` | Aligned. `user.py` correctly uses `role` enum + `email_verified_at`. No drift. |
| Backend imports | `backend/app/main.py`, `backend/app/api/__init__.py`, `backend/app/middleware/*.py` | All resolve. Lifespan references only existing symbols. |
| Alembic env | `backend/alembic/env.py` | Eagerly imports `app.models` package; all 10 model modules importable. |
| Seed admin | `backend/scripts/seed_admin.py` | Uses raw SQL UPSERT into the canonical `users` table; bypasses ORM ⇒ safe. |
| Atlas → trading-engine | `backend/app/services/backtest_service.py` vs `trading-engine/server.py` | Backend never makes HTTP call to trading-engine; uses Redis queue (`backtest:queue`). The orphan `trading_engine_url=http://trading-engine:8200` in config is unused — left as-is (Phase 2 cleanup). |
| Trading-engine → DB | `trading-engine/workers/backtest_worker.py` UPDATE statements | BLOCKER (fixed) — wrote to a non-existent `metrics` jsonb column and to `updated_at`. Rewritten to map summary keys → canonical columns. |
| Frontend auth header | `frontend/src/lib/api.ts` (`Authorization: Bearer ${token}`) vs `backend/app/middleware/auth.py` (`HTTPBearer`) | Matches. |
| NextAuth session token name | `frontend/src/lib/auth.ts` (`session.accessToken`) vs `frontend/src/hooks/use-session-token.ts` (`session.accessToken`) | Matches. |
| All Python compiles | 103 .py files | All pass `python3 -m py_compile`. |
| TS file count | `frontend/src/**/*.ts*` | 64 files present. |
| Sample data | `trading-engine/data/samples/*.csv` | 4 files (XAUUSD M5/H1, BTCUSDT H1/H4). |
| schema.sql exists | `docs/database/schema.sql` | 517 lines. |

## Sanity Check Results (Bash)

```
find projects/forex-bot -name "*.py" ... -exec python3 -m py_compile {} \;
→ exit 0 (no syntax errors across 103 Python files)

find projects/forex-bot/frontend/src -name "*.ts*" | wc -l
→ 64

ls projects/forex-bot/trading-engine/data/samples/*.csv
→ BTCUSDT_H1_sample.csv, BTCUSDT_H4_sample.csv,
   XAUUSD_H1_sample.csv, XAUUSD_M5_sample.csv

wc -l projects/forex-bot/docs/database/schema.sql
→ 517
```

## Issues Found

### BLOCKER — Fixed

**B1. Top-level `.env.example` uses wrong variable names.**
- `JWT_SECRET` → backend config expects `JWT_SECRET_KEY` (required, min_length=32).
- `JWT_EXPIRE_MINUTES` → expects `JWT_ACCESS_TOKEN_TTL_MIN`.
- `ENCRYPTION_KEK` → expects `ENCRYPTION_KEK_BASE64`.
- Without these matching, `Settings()` validation crashes on startup with a Pydantic error and `uvicorn` exits.
- Fixed in `.env.example` and the `replace_placeholder` calls in `scripts/dev.sh` so secrets generated at startup land in the correct keys.

**B2. `NEXT_PUBLIC_API_URL` missing `/api/v1` prefix.**
- The backend mounts all routers under `/api/v1` (`backend/app/main.py:247`).
- `.env.example` was `NEXT_PUBLIC_API_URL=http://localhost:8000`, so all calls 404'd.
- Fixed in `.env.example` and `infra/docker-compose.yml` to include `/api/v1`.

**B3. Trading-engine worker writes to non-existent columns.**
- `backtest_worker.py:_update_backtest_row` issued `UPDATE backtests SET metrics=...::jsonb, updated_at=NOW()` — neither column exists. The `backtests` table has individual metric columns (`total_return_pct`, `sharpe`, …) and no `updated_at` column.
- Every completed backtest would crash, leaving the row stuck in `running`.
- Rewritten to dynamically build the UPDATE from a whitelist of canonical columns + lifecycle timestamps (`started_at`, `completed_at`).
- Also stripped `+asyncpg` from the DSN before passing to psycopg (which does not understand SQLAlchemy driver tags).

**B4. `UserPublic` Pydantic schema does not serialize derived fields.**
- `is_admin`, `display_name` were declared as plain `@property`. Pydantic only includes model fields and `@computed_field`-decorated properties in JSON output.
- The frontend `auth.ts` reads `profile.is_admin` and `profile.display_name` — both were `undefined`. NextAuth.session.user.isAdmin would be `false` even for admin users → admin routes invisible.
- Changed to `@computed_field` so both serialize in `/users/me` JSON.

**B5. Signup field name mismatch (`display_name` vs `full_name`).**
- Frontend signup posts `{ email, password, display_name }`.
- Backend `SignupRequest` requires `full_name` (min_length=1). Result: every signup returned 422.
- Added `validation_alias=AliasChoices("full_name", "display_name")` so both names are accepted, populating the same attribute.

**B6. Compose override runs missing module.**
- `infra/docker-compose.override.yml` set `trading-engine-worker.command = ["python", "-m", "worker"]`. No top-level `worker` module exists (the package is `workers/`).
- Changed to `["worker"]`, using the entrypoint's "worker" mode which runs `rq worker backtest`.

### HIGH — Not Fixed (Phase 2)

**H1. Two competing docker-compose files.**
- Root `docker-compose.yml` (rich, observability stack, `trading-engine` HTTP service).
- `infra/docker-compose.yml` (lean, dev-only, `trading-engine-worker` only — no HTTP).
- `dev.sh` uses the `infra/` one. The root file is unused in dev. Recommend deleting the root file or consolidating once we stabilize.

**H2. Frontend `BacktestPublic` type uses fields the backend does not return** (`range_start`, `range_end`, `initial_balance`, `sharpe_ratio`, `net_profit`, status value `succeeded`). Backend returns `start_date`, `end_date`, `sharpe`, `completed`. This only affects the backtest result UI — login/dashboard still work. Needs an adapter or schema sync.

**H3. `trading_engine_url=http://trading-engine:8200` in `backend/app/core/config.py` is dead config.** The Dockerfile binds 8500. Nothing in the backend code calls this URL today (only Redis queue is used). Leave for now; remove when we wire the synchronous health-check endpoint.

**H4. CORS origin parsing.** `backend/.env.example` uses a JSON-list form `CORS_ORIGINS=["http://localhost:3000",...]`. The Pydantic validator handles both CSV and JSON, but worth a smoke test.

### MEDIUM — Not Fixed

**M1. `backtest_service._publish_job` does not include `strategy_code`.** The worker registry keys are codes, not UUIDs. If we ever drive the worker from the Redis payload alone, it cannot resolve the strategy. Current code path (in-process server.py) takes strategy_code directly from the HTTP request, so this is latent.

**M2. Audit middleware opens a fresh DB session per request.** Acceptable in MVP; will hurt under load (an extra connection per write). Document in runbook.

### LOW — Not Fixed

**L1. `seed_admin.py` default password `changeme123` is 11 chars** — fails the API signup validator (min 12). Not a blocker because it goes through raw SQL. Document and rotate at first login.

**L2. `auth_service.signup`** catches `IntegrityError` but does not call `await self.db.rollback()` before re-raising on the audit failure path. Currently benign because the surrounding `with` block rolls back on exit.

## Fixes Applied — File Index

| # | File | Lines | What |
|---|---|---|---|
| B1 | `.env.example` | 42-50 | Rename JWT_SECRET→JWT_SECRET_KEY, JWT_EXPIRE_MINUTES→JWT_ACCESS_TOKEN_TTL_MIN, ENCRYPTION_KEK→ENCRYPTION_KEK_BASE64; add ENCRYPTION_KEY_VERSION |
| B1 | `scripts/dev.sh` | 118-120 | `replace_placeholder` calls use new variable names |
| B2 | `.env.example` | 58 | NEXT_PUBLIC_API_URL ends with `/api/v1` |
| B2 | `infra/docker-compose.yml` | 160 | `NEXT_PUBLIC_API_URL: http://localhost:8000/api/v1` |
| B3 | `trading-engine/workers/backtest_worker.py` | 62-138 | Rewrote `_update_backtest_row`; added `_normalize_dsn` |
| B4 | `backend/app/schemas/user.py` | 8, 26-36 | `@computed_field` on `display_name`, `is_admin` |
| B5 | `backend/app/schemas/auth.py` | 5, 8-17 | Added `AliasChoices("full_name","display_name")` |
| B6 | `infra/docker-compose.override.yml` | 88-101 | `command: ["worker"]` |

## Verdict

**Conditional ship.** With these blockers fixed, the app should boot via `./scripts/dev.sh`. Smoke flow expected to work:

1. Containers come up (postgres, redis, backend, frontend, trading-engine-worker, mt5-bridge-stub, prom/grafana).
2. Alembic migrates schema.sql baseline.
3. Seed admin runs.
4. User opens `http://localhost:3000`, logs in as `admin@local / changeme123`.
5. Dashboard renders. Backtest enqueue → Redis → worker → metric columns updated.

What might still break that I did not exercise (no docker run):
- Frontend build (TS types may have stricter checks I missed).
- Strategy seed migration `0002_seed_strategies.py` content — assumed correct.
- `infra/docker/mt5-bridge-stub/Dockerfile` build.

**Recommend:** user runs `./scripts/dev.sh` once. If anything fails, capture `docker compose logs <service>` and triage before declaring the integration green.
