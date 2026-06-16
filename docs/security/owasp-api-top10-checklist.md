# OWASP API Security Top 10 — Mapped to Our Codebase

> Each item: definition, our exposure, **defense in our stack**, owner, status
> **Author:** Argus Hayato | **Date:** 2026-06-14
> **Reference:** OWASP API Security Top 10 (2023 edition, still current 2026)

---

## API1:2023 — Broken Object Level Authorization (BOLA / IDOR)

**Definition:** API exposes objects via ID, attacker manipulates ID to access other users' resources.

**Our exposure:** **HIGH** — endpoints like `/orders/{id}`, `/strategies/{id}`, `/broker-credentials/{id}`, `/api/v1/positions/{id}`.

**Defenses:**
- **Centralized auth dep** in FastAPI (`Depends(require_owner(resource))`) — checks `resource.owner_id == current_user.id`.
- **No raw integer IDs** — use UUID v7 (unguessable + sortable, coordinate with Mnemosyne).
- **Resource fetcher pattern:** never `db.query(Order).filter(id=x)`; always `db.query(Order).filter(id=x, owner_id=user.id)`.
- **Test gate:** PyTest fixture creates 2 users; every read/write endpoint has a "user B cannot access user A's resource" test.
- **Lint:** ban direct `.get(id)` on owned models without `.filter_by(owner_id=...)` via custom ruff rule or grep guard.

**Owner:** Atlas | **Status:** spec'd, implementation Phase-1.

---

## API2:2023 — Broken Authentication

**Definition:** Auth weak — easy to bypass / brute-force / steal token.

**Our exposure:** **CRITICAL** — login, 2FA, JWT.

**Defenses:**
- **Argon2id** for passwords (m=64MB, t=3, p=4) — bcrypt fallback only for legacy.
- **HIBP password check** on signup + reset (k-anonymity API, no PII sent).
- **Account lockout:** 5 failed → 15min lock + email warn; sliding window per username AND per IP (separate counters).
- **2FA TOTP mandatory for live trading** (and for sensitive ops: broker credential change, plan change, password change).
- **JWT:**
  - RS256, `kid` header, key rotation supported.
  - Access token TTL 15min, refresh 7 days, refresh rotation on each use.
  - Refresh stored hashed (sha256) in DB so revocation possible.
  - `jti` in denylist on logout.
- **No session in localStorage** — httpOnly + Secure + SameSite=strict cookies.
- **Email confirmation on signup** + on sensitive ops.
- **Step-up auth:** broker credential edit and live toggle require fresh re-auth (< 5min).
- **WebAuthn-ready:** schema supports adding passkey later.

**Owner:** Atlas | **Status:** Phase-1 sprint.

---

## API3:2023 — Broken Object Property Level Authorization (mass assignment / data exposure)

**Definition:** API blindly binds request payload to internal model, or returns more fields than needed.

**Our exposure:** **HIGH** — Pydantic makes this easy AND dangerous.

**Defenses:**
- **Explicit Pydantic schemas** per endpoint:
  - `UserCreateRequest` (only writable: email, password, name)
  - `UserPublicResponse` (only safe: id, email, plan, created_at)
  - `UserAdminResponse` (separate, includes flags)
- **NEVER** `model_dump()` directly to response.
- **NEVER** `**request.dict()` into ORM constructor — explicit field assignment.
- **`Config.extra = "forbid"`** on all input schemas (reject unknown keys).
- **Hidden fields** (admin_flag, role, balance_internal) MUST NOT be in any user-facing response model.
- **Test:** snapshot test of response fields per endpoint; CI fails if new field appears without review.

**Owner:** Atlas | **Status:** schema templates in Phase-1.

---

## API4:2023 — Unrestricted Resource Consumption

**Definition:** No rate limit / quota → DoS, billing abuse, brute force.

**Our exposure:** **HIGH** — open endpoints + ML inference + DB queries.

