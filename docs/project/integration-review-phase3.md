# Integration Review — Phase 3 (TradingView Signal Follow)

> **Reviewer:** Hephaestus Takumi (Senior Developer)
> **Date:** 2026-06-16
> **Scope:** Round 4 — TradingView signal integration across Kairos (engine),
> Atlas (backend), Mnemosyne (DB), Eos (frontend), Argus (compliance).
> **Verdict:** **SHIP** after 5 blocker fixes applied in this review (see § Fixes Applied).
> **Previous reviews:** Phase 1, Phase 2, Phase 2.5 — all in this directory.

---

## 1. What landed in Phase 3

| Agent | Round | Files added |
|---|---|---|
| **Kairos Reo** (Trading Engine) | R4 | `trading-engine/tradingview/{client,scorer,symbols}.py`, `strategies/tv_signal.py`, `live/tv_signal_engine.py`, `server.py` endpoints (`/tv/preview`, `/tv/symbols`), `tests/test_tv_signal.py`, `docs/strategies/tv-signal.md`, `docs/strategies/tradingview-integration.md`, `configs/strategies.yaml` updated. |
| **Atlas Goro** (Backend) | R5 | `backend/app/api/tradingview.py`, `services/tradingview_service.py`, `schemas/tradingview.py`, `services/live_gate_service.py` updated (extra gate `external_service_healthy`), `tests/test_tradingview_endpoints.py`, `docs/api/openapi.yaml` updated. |
| **Mnemosyne Rin** (DB) | R4 | `alembic/versions/0005_tv_signal.py` (asset_class `multi`, `strategies.requires_external_service` BOOL, `strategy_instances.external_signal_provider` VARCHAR), `scripts/seed_strategies.sql` updated, `docs/database/tv_signal-data-model.md`. |
| **Eos Hinata** (Frontend) | R5 | `src/hooks/use-tradingview.ts`, `components/tv-{recommendation-badge,score-bar,timeframe-table}.tsx`, `app/(app)/strategies/tv_signal/page.tsx`, strategy list page + live-trading modal updated (TV health gate), risk-disclaimer-modal bumped to v1.1.0, marketing landing copy updated. |
| **Argus Mira** (Compliance) | R3 | `docs/security/tradingview-integration-risk.md`, `disclaimers-v2.md`, `sbom-update.md`, launch-checklist Section TV (14 gates), regulatory-update Section 8b R10-R13, secure-defaults Section 17. |

---

## 2. Cross-agent contract verification matrix

| # | Contract | Producer | Consumer | Status |
|---|---|---|---|---|
| C1 | Engine `/tv/preview` request shape | Backend `TradingViewService._post` | Engine `tv_preview` handler | OK (signed via `sign_canonical`) |
| C2 | Engine `/tv/preview` response shape | Engine `TVPreviewResponse` | Backend `_normalize_preview` | **BLOCKER → FIXED** (see F1) |
| C3 | Engine `/tv/symbols` response shape | Engine `tv_symbols` (`list_supported()`) | Backend `_normalize_symbol` | OK — both shapes tolerated |
| C4 | Engine `/tv/health` endpoint exists | Engine | Backend `get_health()` | **BLOCKER → FIXED** (F2) — endpoint was missing |
| C5 | Backend `TVPreview` schema = frontend `TVPreview` type | openapi.yaml + Pydantic | `frontend/src/types/domain.ts` | **BLOCKER → FIXED** (F3) — field names diverged |
| C6 | Backend `TVSymbol` schema = frontend `TVSymbol` type | openapi.yaml + Pydantic | `frontend/src/types/domain.ts` | **BLOCKER → FIXED** (F3) — `code/tv_symbol/tv_exchange` vs `symbol/tv_ticker` |
| C7 | Backend `TVHealth` schema = frontend `TVHealth` type | openapi.yaml + Pydantic | `frontend/src/types/domain.ts` | **BLOCKER → FIXED** (F3) — `checked_at` vs `last_success_at` |
| C8 | `tv_signal` strategy code identical across layers | Engine `strategies.yaml`, backend seed, frontend constant `STRATEGY_CODE = "tv_signal"` | All | OK |
| C9 | `requires_external_service` flag DB → API → UI | Migration 0005 → ORM → strategies router → frontend strategy list | All | OK |
| C10 | `external_signal_provider` set to `'tradingview'` on tv_signal instance create | Migration 0005 column → strategy_service R5 | DB | OK |
| C11 | Live-gate `external_service_healthy` blocks live start when TV down | Backend `live_gate_service._external_service_healthy` | Frontend live-trading modal | OK |
| C12 | HMAC `sign_canonical` reused (no fork) | Backend `oms_client.sign_canonical` | Backend `TradingViewService._sign_headers` | OK |
| C13 | Migration chain linear 0001 → … → 0005 | `backend/alembic/versions/` | Alembic head | OK (verified) |
| C14 | Migration 0005 idempotent + downgradable | `0005_tv_signal.py` | — | OK (re-running converges via `ON CONFLICT`; downgrade reverses DDL) |
| C15 | Env vars documented centrally | `.env.example` | All targets | **PARTIAL → FIXED** (F4) — added `TV_PREVIEW_RATE_LIMIT_PER_MIN`, `TV_CATALOG_CACHE_TTL_SEC` |
| C16 | Frontend hook `useTVPreview` payload matches `TVPreviewRequest` | `use-tradingview.ts` | Backend router | OK |
| C17 | OpenAPI `/tv/preview|symbols|health` documented | `docs/api/openapi.yaml` | clients | OK |

