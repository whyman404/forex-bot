# Integration Review — Phase 3.5 (Admin Panel)

> **Reviewer:** Hephaestus Takumi (Senior Developer)
> **Date:** 2026-06-16
> **Round:** R5 (post-Atlas R6 / Eos R6 / Argus R4)
> **Verdict:** **SHIP-IT** — one BLOCKER fixed inline; no remaining hard gates.

---

## 1 — Scope under review

| Track | Agent | Round | Output |
|---|---|---|---|
| Backend admin API | Atlas Goro | R6 | `app/api/admin.py` (22 endpoints), `app/services/admin_service.py`, `app/schemas/admin.py`, `app/middleware/auth.py` (`require_admin` + `require_step_up`), audit-inside-tx, `/readyz` update, `seed_admin.py` env support, openapi.yaml |
| Frontend admin UI | Eos R6 | R6 | `src/app/(admin)/` (8 pages), 10 admin components, 9 admin hooks, `types/admin.ts`, `middleware.ts` role-gate, AppTopbar admin link |
| Security model | Argus | R4 | `admin-security.md`, `threat-model-admin.md`, `incident-response-admin.md`, `admin-onboarding-runbook.md`, secure-defaults §18, secrets-audit 18-23, launch checklist AD1-AD18 |
| Bootstrap seed | Main loop | — | `backend/scripts/seed_admin.py --from-env`, central `.env.example` ADMIN block, `.env.admin` (gitignored) |

---

## 2 — Cross-agent contract verification matrix

| Contract | Backend (Atlas) | Frontend (Eos) | Status |
|---|---|---|---|
| **Step-up TOTP header name** | `X-Step-Up-TOTP` (alias on `require_step_up`) — see `app/middleware/auth.py:100` | **WAS** `X-Admin-Stepup` across 7 files | **FIX APPLIED** — frontend now sends `X-Step-Up-TOTP` (matches backend + openapi.yaml) |
| **Role field** (`/users/me`) | `UserPublic.role: str` + `is_admin: bool` (computed_field) — `app/schemas/user.py:39` | `lib/auth.ts` stores `profile.is_admin` as `user.isAdmin`; middleware + `(admin)/layout.tsx` read `token.isAdmin` / `session.user.isAdmin` | OK — field name `is_admin` flows through unchanged; computed_field guarantees serialization. |
| **Admin route paths** | Mounted `/api/v1/admin/*` (`main.py:285` → `api/__init__.py:37` `prefix="/admin"`) | Hooks call `api.get("/admin/...")` with base `NEXT_PUBLIC_API_URL=...8000/api/v1` → final `…/api/v1/admin/…` | OK — paths align byte-for-byte. |
| **Admin guard semantics** | `require_admin` re-fetches `User` from DB and rejects if `user.role != "admin"` (catches role change after token mint) | `middleware.ts` denies `/admin/*` if `!token.isAdmin`; `(admin)/layout.tsx` second-layer check on session | OK — defence in depth. Backend is authoritative; FE is UX-only as documented. |
| **Audit log on destructive ops** | Atomic — audit row written **inside** the same DB tx as the mutation (no orphan audit / no missing audit) | UI shows toast only on 200 OK | OK. |
| **openapi.yaml admin coverage** | 20+ paths under `tag: admin`; 8 carry `X-Step-Up-TOTP` parameter declaration | TS types in `types/admin.ts` mirror Pydantic schemas field-by-field (`AdminUserListItem`, `AdminUserDetail`, `AdminAuditLogEntry`, `AdminSystemMetrics`, `GlobalKillStatus`, `BroadcastRequest`, `AdminStrategy`, `AdminSubscription`) | OK — spot-checked 4 schemas; no drift. |
| **`/readyz` admin** | Updated to include admin readiness signals | n/a | OK. |
| **`seed_admin.py --from-env`** | Requires `ADMIN_EMAIL` + `ADMIN_PASSWORD`; defaults still warn | n/a | OK — verified by `argparse` inspection + py_compile. |

---

## 3 — Issues found and fixes applied

### BLOCKER (fixed inline) — TOTP step-up header name mismatch

