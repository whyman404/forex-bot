# API Test Suite — Backend (FastAPI + pytest)

**Owner:** Themis Saori + Atlas Goro
**Tool:** pytest, httpx AsyncClient, testcontainers-python (PostgreSQL 16, Redis 7), respx (HTTP mock), freezegun
**Updated:** 2026-06-14

---

## Layout

```
backend/tests/
├── conftest.py                # fixtures: app, db, redis, auth_user, pro_user, broker_mock
├── factories/                 # factory_boy: UserFactory, BrokerAccountFactory, ...
├── unit/                      # pure module tests
│   ├── test_password_hashing.py
│   ├── test_jwt.py
│   └── test_billing_calc.py
└── integration/
    ├── test_auth.py
    ├── test_broker_accounts.py
    ├── test_strategy_instances.py
    ├── test_backtest.py
    ├── test_billing_webhook.py
    └── test_rate_limit.py
```

`conftest.py` boots Postgres + Redis once per session, truncates tables between tests for speed.

---

## 1. Auth endpoints — `test_auth.py`

| # | Test | Expected |
|---|---|---|
| AUTH-01 | POST /auth/signup with valid payload | 201, user row created, password_hash != plaintext, verification email queued |
| AUTH-02 | POST /auth/signup duplicate email | 409, generic error (no enumeration leak) |
| AUTH-03 | POST /auth/signup weak password | 422 with rule violations listed |
| AUTH-04 | POST /auth/verify-email valid token | 200, user.is_verified=True |
| AUTH-05 | POST /auth/verify-email expired token (freezegun jump +25h) | 410 |
| AUTH-06 | POST /auth/verify-email reused token | 410 |
| AUTH-07 | POST /auth/login valid | 200, access + refresh JWT, refresh httpOnly+Secure+SameSite=Lax |
| AUTH-08 | POST /auth/login wrong password | 401, generic message |
| AUTH-09 | POST /auth/login unverified user | 403 with verify-prompt code |
| AUTH-10 | POST /auth/login 6 wrong passwords in 10 min | 429 + lock for 15 min |
| AUTH-11 | POST /auth/refresh valid refresh token | 200, new access token, refresh rotated |
| AUTH-12 | POST /auth/refresh expired refresh | 401 |
| AUTH-13 | POST /auth/refresh reused (rotated) refresh | 401 + token family invalidated |
| AUTH-14 | POST /auth/logout | 204, refresh cookie cleared, token revoked in Redis |
| AUTH-15 | POST /auth/forgot-password unknown email | 202 (no enumeration) |
| AUTH-16 | POST /auth/reset-password valid token + strong pw | 200, login with new works |
| AUTH-17 | POST /auth/reset-password reused token | 410 |
| AUTH-18 | GET /me without auth | 401 |
| AUTH-19 | GET /me with expired access token | 401 with code=token_expired |
| AUTH-20 | POST /auth/enroll-2fa | 200, otpauth URL returned |
| AUTH-21 | POST /auth/verify-2fa valid TOTP | 200, user.two_factor_enabled=True, backup codes returned once |
| AUTH-22 | POST /auth/login with 2fa enabled, no TOTP | 401, code=2fa_required |
| AUTH-23 | POST /auth/login 2fa valid | 200 |
| AUTH-24 | POST /auth/login 2fa with backup code | 200, backup code consumed (cannot reuse) |

JWT integrity: tamper one byte → 401, signature alg=none → 401, kid swap → 401.

---

## 2. Broker accounts — `test_broker_accounts.py`

| # | Test | Expected |
|---|---|---|
| BA-01 | POST /broker-accounts as user A | 201, returns id, credentials NOT in response, db `credentials_enc` starts with KMS prefix |
| BA-02 | GET /broker-accounts/:id as owner | 200, credentials field absent |
| BA-03 | GET /broker-accounts/:id as another user (IDOR) | **404** (not 403 — avoid existence enumeration); critical security check |
| BA-04 | PATCH /broker-accounts/:id as another user | **404** |
| BA-05 | DELETE /broker-accounts/:id as another user | **404** |
| BA-06 | POST /broker-accounts/:id/test-connection happy path (mocked) | 200, status=connected, latency_ms returned |
| BA-07 | POST /broker-accounts/:id/test-connection bad creds (mocked) | 400, generic message, no creds echoed |
| BA-08 | POST /broker-accounts/:id/test-connection broker down (mocked 5s timeout) | 504, retried zero times in this endpoint |
| BA-09 | Logs do not contain credentials (assert via caplog) | No occurrences of test password in log records |
| BA-10 | Rate limit: 11 test-connection calls in 60s | 11th → 429 |