**Defenses:**
- **Per-user rate limit** (Redis token bucket): default 60/min, premium 300/min.
- **Per-IP rate limit** on auth endpoints: login 5/15min, signup 3/hour, password reset 3/hour.
- **Burst lane for kill switch** — separate Redis counter so attacker spamming `/orders` can't lock user out of `/kill`.
- **Request timeout:** Uvicorn 10s default, 30s for backtest.
- **Body size limit:** 1MB default; uploads gated.
- **Pagination required** on list endpoints — max page size 100.
- **SQL query timeout:** 5s default at Postgres `statement_timeout`.
- **Backtest queue depth limit** per user (3 concurrent max).
- **Stripe API calls rate-limited** locally to avoid hitting their limit.

**Owner:** Atlas + Hestia | **Status:** middleware spec done.

---

## API5:2023 — Broken Function Level Authorization

**Definition:** Regular user calls admin endpoint, gets through.

**Our exposure:** **MEDIUM** — admin and user APIs share base.

**Defenses:**
- **Two router prefixes:** `/api/v1/` (user) and `/api/v1/admin/` (admin).
- **Admin router has separate `Depends(require_admin)`** at router level (not per-endpoint, so impossible to forget).
- **Role checks server-side only**; client `role` field is ignored.
- **Admin endpoints log audit always.**
- **Admin requires step-up** (re-auth + IP allowlist optional).
- **Default deny:** new endpoint without explicit `Depends(require_user)` returns 401.
  - Implementation: app-level middleware that scans router and rejects endpoints lacking the marker.

**Owner:** Atlas | **Status:** middleware spec, enforcement test in Phase-1.

---

## API6:2023 — Unrestricted Access to Sensitive Business Flows

**Definition:** Attacker automates legitimate flow at scale (e.g., signup bot, scalp coupon).

**Our exposure:** **MEDIUM** — promo codes, trial signup, backtest abuse.

**Defenses:**
- **CAPTCHA** (Cloudflare Turnstile) on signup, password reset, contact form.
- **Email verification gate** before key flows.
- **Device fingerprint** (lightweight, non-PII): flag rapid multi-account from same fp.
- **Promo code per-user limit + per-email-domain limit.**
- **Backtest:** premium-only or 5/day for free tier.
- **Anomaly alert:** new 50 signups/hour from same /24 → Slack alert.

**Owner:** Atlas + Eos (frontend) | **Status:** Phase-2.

---

## API7:2023 — Server Side Request Forgery (SSRF)

**Definition:** API fetches a URL from user input → attacker pivots to internal services / cloud metadata.

**Our exposure:** **MEDIUM** — webhook URL (future), avatar upload by URL (future), import from URL (backtest data).

**Defenses:**
- **URL allowlist by scheme + domain.**
- **Resolve hostname → reject if RFC1918 / RFC4193 / 127.0.0.0/8 / 169.254.169.254 / ::1.**
- **DNS pin** (resolve once, connect to the same IP — prevent DNS rebinding).
- **Disable HTTP redirects** OR re-validate on every hop.
- **Timeout 5s, max response 5MB.**
- **Outbound proxy** with allowlist (Phase-2): all outbound from backend through a forward proxy with allowed FQDNs.
- **Cloud metadata defense:** even if SSRF, IAM role on host has no `*` permissions (least privilege).

**Owner:** Atlas | **Status:** library wrapper to be built.

---

## API8:2023 — Security Misconfiguration

**Definition:** Defaults, debug on, missing headers, verbose errors, open CORS.

**Our exposure:** **MEDIUM** — easy to mess up FastAPI defaults.

