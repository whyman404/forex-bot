# Security Test Cases

**Owner:** Themis Saori (test execution) + Argus Hayato (threat model + advisory)
**Updated:** 2026-06-14
**Companion:** `docs/security/threat-model.md`

---

## 1. Test categories

| Category | Tool | Cadence |
|---|---|---|
| Auth brute force / lockout | pytest + httpx | Per PR |
| JWT integrity / expiry | pytest | Per PR |
| SQL injection | sqlmap (passive) + parametrized fuzz pytest | Nightly |
| IDOR (cross-tenant) | pytest cases below | Per PR |
| CSRF | Playwright | Per PR |
| Secrets in logs | caplog assertions + gitleaks | Per PR |
| Secrets in repo | gitleaks pre-commit + CI | Per PR |
| Dependency CVE | trivy + pip-audit + npm audit | Per PR + nightly |
| OWASP top-10 baseline | OWASP ZAP baseline | Nightly staging |
| Headers / TLS | testssl.sh, securityheaders scan | Per release |
| Container image scan | trivy on built images | Per PR |

---

## 2. Auth brute force / lockout — `tests/security/test_auth_brute.py`

| # | Test | Expected |
|---|---|---|
| SEC-AUTH-01 | 5 wrong passwords in 10 min for same email → 6th → 429 + 15 min lock | 429, lock recorded |
| SEC-AUTH-02 | Lockout is per-account, not just per-IP (attacker can't switch IP to bypass) | still locked |
| SEC-AUTH-03 | Distributed: 5 different IPs each try once same email → counter still ticks | locks at 5 total |
| SEC-AUTH-04 | 2FA: 5 wrong TOTPs → 2FA lock 15 min, account not deleted | locked |
| SEC-AUTH-05 | Reset-password endpoint rate limited to 3/hour/email | 429 |
| SEC-AUTH-06 | Email enumeration: login wrong-pw vs unknown-email → identical response + timing | δ < 50ms median |

---

## 3. JWT — `tests/security/test_jwt.py`

| # | Test | Expected |
|---|---|---|
| SEC-JWT-01 | Token signed with `none` alg | 401 |
| SEC-JWT-02 | Token signed with HS256 but app uses RS256 (algorithm confusion) | 401 |
| SEC-JWT-03 | Tampered payload (decode → modify role=admin → re-encode without resign) | 401 |
| SEC-JWT-04 | Expired access token | 401 with `code=token_expired` |
| SEC-JWT-05 | Refresh token reuse after rotation | 401 + entire token family revoked |
| SEC-JWT-06 | Refresh token used after explicit logout | 401 |
| SEC-JWT-07 | `kid` swap to attacker-controlled key | 401 |
| SEC-JWT-08 | Token issued by different env (staging token on prod) | 401 (issuer mismatch) |
| SEC-JWT-09 | Token at exact exp instant — leeway documented and tested | per spec |

---

## 4. SQL injection — `tests/security/test_sqli.py`

For every endpoint accepting string input, fuzz with payloads `'; DROP TABLE users; --`, `' OR '1'='1`, `\\'; SELECT pg_sleep(5); --`, plus unicode encodings.

Expected:
- 422 (validation) or 400 (sanitization) — **never** 500.
- Response time deviation < 100ms from baseline (catches time-based blind SQLi).
- Audit: every query in `backend/app/db/` uses parameterized SQLAlchemy queries (grep test: `f"…WHERE…{` and `% (`-style interp must be 0 hits in app code).

---

## 5. IDOR — `tests/security/test_idor.py`

Cross-tenant scenarios. User A and B both exist; B owns resource X.

| # | Resource | Method | Expected for A acting on X |
|---|---|---|---|
| IDOR-01 | broker_accounts/:id | GET | 404 |
| IDOR-02 | broker_accounts/:id | PATCH | 404 |
| IDOR-03 | broker_accounts/:id | DELETE | 404 |
| IDOR-04 | broker_accounts/:id/test-connection | POST | 404 |
| IDOR-05 | strategy_instances/:id | GET / PATCH / DELETE / start / stop | 404 |
| IDOR-06 | backtests/:id | GET | 404 |
| IDOR-07 | trades/:id | GET | 404 |
| IDOR-08 | billing/portal | with query `?customer_id=B-id` | 403 (or 404; spec says 403) |
| IDOR-09 | settings/api-tokens/:id | GET / DELETE | 404 |
| IDOR-10 | audit_log filtered to user — A cannot see B rows | only own |

Sample test file: `sample-tests/test_idor_broker_account.py`.

Why 404 not 403: avoids existence enumeration.

---

## 6. CSRF — `tests/security/test_csrf.spec.ts`

- Mutating endpoints require either: Authorization header (bearer) **or** SameSite cookie + custom header.
- Cross-origin form POST without proper headers → 403.
- Cookie attributes verified: `Secure`, `HttpOnly`, `SameSite=Lax` (refresh), `SameSite=Strict` (admin endpoints).

---

## 7. Secrets in logs — `tests/security/test_secret_leakage.py`

Across the full pytest suite, install a session-scoped pytest plugin that scans all logs (caplog) for:
- Test passwords (sentinel values)
- JWT signature segments
- Stripe `sk_test_…` and `whsec_…`
- Broker passwords (sentinel)
- AWS-style keys `AKIA…`

Fail the suite if any match.

Also: gitleaks runs in CI on every PR and on push to main.

---

## 8. OWASP ZAP baseline (nightly)

ZAP baseline against staging URL. Alerts at threshold WARN+ must be reviewed; FAIL on any HIGH.

---

## 9. Dependency scanning

- `pip-audit` (Python) and `npm audit` (frontend) in CI, fail on HIGH+ unless allow-listed with expiry.
- `trivy` scans container images, fail on HIGH+ unfixable in 14d.
- SBOM (CycloneDX) generated per release.

---

## 10. Headers + TLS

Tested by `tests/security/test_security_headers.py` and externally per release with testssl.sh.

| Header | Required value |
|---|---|
| Strict-Transport-Security | max-age ≥ 31536000; includeSubDomains; preload |
| Content-Security-Policy | strict, no `unsafe-inline` except hashed |
| X-Content-Type-Options | nosniff |
| X-Frame-Options | DENY (or CSP frame-ancestors none) |
| Referrer-Policy | strict-origin-when-cross-origin |
| Permissions-Policy | minimal feature set |

---

## 11. Threat-driven scenarios (collab with Argus)

For each STRIDE category in threat model, at least one test case:
- **Spoofing:** SEC-AUTH-01..09 + JWT tampering.
- **Tampering:** webhook signature, JWT signature, request body tamper for transfers.
- **Repudiation:** every state change writes audit_log; test it does.
- **Information disclosure:** IDOR + secrets-in-logs + error messages don't leak stack traces.
- **DoS:** rate limit tests.
- **Elevation of privilege:** role-claim tamper, broker_account access cross-tenant.
