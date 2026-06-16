# Secure Defaults — Team Playbook

> The "paved road" — concrete defaults every engineer uses. Opting out requires justification.
> **Author:** Argus Hayato | **Date:** 2026-06-14
> **Status:** Authoritative — enforced via lint / CI / middleware.

---

## Principle

> Make the secure choice the **default choice**. Make insecure the explicit, reviewed exception.

If you have to type extra characters to be secure, you'll often forget. If you have to type extra characters to be insecure, it's a conscious choice that gets caught in review.

---

## 1. Authentication & Authorization

### 1.1 Auth required by default

- **All endpoints require auth.** Middleware checks for `auth_required=False` marker and rejects requests if the marker is absent.
- **Opt-out is explicit and reviewed.** Public endpoints (signup, login, health, openapi) must have `@public_endpoint` decorator with a code-review-required tag.
- App-level test scans the router and asserts every endpoint either has `Depends(require_user)` / `Depends(require_admin)` OR `@public_endpoint`. Test fails if neither.

### 1.2 Owner check by default

- **Owned resources (Order, Strategy, BrokerCredential, …) use a base repository class** that always filters by `owner_id=current_user.id`. To override (admin), explicit method needed.
- **No `db.get(Model, id)` on owned tables.** Lint rule rejects.

### 1.3 Admin separation

- **Admin endpoints live under `/api/v1/admin/`** with router-level `Depends(require_admin)`.
- **No mixed user/admin routers.**
- **Admin actions audit-logged always.**

### 1.4 2FA & step-up

- **TOTP 2FA mandatory** before live trading mode toggle. Backup codes one-time-use.
- **Step-up re-auth** (< 5 min freshness) required for:
  - Live mode toggle
  - Broker credential edit
  - Password change
  - 2FA disable
  - Email change
  - Plan downgrade w/ data deletion implication

### 1.5 Password storage

- **Argon2id**, parameters m=64MB, t=3, p=4 (tunable per Phase-2 hw benchmark).
- **No SHA / MD5 / bcrypt for new accounts.** bcrypt only for legacy migration window.
- **HIBP check** on signup + reset (k-anonymity API, no PII sent).

### 1.6 JWT

- **Algorithm:** RS256 (NEVER HS256 in prod — symmetric secret leak = forge keys).
- **Access token TTL:** 15 minutes.
- **Refresh token TTL:** 7 days.
- **Refresh rotation:** each use issues a new refresh; old one revoked. Replay = revoke entire family.
- **`kid` header** present; backend supports multiple keys for rotation.
- **`jti` denylist** in Redis for logout / revoke.
- **Refresh stored hashed** (SHA-256) in DB for revocation lookup.

### 1.7 Sessions / cookies

- **httpOnly + Secure + SameSite=Strict** on all auth cookies.
- **`Domain` attr set** to base domain only (not subdomain wildcard).
- **No JWT in localStorage.** Ever.
- **No sensitive data in URL** (no tokens in query string).

---

## 2. Input / Output

### 2.1 Validation

- **All inputs via Pydantic.** No raw dicts from requests.
- **`model_config = ConfigDict(extra='forbid')`** on every input schema.
- **Constrained types:** `EmailStr`, `HttpUrl`, `constr(max_length=N)`, `conint(ge=0, le=MAX)`.
- **File uploads:** magic-byte check + extension allowlist + size limit + virus scan (Phase-2).

### 2.2 Output

- **Explicit response schemas.** Never `model_dump()` an ORM model to response.
- **Snapshot test** of response shape per endpoint.
- **Mask sensitive fields** in response (email partially, never broker password).

### 2.3 SQL

- **SQLAlchemy 2.0 typed queries.** No raw SQL.
- **`text()` only with bound params**, never f-string. Lint rule rejects.
- **Postgres `statement_timeout=5s`** in app role.
- **DDL via separate migration role.**

### 2.4 Templates / HTML

- No server-rendered HTML in API. Frontend handles via React (escapes by default).
- DOMPurify on any rendered user-provided HTML on frontend.

---

## 3. Network / Transport

### 3.1 TLS

- **TLS 1.3 only**, modern cipher suites.
- **Certificate pinning** for outbound to Stripe and other critical APIs (Phase-2).
- **mTLS** between backend ↔ trading engine.

