# Error Contract

> Stable error shape and code namespace for the Forex Bot API.

**Owner:** Atlas Goro
**Status:** Active (binding)
**Last updated:** 2026-06-14

---

## Why a contract?

Errors are a feature, not an afterthought. Frontend, mobile, support tools, and
on-call engineers all depend on these codes. Breaking the contract = breaking
clients silently. Codes are versioned: rename = add new code + keep old for one
release cycle.

---

## Response shape (all non-2xx)

```json
{
  "error": {
    "code": "AUTH_INVALID_CREDENTIALS",
    "message": "Invalid email or password.",
    "details": { "field": "value" },
    "traceId": "5f1f1c2a-3b22-4d04-90b7-d9a4e3a8f2e1"
  }
}
```

| Field      | Required | Notes                                                                |
|------------|----------|----------------------------------------------------------------------|
| `code`     | yes      | Stable, machine-readable. UPPER_SNAKE_CASE. Namespaced by prefix.   |
| `message`  | yes      | Human-readable. Safe to display to end-users (no stack traces).      |
| `details`  | no       | Structured context. Schema may differ per code.                      |
| `traceId`  | no       | Request ID (= structlog `request_id` = OTel trace ID prefix).        |

**Rules:**
- HTTP status code MUST reflect the failure category (no `200 OK` for errors).
- `code` MUST be stable across versions (add new codes; don't repurpose).
- `message` MAY be localized in the future (planned: `Accept-Language` header).
- `details` MUST never leak secrets, stack traces, internal IDs, or PII.

---

## HTTP status mapping

| Status | When                                                            |
|--------|-----------------------------------------------------------------|
| 400    | Malformed request (bad JSON, bad signature, business pre-check) |
| 401    | Authentication missing / invalid / expired                      |
| 402    | Payment required (no active subscription for paid feature)      |
| 403    | Authenticated but not authorized (role, ownership, email unverified) |
| 404    | Resource not found OR not owned by caller (don't leak)          |
| 409    | State conflict (duplicate, illegal state transition)            |
| 422    | Validation failed (schema, business invariant)                  |
| 429    | Rate limited                                                    |
| 500    | Unhandled — bug. Log + alert.                                   |
| 502    | Upstream broker error (Exness MT5, Binance, Stripe)             |
| 503    | Degraded — circuit breaker open, queue full, dependency down    |

---

## Code namespace

### AUTH_* (authentication / session / MFA)

| Code                          | HTTP | Notes                                                       |
|-------------------------------|------|-------------------------------------------------------------|
| `AUTH_INVALID_CREDENTIALS`    | 401  | Login failed. Same code regardless of "user not found" vs "bad password" to prevent enumeration. |
| `AUTH_TOKEN_MISSING`          | 401  | No `Authorization: Bearer` header.                          |
| `AUTH_TOKEN_INVALID`          | 401  | Signature, audience, issuer, or claim invalid.              |
| `AUTH_TOKEN_EXPIRED`          | 401  | `exp` claim in the past. Client should refresh.             |
| `AUTH_REFRESH_REUSED`         | 401  | Single-use refresh token replayed. All sessions revoked.    |
| `AUTH_MFA_REQUIRED`           | 401  | Action requires TOTP; not supplied.                         |
| `AUTH_MFA_INVALID`            | 401  | Wrong TOTP code.                                            |
| `AUTH_EMAIL_NOT_VERIFIED`     | 403  | Need verified email for this action.                        |
| `AUTH_EMAIL_TAKEN`            | 409  | Signup conflict.                                            |
| `AUTH_FORBIDDEN`              | 403  | Authenticated but not authorized.                           |
| `AUTH_RESET_TOKEN_INVALID`    | 400  | Password reset token invalid/expired/used.                  |
| `AUTH_VERIFY_TOKEN_INVALID`   | 400  | Email verification token invalid/expired/used.              |

### BILLING_* (subscriptions, Stripe)

| Code                            | HTTP | Notes                                                     |
|---------------------------------|------|-----------------------------------------------------------|
| `BILLING_PAYMENT_REQUIRED`      | 402  | No active sub for feature gated by plan.                  |
| `BILLING_CHECKOUT_FAILED`       | 502  | Stripe rejected `checkout.sessions.create`.               |
| `BILLING_PORTAL_FAILED`         | 502  | Stripe rejected portal session.                           |
| `BILLING_WEBHOOK_SIGNATURE`     | 400  | Stripe signature header missing or invalid.               |
| `BILLING_WEBHOOK_REPLAY`        | 200  | Duplicate `event.id` — we ack to stop retries.            |
| `BILLING_SUBSCRIPTION_NOT_FOUND`| 404  | User has no subscription row yet.                         |

### BROKER_* (Exness MT5, Binance)

| Code                            | HTTP | Notes                                                     |
|---------------------------------|------|-----------------------------------------------------------|
| `BROKER_INVALID_CREDENTIALS`    | 400  | Login payload schema OK, but rejected by broker.          |
| `BROKER_CONNECTION_FAILED`      | 502  | Network / TLS / broker API timeout.                       |
| `BROKER_NOT_SUPPORTED`          | 400  | Broker code not in the supported list.                    |
| `BROKER_RATE_LIMITED`           | 502  | Broker rejected with their own 429.                       |
| `BROKER_ACCOUNT_NOT_FOUND`      | 404  |                                                           |
| `BROKER_ACCOUNT_LOCKED`         | 423  | Reserved — broker temporarily blocked us.                 |

### STRATEGY_* (catalog + instances)

| Code                              | HTTP | Notes                                                   |
|-----------------------------------|------|---------------------------------------------------------|
| `STRATEGY_NOT_FOUND`              | 404  | Code unknown / unpublished.                             |
| `STRATEGY_INSTANCE_NOT_FOUND`     | 404  |                                                         |
| `STRATEGY_INSTANCE_CONFLICT`      | 409  | Illegal state transition (e.g. start a running one).    |
| `STRATEGY_INSTANCE_LIMIT_REACHED` | 402  | Plan limit on concurrent instances.                     |
| `STRATEGY_RISK_CONFIG_INVALID`    | 422  | Invariant violation in risk config (e.g. SL > 100%).    |

### BACKTEST_*

| Code                       | HTTP | Notes                                                          |
|----------------------------|------|----------------------------------------------------------------|
| `BACKTEST_NOT_FOUND`       | 404  |                                                                |
| `BACKTEST_RANGE_INVALID`   | 422  | `range_end <= range_start`, or unsupported date range.         |
| `BACKTEST_QUEUE_FULL`      | 503  | Backtest worker queue saturated.                               |
| `BACKTEST_PLAN_LIMIT`      | 402  | Plan exceeds monthly quota.                                    |
| `BACKTEST_FAILED`          | 200  | Returned in response body of GET /backtests/{id} when status=failed (NOT a request error). |

### VALIDATION_*

| Code                  | HTTP | Notes                                                              |
|-----------------------|------|--------------------------------------------------------------------|
| `VALIDATION_FAILED`   | 422  | Pydantic validation failed. `details.errors` lists pydantic errors.|

### Generic

| Code             | HTTP | Notes                                                |
|------------------|------|------------------------------------------------------|
| `NOT_FOUND`      | 404  | Generic 404 fallback (used when more specific code n/a). |
| `CONFLICT`       | 409  | Generic conflict.                                    |
| `RATE_LIMITED`   | 429  | Generic rate limit. `Retry-After` header.            |
| `INTERNAL_ERROR` | 500  | Unhandled exception. Logged + Sentry.                |
| `HTTP_<N>`       | N    | Fallback for unhandled HTTPException with status N.  |

---

## Examples

### 401 — token expired

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
X-Request-Id: 5f1f1c2a-3b22-4d04-90b7-d9a4e3a8f2e1
```
```json
{
  "error": {
    "code": "AUTH_TOKEN_EXPIRED",
    "message": "Access token expired.",
    "traceId": "5f1f1c2a-3b22-4d04-90b7-d9a4e3a8f2e1"
  }
}
```

### 422 — validation

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Request validation failed.",
    "details": {
      "errors": [
        {
          "loc": ["body", "password"],
          "msg": "String should have at least 12 characters",
          "type": "string_too_short"
        }
      ]
    },
    "traceId": "..."
  }
}
```

### 429 — rate limited

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded for scope=auth-login",
    "details": { "scope": "auth-login", "limit_per_min": 10 },
    "traceId": "..."
  }
}
```

### 502 — broker connection failed

```json
{
  "error": {
    "code": "BROKER_CONNECTION_FAILED",
    "message": "Could not connect to broker.",
    "details": { "broker": "exness_mt5", "attempts": 3 },
    "traceId": "..."
  }
}
```

---

## Client guidance

- **Switch on `code`**, not on `message` (which may be localized).
- **Always surface `traceId`** to user in error UI ("Show this to support: X") — saves on-call time.
- For 401 with `code` in (`AUTH_TOKEN_EXPIRED`, `AUTH_TOKEN_INVALID`), attempt refresh once before redirecting to login.
- For 402, route user to upgrade page with `code` as context.
- For 429, respect `Retry-After` — exponential back off if not present.

---

## Adding a new code

1. Pick the right namespace (or propose a new one in a doc PR).
2. Add an entry here with HTTP status + when it fires.
3. Add an `AppError` subclass in `app/core/errors.py`.
4. Wire it into the OpenAPI spec for the affected endpoint(s).
5. Add a test that asserts the contract (code + status + envelope).
