# GDPR + PDPA Compliance

> Practical steps for handling personal data of EU + Thai (and other SEA) users.
> **Author:** Argus Hayato | **Date:** 2026-06-15
> **Disclaimer:** this is a practitioner doc, NOT legal advice. Legal review required before launch.

---

## 1. Applicable Frameworks

| Framework | Applies to | Notes |
|---|---|---|
| **GDPR** (EU/EEA) | Any user residing in EU/EEA at time of data collection | Applies regardless of where we are hosted |
| **UK GDPR** | UK residents | Substantively similar to EU GDPR |
| **PDPA (Thailand)** | Thai residents | In force since 2022; substantively GDPR-like |
| **PDPA (Singapore)** | Singapore residents | If we open SG market |
| **PDP Law (Indonesia)** | Indonesia residents | If we open ID market |
| **CCPA / CPRA** | California residents | We BLOCK US users in Phase 2 → out of scope until later |

We design to the **strictest applicable** (GDPR) and the rest follow.

---

## 2. Roles

| Role | Definition | Us |
|---|---|---|
| **Data Controller** | Determines purposes & means of processing | We are this for all user data |
| **Data Processor** | Processes data on behalf of controller | Stripe, Sentry, Cloudflare, email provider, R2 are our processors |
| **Data Protection Officer (DPO)** | GDPR Art. 37–39: monitors compliance | Phase 1: founder serves. Phase 2: appoint formal DPO (can be external service) before exceeding 250 EU users or processing "large scale" (Art. 37(1)(b)) |

Each processor relationship requires a **DPA (Data Processing Agreement)** signed and on file.

---

## 3. Lawful Basis Mapping

For each data category, we declare lawful basis per Art. 6 GDPR:

| Data category | Purpose | Lawful basis |
|---|---|---|
| Email, password hash, name | Account creation + service delivery | **Contract** (Art. 6(1)(b)) |
| MT5 broker credentials (encrypted) | Service delivery (placing trades) | **Contract** |
| Trade history, strategy params | Service delivery + analytics shown to user | **Contract** |
| IP address, UA, login timestamps | Fraud prevention + security | **Legitimate Interest** (Art. 6(1)(f)) — balancing test recorded |
| Audit log of sensitive actions | Compliance + dispute resolution | **Legal obligation + Legitimate Interest** |
| Marketing email | Newsletters, product updates | **Consent** (Art. 6(1)(a)) — separate checkbox, withdrawable |
| Cookies (analytics, tracking) | Product analytics | **Consent** (ePrivacy Directive overlay) |
| Cookies (functional / session) | Authentication | **Strict Necessity** (no consent needed for strictly necessary) |

**Documentation:** Maintain `data-processing-record.md` (ROPA — Record of Processing Activities, GDPR Art. 30) listing categories, purposes, basis, recipients, retention, security measures.

---

## 4. Special Categories — Avoid

We MUST NOT collect Art. 9 special category data: race, political opinions, religion, health, sex life/orientation, genetic, biometric.

If KYC (Phase 3) requires ID document: extra controls — encrypted storage, restricted access, retention minimization, DPIA required.

---

## 5. DPIA Template (Data Protection Impact Assessment)

Required when processing is "high risk" (Art. 35) — and prudent regardless.

```
# DPIA — <feature/system>
Date: <YYYY-MM-DD>
Assessor: <name>
Approver: DPO

## 1. Description
What does the system do? What data flows?

## 2. Necessity & Proportionality
Why is this data needed? Can we use less?
Is the lawful basis valid?

## 3. Risks to Data Subjects
- Risk 1: <description> → likelihood × severity → score
- Risk 2: ...

## 4. Mitigations
- For each risk: what control reduces it?
- Residual risk after mitigation.

## 5. Consultation
DPO opinion. If high residual risk → consult supervisory authority (Art. 36).

## 6. Decision
Approve / Approve with conditions / Reject.

## 7. Review
Cadence + trigger for re-running.
```

**Run DPIA for** (Phase 2 candidates):
- Strategy params storing user trading patterns (alpha proxy).
- IP-based fraud detection.
- Any future KYC.

---

## 6. Data Subject Rights — Workflows

### 6.1 Right to Access (Art. 15) — DSAR

