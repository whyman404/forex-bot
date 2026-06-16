# Threat Model — Admin Surface (STRIDE)

**Owner:** Argus Hayato
**Scope:** Phase 3.5 admin panel + `/api/v1/admin/*` endpoints
**Last updated:** 2026-06-16

> "Attackers think in graphs, defenders think in lists." Admin compromise = whole-system compromise. Threat model this surface as the crown jewel.

---

## 1. Components in Scope

| ID | Component | Trust boundary |
|---|---|---|
| C1 | Admin auth (NextAuth JWT + DB role check) | Edge → API |
| C2 | Admin endpoint group `/api/v1/admin/*` | API gateway → handler |
| C3 | Step-up TOTP middleware | API → Redis + user TOTP secret |
| C4 | Impersonation token issuer | API → JWT signer |
| C5 | Multi-admin approval queue | API ↔ DB ↔ Email |
| C6 | Audit log writer + reader | API → DB (append-only) |
| C7 | Global kill switch | API → DB flag + signal to bot workers |
| C8 | Broadcast email sender | API → email provider |
| C9 | User search / list | API → DB (PII risk) |
| C10 | Admin session monitor (anomaly) | API → analytics |

---

## 2. STRIDE Per Component

### C1 — Admin Auth
| Threat | Vector | Mitigation |
|---|---|---|
| **S**poofing | Stolen admin JWT (laptop loss, XSS, SSO replay) | Short session (24h), DB role re-check, JTI denylist, anomaly detection (geo, UA), passkey/WebAuthn roadmap |
| **T**ampering | Modified JWT claims (role escalation) | HS256/RS256 signature, server ignores role claim — DB lookup |
| **R**epudiation | "I didn't do that action" | Audit log with IP/UA/payload; immutable; hash-chained |
| **I**nfo disclosure | JWT leaked in logs / referrer | Cookie httpOnly+SameSite=strict, no Authorization header in browser, request logs scrub Authorization |
| **D**oS | Brute force admin login | Login throttle (5/15min/IP), exponential backoff per email, Cloudflare bot mode |
| **E**levation | User → admin via mass-assign | No mass-assign — explicit allowlist; role only via dedicated endpoint |

### C2 — Admin Endpoint Group
| Threat | Vector | Mitigation |
|---|---|---|
| **S** | Bypass `require_admin` via path-matcher escape (`//admin/x`, `/api/v1/admin/.`, case sensitivity) | Route-tree mount on `APIRouter(prefix=..., dependencies=[require_admin])`; reject non-canonical paths at gateway; integration tests assert 401/403 on every admin path without auth |
| **T** | Mass-assign on user PATCH (`role: admin`) | Pydantic update model — exclude role/is_active/balance; dedicated endpoint for role |
| **R** | Action not logged | Middleware-level audit emit; pre-write fail-open is BUG → integration test `audit_log_count == request_count` |
| **I** | Verbose error returns DB / stack | Generic error in prod; full trace only in Sentry |
| **D** | N+1 in `/admin/users` list | Eager load via select_related; cursor pagination; max page 100 |
| **E** | Sub-router missing dependency | Route-tree mount auto-inherits; lint rule on PR to detect missing dependency on `/admin` routers |

### C3 — Step-Up TOTP
| Threat | Vector | Mitigation |
|---|---|---|
| **S** | Replay TOTP code | Redis SETNX bind code+action+target — single use |
| **T** | TOTP code for action X used for action Y | Code bound to action+target hash via Redis key |
| **R** | TOTP success not logged | Audit row mandatory pre-action |
| **I** | TOTP secret leak (DB dump) | Encrypted at rest with KEK; never in logs; never in error |
| **D** | Brute force TOTP (10^6 / 30s window) | Rate limit 5 tries/5min per admin, lock 30min after 3 fails, alert |
| **E** | Step-up bypassed because middleware skipped (config drift) | Test matrix per endpoint asserts 403 without TOTP header on destructive ops |

