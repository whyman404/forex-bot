# Pre-Launch Security Checklist — Live Trading Gate

> **Goal:** Nothing below = no real money on live mode for any user.
> **Owner:** Argus Hayato | **Sign-off required:** Argus + Zeus + Daedalus
> **Date:** 2026-06-14 (template) — to be re-run before each major release

---

## How to use
- This is the **Live Trading Production Gate**. It runs at the end of Phase-2.
- Every item must be GREEN (passing) before the "enable live trading" feature flag is flipped.
- A failed item = blocker. No "we'll fix after launch."
- Sign-off captured in `/docs/security/sign-offs/<date>.md`.

---

## Section A — Authentication & Access

- [ ] **A1.** TOTP 2FA mandatory before "live mode" toggle. Setup flow tested with at least 3 authenticators (Google Authenticator, Authy, 1Password).
- [ ] **A2.** Recovery codes generated, shown once, hash-stored, single-use enforced.
- [ ] **A3.** Email-confirmed sensitive operations (each confirmed by separate code, 10-min TTL):
  - [ ] broker connection create / change / delete
  - [ ] plan change / billing change
  - [ ] password change
  - [ ] 2FA disable
  - [ ] email change
  - (We do NOT support withdrawals — N/A.)
- [ ] **A4.** Step-up re-auth (<5 min freshness) on broker credential edit and live toggle.
- [ ] **A5.** Account lockout after 5 failed logins (sliding 15-min window), per-IP AND per-username counters.
- [ ] **A6.** Have-I-Been-Pwned check on signup + reset.
- [ ] **A7.** Argon2id verified in code review (m=64MB, t=3, p=4).
- [ ] **A8.** JWT TTL: access 15min, refresh 7 days, refresh rotation, denylist on logout.
- [ ] **A9.** JWT signing key on file with mode 0400, owner = app user only.
- [ ] **A10.** Admin endpoints behind separate router + admin-only middleware + audit log.

## Section B — Authorization

- [ ] **B1.** Every owned-resource endpoint has owner-check (BOLA test passes for 100% of endpoints).
- [ ] **B2.** Mass-assignment test passes (input schemas with `extra=forbid` for all endpoints).
- [ ] **B3.** Function-level auth test: regular user gets 403 on every admin endpoint (run via OpenAPI walker).
- [ ] **B4.** ID format = UUID v7 (no integer enumeration).
- [ ] **B5.** Default-deny middleware verified (no endpoint without explicit auth marker).

## Section C — Secrets & Crypto

- [ ] **C1.** Broker credentials envelope-encrypted (AES-256-GCM, DEK-per-row).
- [ ] **C2.** KEK in env with file mode 0400, NOT in git, NOT in CI logs.
- [ ] **C3.** KEK rotation runbook tested in staging (re-wrap migration completes).
- [ ] **C4.** JWT signing key generated on isolated host, audit logged.
- [ ] **C5.** Stripe restricted key used (no refund/transfer permission unless explicit need).
- [ ] **C6.** Stripe webhook signature verified + idempotency table tested with replay attack.
- [ ] **C7.** All `.env` git-ignored; `.env.example` has dummy values only.
- [ ] **C8.** Pre-commit hooks active (gitleaks + detect-secrets) on dev machines AND CI scans repo.
- [ ] **C9.** No plaintext credential in any log (verified by automated grep on staging Loki logs of full e2e test run).
- [ ] **C10.** Sentry scrubber unit-tested with deny-list patterns.

## Section D — Network / Transport