### 3.2 HSTS

- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- Submitted to HSTS preload list.

### 3.3 CSP

```
default-src 'self';
script-src 'self';
style-src 'self';
img-src 'self' data: https:;
font-src 'self';
connect-src 'self' https://api.stripe.com https://sentry.io;
frame-ancestors 'none';
base-uri 'self';
object-src 'none';
form-action 'self';
upgrade-insecure-requests;
```

- **No `unsafe-inline`, no `unsafe-eval`.** Period.
- **Nonce-based** if a future case truly needs inline; never `unsafe-inline`.
- **Stripe Elements**: connect-src + frame-src as required.
- Roll out in `Content-Security-Policy-Report-Only` for 1 week, then enforce.

### 3.4 Other security headers

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), camera=(), microphone=(), payment=()` (allow Stripe domain explicitly)
- `X-Frame-Options: DENY`
- Remove `Server`, `X-Powered-By`.

### 3.5 CORS

- **Explicit origin allowlist.** Never `*`.
- `credentials: true` ONLY where needed.
- Preflight cache 1 hour max.

---

## 4. Rate limit & Quotas

### 4.1 Defaults

- **Per-user**: 60 req/min default, premium 300/min.
- **Per-IP** on auth endpoints: login 5 / 15 min, signup 3 / hour, password reset 3 / hour.
- **Kill switch lane:** separate Redis counter, NEVER blocked by other endpoints.
- **Backtest:** 3 concurrent per user, queue rest.

### 4.2 Body / pagination

- Max body 1MB default.
- Max page size 100.
- Cursor-based pagination preferred over offset (DB perf + stable).

---

## 5. Secrets / Crypto

### 5.1 Storage

- **No secret in git.** Pre-commit gitleaks + detect-secrets.
- **No secret in `.env.example`.** Dummies only.
- **`.env` git-ignored.** CI verifies.
- **No secret in log.** Sentry scrubber + custom log filter.

### 5.2 Cryptography

- **Use PyCA `cryptography`** (Python) and `Web Crypto API` (browser).
- **Never write custom crypto.** Ever.
- **AES-256-GCM** for envelope encryption of broker creds.
- **Per-row DEK** + KEK from env / KMS.
- **HMAC-SHA256** for message authentication (HMAC, not bare SHA).
- **bcrypt → Argon2id** for passwords (above).
- **CSPRNG only** — `os.urandom` / `secrets` module / `crypto.getRandomValues`.

### 5.3 Key rotation cadence

| Secret | Cadence |
|--------|---------|
| KEK | Quarterly + on incident |
| JWT key | 6-month + on incident |
| Stripe / Omise / DB / Redis | Quarterly |
| mTLS certs | Yearly (auto via cert-manager) |

---

## 6. Dependencies / Supply Chain

### 6.1 Backend (Python)

- **`pip install --require-hashes`** in CI / prod build.
- **`uv` or `pip-tools`** for deterministic locking.
- **`pip-audit`** in CI: fail on Critical / High in direct deps.
- **Snyk** weekly + on PR.
- **Renovate** for managed bumps.

### 6.2 Frontend (Node)

- **`npm ci`** (not `npm install`) in CI / prod.
- **`npm audit`** in CI: fail on Critical / High.
- **Snyk** weekly.
- **Renovate** for managed bumps.

### 6.3 Container / OS

- **Distroless or Alpine** base.
- **Non-root user.**
- **Read-only FS** where possible.
- **Drop capabilities**: only NET_BIND if needed.
- **Trivy scan** in CI: fail on Critical / High.

### 6.4 Update SLA

- **Critical CVE:** patched within 7 days from discovery.
- **High CVE:** patched within 30 days.
- **Medium/Low:** monthly review batch.

### 6.5 Pin GitHub Actions to SHA

```yaml
# Bad:  uses: actions/checkout@v4
# Good: uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
```

---

## 7. Logging / Observability

### 7.1 Structured logs only

- JSON only. Field allowlist. No `print()`.
- Request ID propagated end-to-end.

### 7.2 Sentry config

- `before_send` scrubber active.
- `send_default_pii=False`.
- Frontend Sentry: scrub local storage / cookies from breadcrumbs.

### 7.3 Audit log

- Append-only `audit_log` table.
- Hash-chained for tamper detection.
- Events: auth (success/fail), credential ops, plan change, admin action, kill switch, key rotation, sanctions hit.

### 7.4 Retention

- Hot (queryable): 90 days.
- Cold (archive): 1 year for ops, 5 years for audit logs subject to legal hold.

---

## 8. Development / CI

### 8.1 Pre-commit

- gitleaks
- detect-secrets
- ruff / mypy
- eslint / prettier
- branch protection: PR with 1 approval (2 for sensitive areas like `trading-engine/strategies/`, `auth/`, `secrets/`)

### 8.2 CI gates (must pass)

- lint
- type check
- unit tests + coverage threshold
- integration tests
- pip-audit / npm-audit
- Trivy on image
- IDOR test (BOLA walker)
- mass-assignment test
- secret scan on diff

### 8.3 CI secrets

- OIDC only — no long-lived cloud keys.
- Secrets gated behind `environment: production` requiring manual approval.
- `add-mask` for any secret echoed.

### 8.4 Branch protection

- No direct push to `main`.
- 1 approval required (2 for sensitive paths via CODEOWNERS).
- Required status checks: lint, test, security scan.
- No `--no-verify` on hooks.

---

## 9. Frontend Specific

- **Never store JWT / secrets in localStorage.**
- **httpOnly cookies for session.**
- **CSRF token** for state-changing requests where cookie auth is used (double-submit or SameSite=strict alone is the primary defense).
- **Sanitize all rendered HTML** (DOMPurify).
- **No `dangerouslySetInnerHTML` without justification.**
- **Subresource Integrity (SRI)** on all external scripts.
- **No third-party scripts on auth pages** (signup, login, payment).

---

## 10. Common pitfalls — DO NOT

- DO NOT use `pickle.loads` on any input from network / DB / file (RCE).
- DO NOT use `eval` / `exec` (RCE).
- DO NOT use `yaml.load` (use `yaml.safe_load`).
- DO NOT use `subprocess` with `shell=True` and user input.
- DO NOT log the full request body.
- DO NOT echo error stack to user.
- DO NOT disable TLS verification (`verify=False` banned in lint).
- DO NOT trust `X-Forwarded-For` unless behind known proxy.
- DO NOT enable Django/FastAPI debug in prod.
- DO NOT commit `.env`, `secrets/`, `*.pem`, `id_rsa*`.
- DO NOT use `latest` Docker tag in prod.

---

## 11. Quick decision guide

> **"Should I add `auth_required=False`?"** → almost certainly no. Ask Argus.
> **"Can I use this dep that has a Medium CVE?"** → discuss + document risk, plan upgrade.
> **"Can I disable this rate limit for a demo?"** → use a different env. Don't disable in prod.
> **"This endpoint needs to accept any JSON shape."** → No. Define a schema. If truly dynamic, use a typed union.
> **"User asked me to add their custom callback URL."** → SSRF risk. Allowlist domains, never accept arbitrary URL.

---

## 12. Living document

When the team finds a gotcha not covered here, add it. Sec defaults grow with the codebase.

---

## 13. Phase 2 — Stripe Rules (added 2026-06-15)

- **Stripe Checkout (hosted) only.** Never Stripe Elements or custom card forms. See `stripe-pci-scope.md`.
- **Webhook signature verification** mandatory: `stripe.Webhook.construct_event(payload, sig_header, secret)` with explicit tolerance.
- **Idempotency table** (`stripe_events`) UNIQUE constraint on `event.id`; INSERT before processing.
- **Restricted API key** only — NO refund, transfer, payout scope. Refunds via dashboard manual + dual-approval.
- **Webhook secret** separate from API key; rotated quarterly.
- **Entitlement check on every premium action** — `is_premium(user_id)` function reads current `subscriptions` state.
- **Daily reconciliation** — Stripe API vs local DB; downgrade orphans.
- **Resolve user via `customer.id`** (mapped in our DB), not client-controllable `metadata.user_id`.
- **CSP**: `connect-src https://api.stripe.com`; **NO** Stripe.js on non-payment pages.
- **Repo grep gate**: ban card-input field names (`card_number`, `cvv`, etc.) in CI.