### C4 — Impersonation Token Issuer
| Threat | Vector | Mitigation |
|---|---|---|
| **S** | Admin uses impersonation to act as another admin | Block impersonation if target.role==admin |
| **T** | Modify impersonation JWT to extend exp | Signed; server re-validates exp and jti |
| **R** | Impersonator hidden — appears as user | Audit logs BOTH actor_id (user) and impersonator_id (admin) |
| **I** | Token gives access to broker creds | Impersonation token blocks broker creds endpoints + decryption |
| **D** | Admin opens 100 impersonation sessions | Limit 1 active impersonation per admin |
| **E** | Impersonation used to do admin actions | Token type==impersonation, denied at admin middleware |

### C5 — Multi-Admin Approval Queue
| Threat | Vector | Mitigation |
|---|---|---|
| **S** | Admin A forges approval as Admin B | Approval row requires approver_id derived from authed session; cryptographic sign on approval payload |
| **T** | Payload modified after approval | Hash payload at request time; compare on execute |
| **R** | Approval action not logged | Approval insert + execute insert both audit |
| **I** | Approval payload leaks sensitive data in email | Email shows action+target id only, link to panel for details |
| **D** | Mass pending requests fill queue | Per-admin max 10 open requests |
| **E** | Self-approval | Server enforces approver_id != initiator_id |

### C6 — Audit Log
| Threat | Vector | Mitigation |
|---|---|---|
| **S** | Forged audit row attributing to admin X | DB role: only app user inserts, no impersonation of actor_id from request body — actor_id derived from authed session |
| **T** | Update/delete to hide action | REVOKE UPDATE/DELETE on table from app role; hash-chain daily; nightly integrity check |
| **R** | Admin claims "log corrupted" | Hash-chain proves continuity; off-site backup |
| **I** | PII leak in payload column | redact_pii() central helper, DLP scan on writes |
| **D** | Log table grows unbounded | Partition by month, archive to S3 Glacier after 90d |
| **E** | Read audit log of own actions to find detection gap | Read access audited too; SOC reviews admin's own audit-log reads |

### C7 — Global Kill Switch
| Threat | Vector | Mitigation |
|---|---|---|
| **S** | Compromised admin toggles kill | Requires step-up + n-of-m approval |
| **T** | DB flag flipped via SQL injection | Parameterized queries; ORM; SAST |
| **R** | "Who killed switch?" | Audit with actor+co-approver |
| **I** | Flag state reveals strategic info | Flag is binary, no info leak |
| **D** | Kill switch as vandalism — halts all trading, users lose opportunity | n-of-m approval; auto-uncage requires same; per-admin daily limit 1 toggle |
| **E** | Once on, attacker keeps it on | Same as DoS mitigation + alert on every toggle |

### C8 — Broadcast Email
| Threat | Vector | Mitigation |
|---|---|---|
| **S** | Phishing as us | DMARC + SPF + DKIM; broadcast template list — no free-form HTML link |
| **T** | Inject malicious link in template | Templates immutable; only param substitution allowed; URL allowlist |
| **R** | Broadcast not logged | Pre-send audit + recipient list snapshot |
| **I** | Email content leaks subscriber data via cross-tenant | n/a (single tenant) but render-time tested for placeholders |
| **D** | Broadcast spammed to throttle email provider | Per-admin rate 1 broadcast / hour; provider throttle 100k/day |
| **E** | Broadcast → "click here to verify" → admin password reset | URL allowlist; preview required; multi-admin approval for > 10k recipients |

### C9 — User Search / List
| Threat | Vector | Mitigation |
|---|---|---|
| **S** | n/a | — |
| **T** | SQL injection in `q=` param | Parameterized; ORM; SQLi scan in CI |
| **R** | Mass enumeration not logged | Search query + result count audit |
| **I** | Returns broker password / TOTP secret | Pydantic response model excludes secrets; integration test asserts no secret in response JSON |
| **D** | Slow query — full table scan with LIKE | Trigram index on email/name; cursor pagination; rate limit |
| **E** | IDOR — `/admin/users/{id}` with crafted id | Already require_admin so all-users is intended; IDOR is N/A here BUT impersonation of admin id is blocked separately |