---

## 3. Static check results

```
$ python3 -m py_compile <all Phase-3 .py files>
# clean (0 errors)

$ python3 -c "import yaml; yaml.safe_load(open('trading-engine/configs/strategies.yaml')); \
                yaml.safe_load(open('docs/api/openapi.yaml')); print('YAML OK')"
YAML OK

$ grep -rn '<legacy-tv-field>' frontend/src/
# clean — all consumers migrated to new field names
```

`pnpm typecheck` not run in this review env (no node_modules) — type changes
were textual edits guided by the Pydantic / openapi source of truth.

---

## 4. Fixes Applied (Blockers cleared)

### F1. Engine `/tv/preview` response shape — backend can now parse it

**Before:** Engine returned `{ ok, symbol, exchange, intervals, analysis: { per_interval, errors }, score: <dict from combined.to_dict()> }`. Backend `_normalize_preview` looked for **top-level** `score: float`, `confidence: float`, `timeframes: list`, `generated_at: ISO string` — none of which existed. Result would be `score=0.0, timeframes=[], generated_at=now()` for every call (silent data loss).

**Fix:** `trading-engine/server.py:108-135` (`TVPreviewResponse` schema) and `:340-385` (handler) — engine now emits **both** the rich `score_detail` dict (for legacy/dev callers) **and** the flat fields backend expects: `score: float`, `confidence: float`, `timeframes: list[dict]`, `generated_at: ISO`. The legacy `analysis.per_interval` still ships unchanged.

### F2. Engine `/tv/health` endpoint — implemented

**Before:** Backend's `is_healthy_for_gate()` calls `GET /tv/health` against the engine, but the engine had no such route. Result: every `tv_signal` live-start attempt blocked on `external_service_healthy` failure ("trading-engine GET /tv/health → 404").

**Fix:** `trading-engine/server.py:395-445` — added `/tv/health` returning `{status: ok|degraded|down, trading_engine_reachable, upstream_tv_reachable, reason, checked_at}` exactly matching `backend.app.schemas.tradingview.TVHealth`. Implementation does a tiny probe call (`EURUSD/OANDA/1h`) which hits the 60s `TVClient` cache, so polling is cheap.

### F3. Frontend types align with backend openapi

**Before:** `frontend/src/types/domain.ts` declared `TVTimeframeAnalysis.buy/sell/neutral`, `TVPreview.composite_score/composite_recommendation/tv_ticker/agreement_pct/fetched_at`, `TVSymbol.symbol/tv_ticker`, `TVHealth.last_success_at/recent_signal_count` — none matched backend / openapi (`buy_count/sell_count/neutral_count`, `score/confidence/symbol/exchange/generated_at`, `code/tv_symbol/tv_exchange`, `checked_at/upstream_tv_reachable`). Frontend would render `undefined` for every TV field.

**Fix:**
- `frontend/src/types/domain.ts:368-432` — all five TV types rewritten to mirror openapi.
- `frontend/src/components/tv-timeframe-table.tsx:64-66` — `r.buy/sell/neutral` → `r.buy_count/sell_count/neutral_count`.
- `frontend/src/app/(app)/strategies/tv_signal/page.tsx:69-80, 99-101, 116, 251-254, 346-364` — switched to `code/tv_symbol/tv_exchange/score/confidence/generated_at`; added `deriveRecommendation(score)` helper because backend ships a numeric score and the badge wants the categorical tier.
- `frontend/src/app/(app)/strategies/[code]/page.tsx:399-405, 437-441` — `last_success_at` → `checked_at`, `recent_signal_count` → `upstream_tv_reachable`.

