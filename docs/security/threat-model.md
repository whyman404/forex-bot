# Threat Model — Forex/Crypto Trading Bot Platform

> STRIDE per component, trust boundaries, top-10 end-to-end attack scenarios
> **Author:** Argus Hayato | **Date:** 2026-06-14 | **Status:** v1.0 (pre-MVP)
> **Methodology:** STRIDE (Microsoft) + Attack Tree + Data Flow

---

## 0. Executive Summary

Trading bot platform holds **broker credentials (MT5 login/password/server)** plus **money flow (Stripe)** plus **PII (KYC-lite)** and triggers **real-money trades on user accounts**.

**Crown jewels (ranked):**
1. **MT5 broker credentials** (per user) — leak = attacker drains user account
2. **JWT signing key** — forge = full account takeover platform-wide
3. **Stripe secret key** — fraud, refund abuse, customer card data scope
4. **Postgres data** — user PII + encrypted creds + audit trail
5. **Trading engine RCE** — attacker can push arbitrary orders to broker

**Highest residual risk after mitigations:**
- **R1.** MT5 credential storage (envelope encryption AES-256-GCM, KEK rotation) — residual: KEK leak via env/process memory.
- **R2.** Signal injection into trading engine — residual: insider/CI compromise inserting malicious strategy.
- **R3.** Account takeover via session theft — residual: XSS + cookie theft if CSP slips.

---

## 1. System Decomposition

### Components

| ID | Component | Tech | Trust Zone |
|----|-----------|------|-----------|
| C1 | Web Frontend | Next.js 15 / browser | Zone-0 (internet, untrusted) |
| C2 | API Gateway | Nginx / Cloudflare / FastAPI ingress | Zone-1 (edge) |
| C3 | Backend API | FastAPI on Linux VPS | Zone-2 (app) |
| C4 | Trading Engine | Python on Windows VPS | Zone-3 (trading) |
| C5 | MT5 Terminal | MetaTrader5 desktop client | Zone-3 (trading) |
| C6 | PostgreSQL 16 | Linux VPS | Zone-4 (data) |
| C7 | Redis 7 | Linux VPS | Zone-4 (data) |
| C8 | Stripe / Omise | External SaaS | Zone-5 (external trusted) |
| C9 | Exness Broker | External MT5 server | Zone-5 (external trusted) |
| C10 | Sentry / Loki / Prometheus | External SaaS / VPS | Zone-6 (observability) |
| C11 | CI/CD (GitHub Actions) | External SaaS | Zone-7 (build/supply chain) |

### Trust Boundaries (key crossings)

- **TB-A:** Internet → API Gateway (Zone-0 → Zone-1) — TLS, WAF, rate-limit, bot detection
- **TB-B:** API Gateway → Backend (Zone-1 → Zone-2) — mTLS or private network, auth header validation
- **TB-C:** Backend → Trading Engine (Zone-2 → Zone-3) — mTLS over private link / VPN
- **TB-D:** Backend / Trading Engine → DB (Zone-2/3 → Zone-4) — TLS, scoped DB user, network ACL
- **TB-E:** Backend → Stripe (Zone-2 → Zone-5) — TLS, Stripe-Signature webhook verification
- **TB-F:** Trading Engine → Exness MT5 (Zone-3 → Zone-5) — proprietary protocol over TLS
- **TB-G:** CI/CD → Production (Zone-7 → Zone-2/3) — OIDC, ephemeral creds, signed artifacts
- **TB-H:** Browser ↔ user (humans) — phishing, social engineering, device compromise

---

## 2. STRIDE per Component

### C1 — Web Frontend (Next.js)

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| **S**poofing | Phishing clone of our domain steals creds | Brand monitoring, domain typo registration, DMARC/SPF/DKIM, WebAuthn-ready future | M (medium) |
| **T**ampering | Malicious browser extension modifies trade form | CSP strict + SRI on all scripts, no `unsafe-inline`, no `unsafe-eval` | M |
| **R**epudiation | User claims "I didn't place that trade" | Audit log with IP, UA, timestamp, signed action token on critical ops | L |
| **I**nfo disclosure | Sensitive data in localStorage / DOM | Never store JWT/secrets in localStorage, use httpOnly cookies, scrub on logout | L |
| **D**oS | Frontend DDoS | Cloudflare / CDN, static asset cache | L |
| **E**lev priv | Client-side admin-flag flip | Server-side authorization checks ONLY, never trust client role | L |