- [ ] **D1.** TLS 1.3 only, modern cipher suites, no SSLv3/TLS 1.0/1.1 (verified via `testssl.sh`).
- [ ] **D2.** HSTS with `preload` directive set; submitted to HSTS preload list.
- [ ] **D3.** Certificate auto-renew (Let's Encrypt / cert-manager / step-ca) tested.
- [ ] **D4.** mTLS between backend ↔ trading engine (private link).
- [ ] **D5.** Postgres / Redis bound to private network only; firewall rules verified.
- [ ] **D6.** Windows VPS RDP behind VPN; public RDP closed; fail2ban active.
- [ ] **D7.** Cloudflare WAF rules: OWASP CRS enabled, custom rules for our patterns.

## Section E — Headers & CSP

- [ ] **E1.** `Strict-Transport-Security` header verified.
- [ ] **E2.** `Content-Security-Policy` strict (no `unsafe-inline`/`unsafe-eval`), tested on every page (Report-Only mode for 1 week first, then enforce).
- [ ] **E3.** `X-Content-Type-Options: nosniff` verified.
- [ ] **E4.** `Referrer-Policy: strict-origin-when-cross-origin` verified.
- [ ] **E5.** `Permissions-Policy` minimized.
- [ ] **E6.** CORS allowlist only our frontend origins (no wildcard).
- [ ] **E7.** Cookies: `Secure; HttpOnly; SameSite=Strict` on all auth + session cookies.
- [ ] **E8.** No `Server` / `X-Powered-By` headers in response.

## Section F — Rate Limit & Quotas

- [ ] **F1.** Per-user rate-limit verified under load test (Redis token bucket).
- [ ] **F2.** Per-IP rate-limit on auth endpoints verified.
- [ ] **F3.** Kill switch endpoint has separate dedicated rate-limit lane (load-tested while flooding other endpoints).
- [ ] **F4.** Body size limit enforced (1MB default, larger only where justified).
- [ ] **F5.** Pagination max page size 100 enforced.
- [ ] **F6.** Postgres `statement_timeout` set (5s default).

## Section G — Input Validation

- [ ] **G1.** All inputs Pydantic-validated; no raw dict from request.
- [ ] **G2.** `extra=forbid` on all input schemas.
- [ ] **G3.** Lint rule active: ban `text()` SQL with f-string.
- [ ] **G4.** File upload: magic-byte + extension + size enforced.
- [ ] **G5.** No `eval`/`exec`/`pickle.loads` on user input (grep-verified in CI).
- [ ] **G6.** SSRF-safe URL handling (allowlist + RFC1918 deny + DNS pin) — for any feature that accepts URL.

## Section H — Dependency / Supply Chain

- [ ] **H1.** `pip-audit` clean on direct deps (no Critical/High open).
- [ ] **H2.** Snyk clean on backend + frontend.
- [ ] **H3.** `npm audit` clean.
- [ ] **H4.** Lockfiles enforced with hash pinning.
- [ ] **H5.** SBOM generated per build (CycloneDX / SPDX), stored.
- [ ] **H6.** Renovate / Dependabot active, weekly PR cycle.
- [ ] **H7.** All GitHub Actions pinned to commit SHA.
- [ ] **H8.** Container images: minimal base (distroless / alpine), non-root user, no `latest` tag.
- [ ] **H9.** Container scan (Trivy) clean.
- [ ] **H10.** Build provenance (SLSA L2 target) — cosign-signed artifacts.

## Section I — Observability / Detection

- [ ] **I1.** Sentry connected backend + frontend + trading engine.
- [ ] **I2.** Sentry `before_send` scrubber unit-tested.
- [ ] **I3.** Loki ingesting structured JSON logs from all services.
- [ ] **I4.** Prometheus + Grafana dashboards live: auth failures, 5xx, p99 latency, trade execution latency, broker connection status.
- [ ] **I5.** Alerting rules wired to Slack / email:
  - [ ] >50 auth failures / 5min
  - [ ] >10 5xx / min on any endpoint
  - [ ] broker disconnect > 1 min for any active live user
  - [ ] kill switch triggered
  - [ ] KEK access from unexpected process
  - [ ] strategy file change detected
  - [ ] sanctions match on signup
- [ ] **I6.** Audit log (hash-chained, append-only) writing for all sensitive events.
- [ ] **I7.** Logs retention: 90 days hot, 1 year cold (PDPA-compliant).

## Section J — Backup / DR

- [ ] **J1.** Postgres daily backup encrypted (age / gpg) to off-site bucket with object-lock.
- [ ] **J2.** Backup KEK separate from prod KEK (independent recovery).
- [ ] **J3.** **Restore drill done** — fully restored to staging, app boots, data verified. **Documented timestamp.**
- [ ] **J4.** RPO ≤ 1 hour (WAL streaming), RTO ≤ 4 hour stated and tested.
- [ ] **J5.** Old KEKs (N-1, N-2) in cold storage, documented retrieval procedure.

## Section K — Kill Switch & Safety

- [ ] **K1.** User-side kill switch button tested (one click, no confirm needed in emergency).
- [ ] **K2.** Admin override kill switch tested.
- [ ] **K3.** Automatic triggers tested:
  - [ ] Max DD breach (per-user threshold)
  - [ ] Daily loss breach
  - [ ] Broker disconnect > 5 min
  - [ ] Anomaly (>X orders / min)
- [ ] **K4.** Kill switch endpoint independently rate-limited (separate lane).
- [ ] **K5.** Re-arm flow requires step-up + cooling period.
- [ ] **K6.** Kill switch chaos test: simulate broker disconnect, verify engine pauses + alerts user.

## Section L — Legal / Compliance

- [ ] **L1.** T&C published, version-pinned, accepted at signup with audit.
- [ ] **L2.** Privacy Policy published; PDPA + GDPR-compliant items.
- [ ] **L3.** DPA executed with Stripe, Sentry, Cloudflare.
- [ ] **L4.** Risk warning gate on signup (scroll + tick).
- [ ] **L5.** Strategy page disclaimer visible above all performance numbers.
- [ ] **L6.** Cookie banner (if EU users allowed).
- [ ] **L7.** Geo-block list active for restricted jurisdictions (until lawyer review).
- [ ] **L8.** OFAC sanctions check on signup (or country-block as interim).
- [ ] **L9.** Data export endpoint for user (PDPA / GDPR right to access).
- [ ] **L10.** Data deletion flow tested (right to erasure, with broker creds wiped immediately).

## Section M — Penetration Test

- [ ] **M1.** Internal pentest (Argus) complete with all High+ resolved.
- [ ] **M2.** External pentest (Phase-3 before scale) scheduled.
- [ ] **M3.** Bug bounty / vuln disclosure policy posted at `/security` (security.txt RFC9116).

## Section N — Incident Response

- [ ] **N1.** Incident response playbook published (`incident-response-playbook.md`).
- [ ] **N2.** On-call rotation defined and tested with a chaos drill.
- [ ] **N3.** Status page (status.<domain>) live.
- [ ] **N4.** Breach notification template ready (PDPA: 72 hours).
- [ ] **N5.** External counsel contact in playbook.

---

## Sign-off

```
Argus Hayato (Security): __________  Date: __________
Daedalus Souta (Tech Lead): _______  Date: __________
Zeus Ryujin (PM): _________________  Date: __________
```

NO LIVE MODE WITHOUT ALL THREE.