**Endpoint:** `GET /api/v1/users/me/export` → returns a job ID.
**Async job:** within 30 days (legal max), aim for <24h:
- Compile user's data: profile, broker accounts (creds redacted to "connected: yes / no" — never decrypt for export), strategies, backtests, trade history, audit log entries about them, billing records.
- Format: JSON + CSV in a zip.
- Encrypt zip with password sent via separate channel (in-app) or to verified email.
- Provide one-time download link valid 1 hour.

**Defense against scraping:** see threat-model-phase2 AS-P2-10 — rate-limit, 2FA, account age gate.

### 6.2 Right to Rectification (Art. 16)

**UI**: user can edit profile fields directly (name, locale, marketing preference).
**For correctness of system-derived data** (e.g., trade history is what broker reported — we can't rectify; provide note).

### 6.3 Right to Erasure / "Right to be Forgotten" (Art. 17)

**Endpoint:** `DELETE /api/v1/users/me` → enters 30-day grace period.

**Grace period (Phase 2 default):**
- During grace: account disabled (no login), but data retained.
- User can cancel deletion via support request.
- After grace: hard delete (see Anonymize vs Delete below).

**Immediate actions on request:**
- Broker credentials: wipe immediately (cannot wait 30 days with creds in DB).
- Sessions: revoked.
- Email sends: stop.

**Hard delete (after grace):**
- User row + cascaded children deleted from `users`, `broker_credentials`, `strategies`, `backtests`, `trades`, etc.
- Audit log entries: **retain** (legitimate interest + legal obligation for trade records).
  Anonymize the actor — `user_id` replaced with `redacted-{hash}`. Audit log keeps the action but not the identity.
- Stripe customer: delete via Stripe API (Stripe will retain limited financial records for legal compliance — disclose in privacy policy).
- R2 backups: backups containing user data are retained per backup retention; we cannot reach back into all backups to erase, but we MUST disclose this and ensure that on restore, deleted users are re-deleted.

**Exceptions to erasure** (Art. 17(3)): legal obligation (tax/AML records), legal claims, public interest. Document any case we invoke.

### 6.4 Right to Restriction (Art. 18)

**Endpoint:** flag in account `restrict_processing=true`. While set: account read-only; no new processing.

### 6.5 Right to Data Portability (Art. 20)

The DSAR export (Art. 15) covers this — provided in machine-readable JSON.

### 6.6 Right to Object (Art. 21)

**Marketing**: unsubscribe link in every marketing email → toggles `marketing_consent=false` immediately.
**Legitimate interest processing**: handled case-by-case via support email; we re-balance.

### 6.7 Right not to be subject to automated decision-making (Art. 22)

Our trading bot **executes** decisions per user-configured strategy — this is the user's automated decision, not ours, and serves the user. Document this.
If we add a "robo-advisor" recommending strategies, Art. 22 becomes directly relevant — handle then.

---

## 7. Breach Notification

| Authority | Trigger | Deadline | Process |
|---|---|---|---|
| **EU lead DPA** | Personal data breach (Art. 33) likely to result in risk to data subjects | **72 hours** from awareness | Identify lead DPA (one-stop-shop) — for us hosted in EU, the DPA of host country |
| **Thai PDPC** | PII breach affecting Thai data subjects | **72 hours** | Online form at PDPC website |
| **Affected users** (high risk to rights) | Required by Art. 34 + PDPA | "Without undue delay" — practically same 72h | Direct email |

**Pre-position**:
- Template letters in `incident-response-playbook.md`.
- Pre-identified primary contact at each DPA (research now, not during incident).
- Incident response includes "is this a notifiable breach?" decision in playbook.

**Records (Art. 33(5))**: keep internal record of all breaches (notifiable or not) including facts, effects, remedial action.

---

## 8. Cross-Border Transfer

GDPR Chapter V restricts transfer outside EU/EEA without adequate protection.

| Receiving country | Mechanism |
|---|---|
| Within EU/EEA | Free flow |
| UK | Adequacy (EU has adequacy decision for UK) |
| Switzerland | Adequacy |
| **US** | We are NOT operating US data flows in Phase 2 (block US users). Future: EU-US Data Privacy Framework certification OR SCCs |
| Singapore | Adequacy (recently granted) or SCCs |
| Thailand | NOT in EU adequacy list as of 2026 — use **Standard Contractual Clauses (SCCs)** for any EU-personal-data flow to TH-hosted services |

**Our hosting decision:**
- Backend: Hetzner EU (Germany or Finland) — keeps EU data in EU.
- mt5-bridge: location may be near broker (often LD4 London, NY4 NYC, or Asia). For EU customers, place bridge in EU or use SCCs for transfer to non-EU bridge.
- Postgres: same region as backend.
- R2 backups: Cloudflare R2 jurisdiction setting (EU jurisdiction available).

**DPA between us and processors covers SCCs where needed.**

---

## 9. Cookie Banner

ePrivacy Directive (and PDPA emerging guidance) requires:
- **Strictly necessary cookies**: no consent needed (session, CSRF, auth).
- **Analytics cookies**: consent required (opt-in, not opt-out, not pre-ticked).
- **Marketing cookies**: consent required.
- **Granular** controls (not "accept all" vs "exit").
- **Reject all** as easy as "accept all" (CNIL France enforces this).
- **Withdrawable** at any time (footer link).

**Tooling**: lightweight consent solution — `consent-manager` (segment.io), `klaro!`, or custom. Avoid heavy SaaS that itself loads tracking before consent.

**Default**: no analytics or marketing cookies fire until consent. Strictly necessary fire on first load.

---

## 10. Privacy Policy + Terms of Service — Outline (Legal Review Required)

### Privacy Policy
1. Who we are (legal entity, contact, DPO email).
2. What data we collect (categories, sources).
3. Why we collect (purposes, lawful basis).
4. Who we share with (Stripe, Sentry, Cloudflare, email provider, R2, broker) — link each processor's privacy notice.
5. Retention periods (per category).
6. International transfers + mechanisms (SCCs etc.).
7. Your rights (access, rectification, erasure, restriction, portability, object, withdraw consent).
8. How to exercise rights (in-app + email).
9. Right to lodge complaint with supervisory authority (DPA list).
10. Changes to policy (notification process).
11. Cookies section (link to cookie policy).

### Terms of Service
1. Service description (algorithmic trading tools, not financial advice).
2. Eligibility (age 18+, jurisdiction restrictions).
3. Account responsibilities.
4. Acceptable use.
5. Subscription, billing, refunds.
6. **Risk disclosures** (capital loss possible, no guarantees, past performance, leverage risk, broker-side risks).
7. Limitation of liability.
8. Indemnification.
9. IP rights.
10. Termination (by us, by user).
11. Governing law + dispute resolution.
12. Modifications + notice.

### Risk Disclosure (separate, gated at signup with scroll + tick)
1. Trading carries risk of total loss.
2. We do NOT custody funds; broker (Exness) holds funds.
3. We are NOT a financial advisor; tools only.
4. Past performance does not guarantee future results.
5. Algorithmic strategies can fail catastrophically; kill switch is user's responsibility to use.
6. Leverage amplifies losses.
7. Network / broker / our outages may cause inability to act.
8. Specific to user's jurisdiction warnings.

**Acceptance audit**: timestamp + IP + UA + ToS version logged on accept.

---

## 11. Concrete Checklist (Pre-Launch)

- [ ] Identify host country → lead DPA known.
- [ ] DPO appointed (founder for now; formalize if EU user count grows).
- [ ] ROPA maintained.
- [ ] Privacy Policy published + version-pinned.
- [ ] Terms of Service published + version-pinned.
- [ ] Risk Disclosure gated at signup.
- [ ] Cookie banner live with granular controls.
- [ ] DPAs signed: Stripe, Sentry, Cloudflare, email provider, R2.
- [ ] SCCs in place where needed.
- [ ] DSAR endpoint live + tested.
- [ ] Erasure endpoint live + 30-day grace tested.
- [ ] Breach notification template ready (72h playbook).
- [ ] DPIA done for at-least one Phase 2 high-risk processing.
- [ ] Marketing consent stored separately + withdrawable.

---

## 12. Sign-off

- [ ] Privacy Policy reviewed by legal counsel before public launch.
- [ ] DPAs signed and on file.
- [ ] DSAR + erasure tested in staging.
- [ ] Cookie banner audited (no tracking before consent).

Argus Hayato: ____________ Date: ____________
Zeus Ryujin: _____________ Date: ____________
DPO: _____________________ Date: ____________