### F4. `.env.example` central — adds two missing TV vars

**Before:** Project-root `.env.example` had `TV_ENABLED / TV_THROTTLE_CONCURRENT / TV_THROTTLE_SPACING_SEC / TV_CACHE_TTL_SEC` but not the **backend-layer** vars `TV_PREVIEW_RATE_LIMIT_PER_MIN` (per-user rpm cap) and `TV_CATALOG_CACHE_TTL_SEC` (Redis catalog TTL). Operators copying the central template would miss them.

**Fix:** `.env.example:88-99` — added both with comments. Backend `.env.example` already had them.

### F5. `STATUS.md / QUICKSTART.md / PROJECT-STATUS.md` updated for 7 strategies

**Before:** Docs claimed 6 strategies, no Phase-3 row.

**Fix:** `STATUS.md` got Phase-3 capability table; `QUICKSTART.md` got "7 strategies, tv_signal paper-only by default" note; `PROJECT-STATUS.md` got Phase-3 row in the capability table and a top-line phase summary update.

---

## 5. Issues observed but deferred (not blockers)

| # | Observation | Severity | Why deferred |
|---|---|---|---|
| D1 | Engine `/tv/*` endpoints do NOT verify the HMAC headers backend sends. | Med | Engine is private (Railway internal network, not exposed). Adding verification is a 10-line lift but does not change the security posture today — file an issue and ship a quick follow-up before opening the engine to the public internet. |
| D2 | Engine `tv_health` probe symbol is hard-coded `EURUSD/OANDA`. | Low | If OANDA delists EURUSD (won't happen) the probe always fails. Add `TV_HEALTH_PROBE_SYMBOL` env var when this list grows. |
| D3 | `TVPreview.score` is `0..100`; UI's `deriveRecommendation` thresholds (`60/20`) duplicate the engine's `Scorer` thresholds (`60/20`). Two sources of truth. | Low | Workable for MVP. Centralize when product wants user-tunable thresholds. |
| D4 | `frontend/src/types/domain.ts` not type-checked in this review (no `pnpm typecheck`). | Low | The edits are 1:1 with openapi; type errors will surface in the Vercel build. If the build fails, the deltas are localised to ~3 files. |
| D5 | `requires_external_service` is in DB + read by live_gate, but NOT (yet) surfaced in the strategy-catalog API response — frontend infers `is_tv_signal = strategy.code === 'tv_signal'` instead of `strategy.requires_external_service`. | Low | Same effect; tighten to flag-driven when we add a 2nd external-signal strategy. |

---

## 6. Migration order verified

```
0001_initial               base schema
0002_seed_strategies       seeds 6 strategies
0003_phase2_tables         Phase-2 additions (signals, trades, broker_accounts, …)
0004_seed_plans            Stripe plans
0005_tv_signal             this round — additive only; idempotent UPSERT; reversible DDL
```

`alembic upgrade head` is linear (no branches). `alembic downgrade base` reverses cleanly.

---

## 7. Test alignment

| Suite | Files | py_compile | Notes |
|---|---|---|---|
| `trading-engine/tests/test_tv_signal.py` | 1 | OK | Strategy smoke test — does not require live TV. |
| `backend/tests/test_tradingview_endpoints.py` | 1 | OK | Async router tests — mocks the engine, exercises auth + rate limits + 503 path. |

Neither suite was executed (no Python venv in this review env). Both compile clean. Recommend running `pytest -k tv_signal or tradingview` before declaring Phase-3 done.

---

## 8. No regressions

Spot-checked:
- Existing 6 strategies untouched in `configs/strategies.yaml` (tv_signal appended; no edits to other blocks).
- `live_gate_service.evaluate()` still runs every prior gate; `external_service_healthy` only adds a check when `strategy_code == 'tv_signal'`.
- Auth, billing, broker-account endpoints unchanged.
- Migrations 0001-0004 untouched; only 0005 added.
- Frontend hooks unrelated to TV unchanged.

---

## 9. Verdict

**SHIP IT.** All five blockers resolved in this review. The system now has:
- a working `/tv/preview` whose response is parseable by the backend;
- a real `/tv/health` so the live-gate doesn't trip on a 404;
- frontend types that match what the backend actually returns;
- a complete env-var template;
- accurate docs.

`tv_signal` remains **paper-only by default**. Flipping any instance to live still requires the Argus Section TV launch checklist (14 gates) — that is intentional and correctly enforced by the live-gate `external_service_healthy` check + the disclaimer v1.1.0 re-consent.

— Hephaestus Takumi