---

## 3. Strategy instances — `test_strategy_instances.py`

| # | Test | Expected |
|---|---|---|
| SI-01 | POST /strategy-instances (paper, valid) | 201, status=pending |
| SI-02 | POST /strategy-instances live without verified broker | 422 |
| SI-03 | POST /strategy-instances live without paid tier | 402 |
| SI-04 | POST /strategy-instances/:id/start | 200, engine receives start event, status→running |
| SI-05 | POST /strategy-instances/:id/stop (kill switch) | 200, engine receives stop event, status→stopped, audit_log row written |
| SI-06 | POST /strategy-instances/:id/start as non-owner | 404 |
| SI-07 | POST /strategy-instances/:id/stop while not running | 409 |
| SI-08 | GET /strategy-instances list | only own instances returned |
| SI-09 | Lifecycle illegal transition (stopped → running) | 409 |
| SI-10 | Webhook from engine: trade event idempotent on duplicate event_id | only one trade row |

---

## 4. Backtest endpoint — `test_backtest.py`

| # | Test | Expected |
|---|---|---|
| BT-01 | POST /backtests valid range + strategy | 202 with job_id |
| BT-02 | GET /backtests/:job_id pending | 200 status=pending |
| BT-03 | GET /backtests/:job_id done | 200 with metrics block including PF, Sharpe, Max DD, slippage_pct, walk_forward_folds |
| BT-04 | GET /backtests/:job_id as non-owner | 404 |
| BT-05 | POST /backtests start>end | 422 |
| BT-06 | POST /backtests range > 5y | 422 (resource guard) |
| BT-07 | Backtest result is reproducible: same payload → same metrics hash | identical |
| BT-08 | Strategy unknown | 404 |

---

## 5. Billing webhook — `test_billing_webhook.py`

| # | Test | Expected |
|---|---|---|
| WB-01 | POST /webhooks/stripe with valid signature + checkout.session.completed | 200, user.tier→pro, stripe_event row written |
| WB-02 | Tampered body, original signature | 400 (signature verify fail) |
| WB-03 | Replay same event_id 10 sec later | 200 (acknowledge) but no second tier change (idempotent) |
| WB-04 | Out-of-order: customer.subscription.deleted arrives before checkout.session.completed | Final state matches stripe-source-of-truth reconciliation |
| WB-05 | invoice.payment_failed | tier remains pro for grace period, dunning email queued |
| WB-06 | customer.subscription.deleted | tier→free, strategy_instances paused |
| WB-07 | Unknown event type | 200 (acknowledge, no-op) — never 500 to Stripe |
| WB-08 | Timestamp skew > 5min | 400 (anti-replay) |
| WB-09 | Webhook secret rotation: old + new accepted during window | both 200 |

---

## 6. Rate limit — `test_rate_limit.py`

| # | Test | Expected |
|---|---|---|
| RL-01 | 5 login attempts in 60s | 5th → 429, Retry-After header set |
| RL-02 | 60 GET /me in 60s for free tier | 61st → 429 |
| RL-03 | 600 GET /me in 60s for pro tier | within limit |
| RL-04 | 429 response shape includes code, retry_after_seconds | yes |
| RL-05 | Rate limit per user-id, not just IP (carrier-NAT case) | two users from same IP each get full quota |

---

## 7. Cross-cutting

- **Pagination default + max:** every list endpoint returns ≤ 100 items per page, default 20, `?limit=10000` → 422.
- **CORS:** allowed origins only; preflight from disallowed origin → no `Access-Control-Allow-Origin` header.
- **Error format:** every error response matches the documented schema (`{code, message, details?}`).
- **Logs do not include secrets:** caplog assertion that JWT, passwords, broker creds, Stripe secrets never appear in any log record across full suite.
- **OpenAPI contract:** test that every endpoint matches `docs/api/openapi.yaml` using schemathesis.

---

## CI gates

- Coverage `backend/app/` ≥ 80%.
- Integration suite < 4 min wall clock (parallelize with pytest-xdist).
- Schemathesis property tests fuzz each endpoint with 100 examples (nightly with 1000).