### C2 — API Gateway

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | Header spoofing (`X-Forwarded-For`, `X-Real-IP`) | Trust only edge proxy, strip + re-inject inside | L |
| T | TLS downgrade | TLS 1.3 only, HSTS preload, no SSLv3/TLS1.0/1.1 | L |
| R | Missing access log | Structured access log with request ID, ship to Loki | L |
| I | Verbose error reveals stack | Generic 5xx body in prod, detail to Sentry only | L |
| D | L7 DDoS, slowloris | Cloudflare, conn timeout, rate-limit (per-IP+per-user) | M |
| E | Routing bypass to internal admin | Path allowlist, no `/admin` proxied to public | L |

### C3 — Backend API (FastAPI)

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | Forged JWT | RS256, key rotation, `jti` denylist on logout, short-lived access (15m) | L |
| T | IDOR (`/orders/{id}` accesses another user) | Owner-check middleware on every resource fetch, deny by default | M |
| T | Mass-assignment via Pydantic | Explicit input/output schemas, never `**kwargs` model_dump | L |
| R | No audit on credential change | Append-only audit log table, hash-chained, no UPDATE/DELETE | L |
| I | Sensitive data in error response | Custom exception handler scrubs traceback, generic message | L |
| I | SSRF via webhook URL field | URL allowlist, deny RFC1918, deny metadata IP (169.254.169.254), DNS pin | M |
| D | Slow endpoint exhaustion (regex, query) | Request timeout (10s), SQL query timeout, Redis circuit breaker | M |
| E | Privilege escalation via role param | Role is server-derived, never accepted from client | L |

### C4 — Trading Engine (Python on Windows VPS)

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | Spoofed signal from "Backend" | mTLS + signed message (HMAC) + nonce | L |
| T | Strategy file tampered (signal injection) | File hash pinned at deploy, signed artifacts, read-only mount | M |
| T | Order tampering between signal and broker | Order envelope HMAC, idempotency key, dual-write to audit | M |
| R | "Engine placed wrong trade" no log | Per-order trace ID, broker ticket ID stored, full pre/post snapshot | L |
| I | MT5 credential read from memory dump | Decrypt-just-in-time, zero buffer, no swap (mlock not on Win — accept) | **H** |
| I | Strategy parameter leak (alpha) | Parameter encryption at rest, RBAC on view | M |
| D | Strategy infinite loop blocks others | Process per strategy, watchdog, kill on timeout | M |
| E | Engine RCE places arbitrary orders | Pickle blocked, no `eval`/`exec` on input, deps pinned + scanned | M |

### C5 — MT5 Terminal

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | Fake broker server MITM | Pin Exness server names, TLS validation by MT5 (vendor managed) | M |
| T | Order modified in flight | Vendor TLS, post-trade verification via MT5 history | M |
| R | Trade with no platform record | Sync broker history every N seconds, reconcile | L |
| I | Terminal crash dump contains creds | Disable crash dump upload, restrict access to VPS | M |
| D | Terminal hang | Auto-restart, health probe, alert | L |
| E | RDP weak password to VPS | RDP only via VPN, MFA, fail2ban, no public RDP | M |

### C6 — PostgreSQL

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | App pretending to be replication user | Per-role pg_hba, scram-sha-256, separate replica creds | L |
| T | SQL injection | SQLAlchemy parameterized only, lint ban `text()` with f-string | L |
| R | DBA changes data with no trail | pgaudit, WAL archived, immutable backups | L |
| I | Backup dump leak | Backup encrypted (age/gpg), KMS-wrapped, restricted bucket | M |
| I | Cipher column readable if KEK leaks | KEK in env/KMS, separate from DB user, rotation | **H** |
| D | Connection exhaustion | pgbouncer, per-app conn cap, slow query kill | M |
| E | App user can DROP TABLE | App user has DML only, DDL via migration user | L |

### C7 — Redis

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | Unauth client connects (default Redis = open!) | requirepass + ACL + bind 127.0.0.1 / private net | L |
| T | Key poisoning | Namespace per tenant, signed values for critical keys | L |
| R | No log of session change | AUDIT via app-side, Redis SLOWLOG | M |
| I | Session data plaintext on disk (RDB) | RDB on encrypted volume, AOF off by default in cache role | M |
| D | Memory exhaustion | maxmemory + LRU eviction policy, per-key TTL | L |
| E | Lua script abuse | Disable Lua (`--enable-modules=no`), or restrict | L |

### C8 — Stripe / Omise

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | Webhook spoof (attacker hits `/webhook/stripe`) | Verify `Stripe-Signature` with secret, reject unsigned | L |
| T | Replay of old webhook | Track event ID idempotency table, reject duplicates | L |
| R | No record of refund decision | Store full Stripe event JSON + decision rationale | L |
| I | Cardholder data on our server | NEVER touch PAN — use Stripe Elements / Checkout, PCI SAQ-A scope | L |
| D | Stripe outage | Graceful degrade, queue webhooks for retry | M |
| E | API key leak grants refund power | Restricted key (no refund/transfer), restricted IP, rotation 90d | M |