**Defenses:**
- **Security headers** (via middleware):
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  - `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://api.stripe.com; frame-ancestors 'none'; base-uri 'self'; object-src 'none';`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: geolocation=(), camera=(), microphone=()`
  - `X-Frame-Options: DENY` (redundant w/ frame-ancestors but defense in depth)
  - Remove `Server`, `X-Powered-By`.
- **CORS:** explicit allowlist, NEVER `*`. Allow only our frontend origin. `credentials: true` only when needed.
- **Debug off** in prod (`DEBUG=false`, FastAPI `debug=False`).
- **Generic error responses** in prod; full to Sentry only.
- **CIS Benchmark** on Postgres, Redis, OS.
- **Docker:** non-root user, read-only FS where possible, no `--privileged`, drop capabilities.
- **TLS 1.3 only**, modern cipher suites.

**Owner:** Atlas + Hestia | **Status:** middleware + IaC Phase-1.

---

## API9:2023 — Improper Inventory Management

**Definition:** Forgotten old API versions, staging exposed to internet, undocumented endpoints.

**Our exposure:** **LOW (now), MEDIUM (growing)**.

**Defenses:**
- **OpenAPI spec is source of truth** (Atlas owns `openapi.yaml`).
- **CI gate:** any endpoint in code without OpenAPI entry fails build.
- **Sunset header** on deprecated versions: `Sunset: <date>`.
- **Staging behind VPN / basic auth.**
- **Hostname inventory:** Hestia maintains, quarterly review.
- **`/docs` and `/redoc` disabled in prod**, or behind admin auth.

**Owner:** Atlas + Hestia | **Status:** Phase-1.

---

## API10:2023 — Unsafe Consumption of APIs (third-party)

**Definition:** We blindly trust third-party API responses (Stripe, Exness, market data).

**Our exposure:** **HIGH** — we consume Stripe + Exness + price feeds.

**Defenses:**
- **TLS verification ON** for all outbound (default but verify).
- **Strict schema validation** of responses (Pydantic on incoming JSON from Stripe).
- **Webhook signature verification** (Stripe-Signature HMAC).
- **Idempotency** on consumed events.
- **Timeouts + circuit breaker** (tenacity / pybreaker).
- **Don't blindly redirect to URLs returned by 3rd party.**
- **Sandbox / test mode for non-prod** — never point staging at live Stripe.
- **Treat 3rd-party JSON as untrusted input** — same scrubbing as user input.
- **Pin Stripe API version** in code; upgrade deliberately.

**Owner:** Atlas | **Status:** wrapper modules Phase-1.

---

## Cross-cutting controls

### Input validation
- All inputs via Pydantic with `extra=forbid` + constrained types (`conint`, `constr`, `EmailStr`, `HttpUrl`).
- File uploads: magic-byte check + extension allowlist + size limit.
- No raw SQL with f-string. Use `text()` only with bound params, ban f-string `text()` via lint.

### Output encoding
- JSON only on API. No HTML rendering server-side (Next.js handles separately).
- Set `Content-Type` explicitly.

### Logging & monitoring (alerting != just logging)
- All auth events → alert on threshold.
- All admin actions → audit log + Slack.
- Sentry on backend + frontend (with PII scrubbing).
- Loki for structured logs; Prometheus for metrics; alerts on `>N` 401, `>N` 5xx, latency p99 spike.

### Dependency scanning (SCA)
- `pip-audit` + Snyk + Dependabot, weekly + on PR.
- `npm audit` + Snyk on frontend.
- Block CI on Critical / High CVE in direct deps; review Medium.
- Hash-pin in lockfiles. Renovate for managed updates.

### Secrets in CI/CD
- GitHub Actions secrets via `environment: production` requiring approval.
- OIDC to cloud, no long-lived keys.
- `add-mask` for any secret.

---

## Status dashboard

| Item | Status |
|------|--------|
| API1 BOLA | spec done, impl Phase-1 |
| API2 Auth | impl Phase-1 |
| API3 Mass-assign | schema pattern done |
| API4 Rate limit | middleware Phase-1 |
| API5 Func auth | router pattern Phase-1 |
| API6 Bus flow | Phase-2 |
| API7 SSRF | wrapper Phase-1 (when needed) |
| API8 Misconfig | headers + IaC Phase-1 |
| API9 Inventory | OpenAPI gate Phase-1 |
| API10 3rd-party | wrappers Phase-1 |

---

## References
- OWASP API Security Top 10 (2023)
- OWASP ASVS L2 (target compliance)
- OWASP Cheat Sheet Series