## 14. Phase 2 — Email Rules (added 2026-06-15)

- **SPF + DKIM + DMARC `p=reject`** on sending domain. See `email-security.md`.
- **Token generation**: `secrets.token_urlsafe(32)` → store SHA-256 hash in DB.
- **TTL**: verify 1h, password reset 15min, email change 30min, magic link 10min.
- **Single-use** + sibling invalidation on success.
- **Anti-enumeration** on reset request: identical response + timing for known vs unknown email.
- **2FA preserved through reset** — password reset alone cannot bypass 2FA.
- **No tokens visible past landing**: `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, no 3rd-party scripts on reset pages.
- **Provider API token**: send-only scope, IP allowlist where supported.
- **Subject lines**: no PII; generic ("Action required on your account").
- **No URL shorteners** in email body — canonical domain only.

## 15. Phase 2 — mt5-bridge Rules (added 2026-06-15)

- **Bearer token**: constant-time compare (`hmac.compare_digest`), never logged (log SHA256-derived audit_id).
- **Network**: Tailscale or Cloudflare Tunnel; never public + token-only.
- **HMAC envelope** on every order with timestamp + nonce; replay-rejected.
- **Symbol allowlist** + side validation + lot cap + SL required.
- **Magic number namespace**: `hash(user_id, strategy_id)` per order; cross-namespace = reject.
- **Quarterly rotation** + on RDP-anomaly + on incident.

## 17. Phase 3a — TradingView Integration Rules (added 2026-06-16)

> Authoritative defaults for `tv_signal`-family strategies. Read with `tradingview-integration-risk.md`.

- **Backend-only calls.** All TV requests originate from our backend / trading-engine. **Never browser-direct** — no client-side TV SDK; no client-side fetch to TV endpoints. CSP `connect-src` does NOT include `*.tradingview.com`.
- **Response validation.** Every TV response parsed via strict Pydantic model (`extra='forbid'`); schema mismatch → reject + alert + halt strategy on N consecutive failures.
- **Max-age check.** `generated_at` embedded at ingest (server time of successful TV response). Live-gate rejects orders if signal age > 300s.
- **Schema fields enforced** in adapter: `RECOMMENDATION` (enum), `BUY` (int), `SELL` (int), `NEUTRAL` (int), `summary` (dict), `oscillators` (dict), `moving_averages` (dict). Anything else → log + reject.
- **Cache** — Redis 60s per `(symbol, interval)` tuple; cache key includes provider version (`tv_v0.7`) to invalidate on lib upgrade.
- **Throttle** — semaphore max 4 concurrent outbound TV requests; 0.8s spacing between batches.
- **User preview rate-limit** — 6/min per-user; 60/min per-IP — defends our service against scraping.
- **Process isolation** — TV adapter is a separate worker (`trading-engine-tv-worker`). Cannot read `broker_credentials`. Cannot read KEK. Egress allowlist: `scanner.tradingview.com`, `api.tradingview.com`, internal API only.
- **No `eval`/`exec`/`pickle.loads`** on TV response — lint-enforced.
- **TLS verification mandatory** — never `verify=False` against TV. Lint-enforced.
- **Audit log** — every TV call: timestamp, symbol, interval, recommendation, latency, status_code. Retained 90d hot.
- **TV credentials** — currently none (unofficial scraping). If we adopt **paid TradingView API**: envelope-encrypted same as MT5 broker creds (KEK pattern); restricted scope; quarterly rotation. Add as item 18 in `secrets-audit.md`.
- **No PII to TV** — only public symbol + exchange + interval. Verified by adapter unit test.
- **Stable User-Agent** — `User-Agent: WhyMan404-Bot/0.7 (+https://whyman404.com/contact)` — transparent good-faith.
- **Halt-on-health-failure** — 3 consecutive health-check failures (2-min interval) → auto-halt all `tv_signal` strategies; users notified; admin alert.

## 16. Phase 2 — Live Gate Rules (added 2026-06-15)

- **Per-trade re-check** of all 7 gates on every order (not cached past 30s):
  1. live_mode_enabled
  2. 2fa_recent
  3. tos_version_accepted >= current
  4. plan_active and includes_live
  5. broker_connected and balance >= min
  6. kyc_tier sufficient
  7. jurisdiction allowed
- **When in doubt → pause, not trade.**