### C10 — Anomaly Monitor
| Threat | Vector | Mitigation |
|---|---|---|
| **S** | Attacker spoofs geo via VPN matching admin location | Layered with UA + behavior; passkey roadmap |
| **T** | Disable monitor toggle | Toggle requires multi-admin + audit |
| **R** | Alerts to email only — admin deletes email | Alerts also to Slack + immutable audit |
| **I** | Anomaly model leaks behavior | Internal only |
| **D** | Flood false alerts to desensitize SOC | Tunable thresholds, on-call rotation |
| **E** | n/a | — |

---

## 3. Top 10 Attack Scenarios

### A1 — Admin JWT Exfiltration → Mass Takeover
**Story:** Admin's laptop is compromised by malware → JWT cookie stolen → attacker uses it to call `/admin/users/list`, dump emails, then `POST /admin/broadcast/email` to phish all users with a "verify your account" link to attacker-controlled domain.
**Likelihood:** medium · **Impact:** critical (CVSS 9.6)
**Mitigations:**
- Short session (24h) + IP allowlist (attacker IP fails)
- Step-up TOTP required on broadcast (attacker doesn't have phone)
- Anomaly: new country alert
- Broadcast template allowlist — no arbitrary URLs
**Residual:** acceptable if step-up + IP allowlist active

### A2 — Broken `require_admin` (Matcher Bypass)
**Story:** Developer adds new route `/api/v1/admin-tools/export` thinking it's covered by admin middleware (regex matches `/admin/*`, but tools is not a sub-prefix). require_admin never runs → unauthenticated user calls it.
**Likelihood:** medium · **Impact:** critical
**Mitigations:**
- Route-tree mount on `APIRouter(prefix="/api/v1/admin")` — physical sub-tree
- CI test: enumerate all routes, assert any matching `admin` in handler name has `require_admin` in deps
- Default-deny gateway rule on `/api/v1/admin*` (belt + suspenders)

### A3 — SQL Injection on User Search
**Story:** `q` param in `/admin/users?q=*` interpolated into raw SQL → attacker (compromised admin) uses `' UNION SELECT broker_password ...` to exfiltrate.
**Likelihood:** low (we use ORM) · **Impact:** critical
**Mitigations:**
- Parameterized only; ORM; SAST (Bandit) in CI
- Pentest scope: SQLi fuzz on every admin query param
- Logs: log every admin search query

### A4 — IDOR in `/admin/users/{id}`
**Story:** N/A in classic sense (admin should access all users) BUT IDOR-by-role: admin can `GET /users/{another_admin_id}` and see their TOTP backup codes or session list, then hijack.
**Likelihood:** medium · **Impact:** high
**Mitigations:**
- Response model excludes TOTP secret / backup codes — always
- Session list endpoint not exposed via admin (or step-up + multi-admin)
- Integration test: response JSON for `/admin/users/{id}` MUST NOT contain `totp_secret`, `password_hash`, `backup_codes`, `broker_password`

### A5 — Race Condition on Demote-Then-Action
**Story:** Admin A demotes admin B. B has valid JWT cached, immediately calls `/admin/system/kill-switch` before token re-check kicks in.
**Likelihood:** low · **Impact:** high (DoS)
**Mitigations:**
- DB re-fetch every request (race window ~ DB latency ≤ 50ms)
- Redis pub/sub `revoked_admins` channel pushes JTI to denylist instantly
- Multi-admin approval on kill switch — single demoted admin can't trigger alone

### A6 — Audit Log Poisoning
**Story:** Compromised admin uses SQL injection (if any) or direct DB access to insert fake audit entries blaming another admin for malicious action.
**Likelihood:** low (no direct DB) · **Impact:** critical (incident response confusion)
**Mitigations:**
- Audit row actor_id derived from authed session, not body
- DB role separation: app user has INSERT only; no UPDATE/DELETE
- Hash-chain daily batches — tampering detectable
- Off-site backup to S3 with Object Lock (WORM)

### A7 — Mass Broadcast as Phishing Vector
**Story:** Compromised admin sends broadcast "Click here to verify your MT5 credentials" → users click → credentials harvested → trading account drained.
**Likelihood:** medium · **Impact:** critical (financial)
**Mitigations:**
- Template allowlist — no free-form HTML, no arbitrary URLs (allowlist domain matches platform domain)
- Multi-admin approval for > 10k recipients
- Preview required before send; recipient list snapshot in audit
- Outbound DMARC/SPF for spoof protection
- User notification: "We never ask you to verify MT5 credentials via email" — periodic reminder

### A8 — Global Kill Switch as DoS Vandalism
**Story:** Attacker compromises one admin → toggles kill switch → all users' bots halt during peak news event → users miss opportunities, lawsuit risk.
**Likelihood:** medium · **Impact:** high (reputational + financial)
**Mitigations:**
- n-of-m approval (n=2)
- Auto-revert NOT allowed (must be manual + approved) — but per-admin daily toggle limit
- SOC alert on every toggle (PagerDuty)
- Comms playbook: status page auto-publishes

### A9 — Reset-Password Flood (User Lockout)
**Story:** Compromised admin triggers `/admin/users/{id}/reset-password` on thousands of users → users locked out, support overwhelmed, churn spike.
**Likelihood:** medium · **Impact:** high
**Mitigations:**
- Per-admin rate limit on reset trigger: 50/hour
- Bulk reset (> 10 users) requires multi-admin approval
- Audit + alert on > 100 resets / day

### A10 — Impersonation → Drain via Paper-then-Flip-to-Live
**Story:** Admin impersonates user in paper mode (innocuous), changes EA strategy aggressively, then attacker (also admin) flips user to live mode via separate non-impersonation path → live trades execute with malicious strategy → drains broker account.
**Likelihood:** low (requires two compromises) · **Impact:** critical (financial)
**Mitigations:**
- Impersonation blocks EA strategy change
- Live-mode flip requires step-up by **user** (not admin) — even admin can't flip
- Admin-initiated live mode flip = explicit `POST /admin/users/{id}/force-live` requires multi-admin + user-side confirmation email
- Outbound risk-limit guard: max drawdown per EA per day, hard-stop on broker

---

## 4. Trust Boundary Diagram

```
[Browser] --HTTPS--> [CDN] --> [API Gateway: IP allowlist for /admin/*]
                                    |
                                    v
                              [require_admin: DB role re-check]
                                    |
                                    v
                              [Step-up TOTP middleware] (destructive)
                                    |
                                    v
                              [Multi-admin approval check] (top-tier)
                                    |
                                    v
                              [Handler + audit_log INSERT (write-ahead)]
                                    |
                                    v
                              [Domain action (DB / queue / broker)]
                                    |
                                    v
                              [audit_log UPDATE -> success/fail]
```

Every arrow = trust boundary → control required.

---

## 5. Residual Risk Acceptance

| Risk | Residual | Acceptance |
|---|---|---|
| 1s race after demote before pub/sub | LOW | accept (acceptable for non-financial actions) |
| Admin breakglass abuse | LOW | accept w/ alert + post-incident review |
| Anomaly false negatives | MEDIUM | accept w/ layered controls |
| Insider threat (legitimate admin acts maliciously) | MEDIUM | accept w/ multi-admin + audit |

---

## 6. Open Threats (Roadmap)

- Passkey / WebAuthn for admin (post-launch)
- Hardware token (YubiKey) for kill switch (post-launch)
- SIEM integration (Splunk / Datadog) for real-time alert correlation
- Tabletop exercise quarterly