### C9 — Exness Broker

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | Account takeover at broker level | Out of our control — encourage user to enable broker-side 2FA | M |
| T | Slippage / requote dispute | Snapshot quote at decision time, store with order | M |
| R | Broker denies trade was placed | Store broker ticket ID + raw response | L |
| I | Broker leak (not our scope but downstream impact) | Communicate user-side hygiene; we minimize what we hold | M |
| D | Broker API down | Degrade to paper mode, kill switch, alert user | M |
| E | n/a | — | — |

### C10 — Observability (Sentry/Loki/Prometheus)

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | Forged metric push | Auth tokens per scraper, mTLS internal | L |
| T | Log injection (`\n[ERROR] hacked`) | Structured log only (JSON), escape user input | L |
| R | Logs deleted to cover trail | Logs streamed to write-once bucket, retention 90d+ | M |
| I | PII / secret leaked to Sentry | Pre-send scrubber: deny-list (password, MT5 login/pwd, JWT, Stripe key, email) | **H** |
| D | Log volume DoS | Sampling, rate limit on log line, separate quotas | M |
| E | Sentry admin compromise reads stack | Restrict Sentry org, SSO, MFA, scrub at source | M |

### C11 — CI/CD (GitHub Actions)

| STRIDE | Threat | Mitigation | Residual |
|--------|--------|-----------|----------|
| S | PR from fork runs workflow with secrets | `pull_request_target` forbidden, secrets gated by env approval | L |
| T | Action pinned to mutable tag | Pin all actions to commit SHA, use Renovate to upgrade | L |
| R | Untracked deploy | Required workflow runs only via main, sign with cosign | L |
| I | Secrets in build log | `add-mask` for any secret, scan logs for leak patterns | M |
| D | Build queue saturation | Self-hosted runner pool with autoscale, fork PRs limited | L |
| E | Compromised dep escalates to prod | OIDC short-lived creds, no long-lived AWS keys, SLSA build provenance | **H** |

---

## 3. Top-10 End-to-End Attack Scenarios

### AS-1. Mass MT5 credential exfiltration (CRITICAL)
**Attack path:** SQLi or compromised app role → dump `broker_credentials` table → decrypt with stolen KEK from env.
**Pre-conditions:** SQLi vector + KEK access OR direct DB user compromise.
**Impact:** All users' MT5 accounts drainable. Catastrophic financial + reputational loss.
**Detection:** anomalous SELECT volume on `broker_credentials`, KEK access from non-app process, sudden outbound traffic.
**Mitigation:**
- SQLAlchemy parameterized queries only (ban `text()` + f-string in lint)
- KEK in separate process / KMS, never in app env in prod (interim: env w/ strict file ACL)
- Per-row encryption (nonce per row) so dumping table without KEK = useless
- Audit alert on bulk SELECT
- Quarterly KEK rotate with re-wrap migration
**Residual:** Medium — relies on KEK isolation.

### AS-2. Strategy / signal injection (CRITICAL)
**Attack path:** Compromised CI or insider pushes malicious strategy file → engine loads → places attacker-favorable trades.
**Impact:** Targeted account draining via slippage / wash trades.
**Mitigation:**
- Strategy files signed (cosign / minisign), engine verifies signature on load
- Code review required (CODEOWNERS), 2 approvers for `trading-engine/strategies/`
- Diff alert to Slack on strategy change
- Canary: new strategy in paper mode for X days before live
**Residual:** Medium — insider with merge rights remains a risk; mitigate via dual-control + post-deploy diff alarms.

### AS-3. Account takeover via session theft (HIGH)
**Attack path:** XSS or stolen cookie → impersonate → connect attacker broker / change strategy on victim account.
**Mitigation:**
- httpOnly + Secure + SameSite=strict cookies
- CSP strict (no unsafe-inline/eval), DOMPurify on rendered HTML
- 2FA TOTP required for "live mode" toggle and credential edit
- Re-auth (step-up) on sensitive ops
- Concurrent session limit + device fingerprint
**Residual:** Low–Medium.

### AS-4. Stripe webhook spoof (HIGH)
**Attack path:** Attacker hits `/webhook/stripe` with crafted `payment_intent.succeeded` to unlock premium.
**Mitigation:**
- Verify `Stripe-Signature` with HMAC + tolerance window
- Idempotency table on `event.id`
- Webhook secret rotated quarterly
- Endpoint allowlist by Stripe IPs (defense in depth)
**Residual:** Low.