**Symptom:** Every destructive admin operation (ban, delete, unban, reset-password, impersonate, grant subscription, kill-all-strategy, global-kill engage/disarm, broadcast) would have returned **HTTP 403 `ADMIN_STEP_UP_REQUIRED`** because the frontend was sending `X-Admin-Stepup` while the backend (and openapi.yaml) declared `X-Step-Up-TOTP`.

**Root cause:** Eos R6 picked a shorter custom name (`X-Admin-Stepup`) independently; Atlas R6 followed the docstring already in `auth.py` (`X-Step-Up-TOTP`).

**Decision:** Backend + openapi.yaml + Argus docs were the **source of truth** (3-of-4 agree, plus it's the externally-visible API contract). Frontend was changed to match — cheaper diff, no API-versioning concern.

**Fix:** Replaced `X-Admin-Stepup` → `X-Step-Up-TOTP` in 9 files:

```
frontend/README.md
frontend/DEPLOY-VERCEL.md
frontend/src/types/admin.ts                      (1 comment)
frontend/src/components/admin/totp-step-up-modal.tsx  (1 comment)
frontend/src/hooks/admin/use-admin-users.ts      (2 occurrences)
frontend/src/hooks/admin/use-admin-totp-step-up.ts (1 comment)
frontend/src/hooks/admin/use-admin-broadcast.ts  (1 occurrence)
frontend/src/hooks/admin/use-admin-strategies.ts (1 occurrence)
frontend/src/hooks/admin/use-global-kill-switch.ts (2 occurrences)
```

Verified with `grep -rln "X-Admin-Stepup" /Users/shinzo/Desktop/whyman404/projects/forex-bot/` → no hits.

### SUGGEST (no action this round)

1. **`require_admin` issues an extra `SELECT users WHERE id=...` per admin request.** This is a deliberate freshness guard (catches role change between token mint and now), and admin traffic is low. Acceptable for MVP. If/when admin endpoints get heavy traffic, cache the re-fetch for ~30s in Redis with explicit invalidation on role change.

2. **`X-Step-Up-TOTP` validates the TOTP code per request — no short-lived step-up token.** The `TotpStepUpModal` UI calls `/admin/auth/step-up` which mints a `step_up_token`, but the modal then attaches the **raw TOTP digits** as `X-Step-Up-TOTP` (because backend verifies the digits, not the token). That's consistent — but the `step_up_token` field on the response is presently unused. Either remove it from the response or wire backend to accept the short-lived token. Park as `TODO(admin-stepup-token)` — not a blocker.

3. **NextAuth `isAdmin` is captured at sign-in and refreshed only on access-token refresh (~15 min cadence).** Backend `require_admin` will still 403 the operation if role was demoted in between (that's the authoritative check), but the UI may show admin nav for up to 15 min after a demotion. Acceptable for MVP.

### NIT (informational)

- `frontend/src/lib/auth.ts` casts `user as unknown as User` in `jwt()` callback. Standard NextAuth pattern; keeps type-narrowing strict. No action.
- `admin/auth/step-up` returns `step_up_token` field that is presently unused (see SUGGEST 2).

---

## 4 — Verification log

```
Step                                                       Result
-----------------------------------------------------------------
grep "X-Admin-Stepup" across repo                          0 hits (post-fix)
grep "X-Step-Up-TOTP" backend + openapi + frontend         consistent
py_compile backend/scripts/seed_admin.py                   exit 0
py_compile app/api/admin.py                                exit 0
py_compile app/services/admin_service.py                   exit 0
py_compile app/schemas/admin.py                            exit 0
py_compile app/middleware/auth.py                          exit 0
py_compile app/api/health.py                               exit 0
yaml.safe_load(docs/api/openapi.yaml)                      OK
seed_admin.py --from-env path                              argparse OK; required env vars checked
pnpm typecheck (Next 15 + TS strict)                       PASS — 0 errors
pnpm build                                                 PASS — 27 routes, 9 under /admin
```

### Build tail (post-fix)

```
✓ Compiled successfully in 4.9s
✓ Generating static pages (27/27)
Route (app)                                 Size  First Load JS
├ ○ /admin                                 171 B         103 kB
├ ○ /admin/audit-log                     2.35 kB         157 kB
├ ○ /admin/notifications                 6.61 kB         171 kB
├ ○ /admin/strategies                    5.82 kB         173 kB
├ ○ /admin/subscriptions                 3.65 kB         171 kB
├ ○ /admin/system                        5.75 kB         151 kB
├ ○ /admin/system/global-kill            6.83 kB         171 kB
├ ○ /admin/users                         8.12 kB         198 kB
├ ƒ /admin/users/[id]                    7.41 kB         174 kB
ƒ Middleware                             61.8 kB
```

---

## 5 — Regression sweep

| Surface | Before Phase 3.5 | After | Result |
|---|---|---|---|
| `/api/v1/admin` stub endpoint | trivial 200 | replaced by 22-endpoint router with `require_admin` dep | OK — no orphan callers in frontend (grepped). |
| `/api/v1/users/me` | returns `UserPublic` | unchanged; now relied on by `lib/auth.ts` for `is_admin` | OK. |
| Total `/api/v1/*` route count | ~30 | 30 + 22 admin = ~52 | OK. |
| Frontend middleware bundle | did not gate `/admin/*` | gates `/admin/*` on `token.isAdmin` | OK. |
| `pnpm build` | 18 routes | 27 routes (+9 admin) | OK. |
| Existing dev login `admin@local / changeme123` | works via raw-SQL seed | unchanged; now also supports `--from-env` path | OK. |

No regressions.

---

## 6 — Specific reconciliation calls

### 6.1 Step-up TOTP header name

**Reconciled to:** `X-Step-Up-TOTP`
**Why:** Backend `require_step_up` dep already uses this alias; openapi.yaml documents it as the parameter; Argus threat-model and runbook reference it; only the frontend used `X-Admin-Stepup`. Smaller diff, no API-versioning concern, no client-library churn.
**Action taken:** Find-and-replaced across 9 frontend files; verified zero remaining `X-Admin-Stepup` references; rebuilt FE successfully.

### 6.2 NextAuth `session.user.role` field

**Reconciled to:** `isAdmin: boolean` exposed on `session.user`.
**Why:** Backend `UserPublic` exports both `role: str` and `is_admin: bool` (computed field). Frontend convention is camelCase. `isAdmin` is a strict boolean → easier to gate UI, no string comparison risk.
**Action taken:** No change needed — `lib/auth.ts` already maps `profile.is_admin → isAdmin`; middleware + `(admin)/layout.tsx` read `token.isAdmin`. Verified.

---

## 7 — What ships when user merges this

1. Admin panel UI at `/admin/*` (8 pages, role-gated) — non-admins are redirected to `/dashboard` with a clear 403 note in the layout.
2. 22 admin API endpoints under `/api/v1/admin/*`, all gated by `require_admin` (DB re-fetch, no stale-token escalation); destructive ops additionally gated by `require_step_up`.
3. Audit log row written **in the same transaction** as every state change (cannot orphan).
4. Step-up TOTP modal flow on FE that POSTs the 6-digit code via `X-Step-Up-TOTP` header (now header-aligned).
5. First-admin seed via `python -m scripts.seed_admin --from-env` reading `ADMIN_EMAIL` + `ADMIN_PASSWORD` from environment (Railway env panel, dev `.env.admin`, or compose `--env-file`).
6. Argus security pack: privileged-access policy, STRIDE+10-scenario admin threat model, incident-response, onboarding runbook, AD1-AD18 launch gates.

---

## 8 — Conditional caveats

None blocking. The two SUGGEST items above (step-up token wiring; admin-cache for re-fetch) can ship in a follow-up without affecting this release.

## 9 — Sign-off

- Contract alignment: OK
- Type safety: OK (`pnpm typecheck` clean)
- Build: OK (`pnpm build` 27/27 routes)
- Static checks: OK (`py_compile` clean, YAML parse OK)
- Security defaults: OK (Argus AD1-AD18 documented)
- Regression: none

**Ship.**

— Hephaestus Takumi