### AS-5. Order tampering between backend and engine (HIGH)
**Attack path:** MITM or insider on private link modifies trade size / symbol.
**Mitigation:**
- mTLS between backend ↔ engine
- Each order signed with HMAC including nonce + timestamp
- Engine rejects orders > X% account or outside whitelist symbols
- Reconcile every N seconds vs broker
**Residual:** Low.

### AS-6. Insider abuse — admin places trades on user account (HIGH)
**Attack path:** Admin role views user creds or directly triggers `/admin/trade`.
**Mitigation:**
- No admin role can decrypt broker creds (separate ABAC scope)
- All admin actions audit-logged + Slack alert
- 2-person rule on sensitive admin ops (impersonation requires approval)
- No "trade as user" admin endpoint — period
**Residual:** Medium — culture + process dependent.

### AS-7. Supply chain — malicious Python/npm package (HIGH)
**Attack path:** Compromised `vectorbt` / `ccxt` mirror or typosquat package → RCE in engine.
**Mitigation:**
- pip-audit / Snyk / npm-audit in CI, block on high/critical
- Pin via hash (`pip install --require-hashes`), lockfiles enforced
- Renovate / Dependabot weekly review
- SBOM generated per build, stored
- Restrict outbound from prod (allowlist broker + Stripe + Sentry only)
**Residual:** High — accept supply chain as ongoing risk; detection-first.

### AS-8. Credential stuffing on login (MEDIUM)
**Attack path:** Known breach DB → credential stuffing → access user platform.
**Mitigation:**
- Argon2id passwords
- Rate-limit login by IP + by username (separate counters)
- Have-I-Been-Pwned password check on signup + reset
- 2FA required for live trading
- CAPTCHA after N failures
**Residual:** Low.

### AS-9. DoS on order endpoint to disable user during market move (MEDIUM)
**Attack path:** Attacker hammers user's order endpoint so user cannot stop loss.
**Mitigation:**
- Per-user rate-limit on order ops (higher quota for premium)
- Kill switch endpoint has separate, untouchable rate-limit lane
- Cloudflare WAF for L7 patterns
- Auto-pause trading if user has > N failed requests in window (notify user)
**Residual:** Medium.

### AS-10. JWT key compromise → platform-wide impersonation (CRITICAL)
**Attack path:** RS256 private key leak (env / backup / CI log).
**Mitigation:**
- Key generated on isolated host, only public key on app
- Key file mode 0400, owned by separate user, mounted secret
- `kid` header in JWT, key rotation supported, rolling renew
- Short-lived access (15m), refresh rotation, denylist on revoke
- Anomaly detection: same `jti` from two geos within Xs
**Residual:** Medium — rotation is the safety net; pre-stage rotate ability.

---

## 4. Risk Register (top items, owner, due)

| ID | Risk | Severity | Owner | Mitigation status | Due |
|----|------|---------|-------|------------------|-----|
| R1 | KEK leak via env | Critical | Argus + Daedalus | KMS migration planned (ADR-005) | Phase-2 end |
| R2 | Strategy signal injection | High | Argus + Kairos | Cosign signing + 2-approver CODEOWNERS | Phase-2 |
| R3 | Sentry PII leak | High | Argus + Atlas | Scrubber + deny-list | Phase-1 end |
| R4 | Supply chain RCE | High | Argus + Hestia | Snyk + pip-audit + hash pin | Phase-1 |
| R5 | JWT key rotation | Medium | Argus + Atlas | `kid` + rotation runbook | Phase-2 |
| R6 | Insider admin abuse | Medium | Zeus + Argus | ABAC + 2-person rule | Phase-2 |
| R7 | DDoS on kill switch | Medium | Argus + Hestia | Separate lane + Cloudflare | Phase-2 |
| R8 | Backup encryption | Medium | Mnemosyne + Argus | age + KMS wrap | Phase-1 |
| R9 | RDP weak on Windows VPS | Medium | Hestia + Argus | VPN-only RDP, MFA | Phase-1 |
| R10 | Stripe restricted key | Low | Atlas + Argus | Use Stripe restricted key | Phase-1 |

---

## 5. Assumptions & Out of Scope (this version)

- Physical security of cloud providers trusted (Hetzner / Contabo SOC 2).
- Broker (Exness) infrastructure trusted (we cannot audit them).
- We do NOT custody funds — user MT5 account is theirs.
- We do NOT touch PAN — Stripe Elements only.
- DDoS at L3/L4 absorbed by Cloudflare; we focus L7.

## 6. Next steps

- Update model when adding: copy-trading, mobile app, KYC tier-2, withdraw feature (if ever).
- Re-run STRIDE before every major architecture change (Daedalus to flag).
- Quarterly threat model review.
