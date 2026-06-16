# Incident Response Playbook

> What to do when something goes wrong. Plans beat panic.
> **Author:** Argus Hayato | **Date:** 2026-06-14
> **Review cadence:** quarterly + after every incident.

---

## 0. Roles

| Role | Default holder | Responsibility |
|------|---------------|---------------|
| **Incident Commander (IC)** | Whoever opens the incident — usually on-call eng | Coordinates, decides, owns timeline |
| **Communications Lead** | Zeus (PM) | Internal + external messaging |
| **Tech Lead** | Daedalus | Architecture / fix direction |
| **Security Lead** | Argus | Forensics, containment, comm to authorities |
| **Operations Lead** | Hestia | Infra, kill switch, scaling |
| **Scribe** | Anyone not IC | Timeline log in #incident channel |

**Rule:** The first person to recognize the incident is IC until they hand off. They are NEVER the one alone — pull a second person within 5 minutes.

---

## 1. Severity & SLA

| Sev | Definition | Response | Comm |
|-----|-----------|---------|------|
| **SEV-1 — Catastrophic** | Active financial loss, data breach in progress, all users affected | Immediate. War room within 5 min. | Status page + email within 1h |
| **SEV-2 — Major** | Service down, security control bypassed, multi-user impact | War room within 15 min. | Status page within 30 min |
| **SEV-3 — Significant** | Single-user impact, recoverable, no security breach | Address same business day | Direct DM to affected user |
| **SEV-4 — Minor** | Issue with workaround, no immediate impact | Address next business day | Internal log only |

---

## 2. Universal Incident Flow

1. **Detect** — alert, user report, audit anomaly.
2. **Triage** — assign IC, classify severity, open `#inc-YYYY-MM-DD-<slug>` Slack channel + tracking ticket.
3. **Contain** — stop the bleeding (often: kill switch, revoke tokens, pull plug).
4. **Eradicate** — find and remove root cause.
5. **Recover** — restore service safely.
6. **Lessons learned** — blameless post-mortem within 5 business days.

Throughout: **Scribe maintains timeline** in incident doc with UTC timestamps.

---

## 3. Scenario Playbooks

### IR-1. Credential Leak (broker creds, KEK, JWT key, Stripe key)

**Sev:** SEV-1 always.

**Detect:**
- Alert: KEK accessed from unexpected process.
- Alert: GitHub secret scanner finds leaked secret.
- External report (HackerOne / responsible disclosure).
- User reports unauthorized trade with no platform record.

**Contain (first 30 min):**
1. **Rotate the leaked secret immediately:**
   - JWT key → new `kid`, deploy, force-revoke all sessions.
   - Stripe key → new in Stripe console, deploy, revoke old.
   - KEK → harder: see below KEK procedure.
2. **Disconnect all live users' broker accounts** (force-pause trading engine globally if KEK or DB compromise suspected).
3. **Revoke all active sessions** (clear JWT denylist sentinel).
4. **Disable user logins temporarily** if active exploit ongoing (display maintenance page).

**KEK leak procedure (worst case):**
1. Generate new KEK `vN+1`, deploy.
2. **For every credential row:**
   - Decrypt with old KEK + old DEK → throw away plaintext IMMEDIATELY.
   - Mark row as "REQUIRES USER RE-ENTRY".
3. Email all users: "Your broker connection was reset for security; please re-connect."
4. Until user re-enters, no trading on that account.
5. Investigate how KEK leaked — fix root cause before publishing new KEK to env.

**Eradicate:**
- Find the source (env file, log, backup, accidental commit).
- Remove the leaked secret from anywhere it persists (rotate git history with `git filter-repo` if needed, but assume already compromised).
- Patch the vulnerability that allowed leak.

**Recover:**
- Communicate to users: what happened, what we did, what they should do.
- File PDPA notification if user data exposed (Thailand: 72 hours to PDPC).
- Status page update.

**Lessons learned:**
- Was there a single point of failure? Add layer.
- Could detection have been faster? Improve alert.

---

### IR-2. Stripe Webhook Spoof

**Sev:** SEV-2 if attempt detected without success; SEV-1 if subscription granted falsely.

**Detect:**
- Alert: webhook signature verification failures > N/min.
- Alert: subscription granted with no matching Stripe event in our log.

**Contain:**
1. **Verify webhook still has signature verification ON** (regression check).
2. **Reject all unverified webhooks** — return 401 (note: Stripe expects 2xx for delivery, but malicious webhooks aren't Stripe — they're spoofers; for genuine Stripe deliveries verification passes, no issue).
3. **Audit affected user accounts** — any false subscription grants? Reverse them.
4. **Check idempotency table** — any duplicate events processed?

**Eradicate:**
- Patch any verification gap (e.g., we missed verifying signature on one endpoint).
- Add unit test for that gap.

**Recover:**
- Rebill / fix affected users.
- Apologize where needed.

**Reference: Stripe-Signature verification with tolerance window (default 5 min).**

---

### IR-3. Unauthorized API Access (auth bypass / token theft / privilege escalation)

**Sev:** SEV-1 if privileged access (admin); SEV-2 for single-user.

**Detect:**
- Alert: admin endpoint hit by non-admin token (`require_admin` returned 403 but cookie mismatch).
- Alert: same `jti` from two geographic regions within seconds.
- User reports they didn't perform an action shown in their audit log.
- Anomalous resource access (user accessing 100 orders not their own → 100 IDORs detected).

**Contain:**
1. **Revoke the token** (add `jti` to denylist).
2. **Force-logout the affected user** (require re-auth with 2FA).
3. **If admin token compromised** — revoke ALL admin tokens, audit recent admin actions.
4. **Rate-limit by IP and user-agent** of suspected attacker.

**Eradicate:**
- Forensic: how did they get the token? XSS? Phishing? Token in log? IDOR in code?
- Patch the root cause.
- Push patch + force-rotate JWT signing key if mass compromise possible.

**Recover:**
- Audit all actions of compromised account.
- Reverse fraudulent actions (subscription, broker connection change).
- Notify affected user(s).

---

### IR-4. Suspected Unauthorized Trade on User Account

**Sev:** SEV-1 (financial impact).

**Detect:**
- User reports trade they didn't authorize.
- Alert: trade placed for a user whose live mode is OFF.
- Alert: trade volume on user account > 10× their normal.

**Contain (immediate):**
1. **EMERGENCY-STOP that user's trading** (engine flag + kill switch).
2. **Force-disconnect their broker account** (clear in-mem creds, mark "needs re-auth").
3. **Snapshot all evidence**: audit log, broker history, current positions, recent code deploys, recent admin actions.
4. **Contact user via verified email + phone** — confirm: "Did you place these trades?" Do NOT include trade details in the first contact (could be phishing victim already).

**Investigate:**
- Was there a code change to strategy that affected this account?
- Was admin impersonation used? (audit log)
- Was JWT compromised? (geo / device anomaly)
- Was MT5 credential compromised? (decrypt access log)
- Was the engine misconfigured?

**Eradicate:**
- Patch the cause.
- If global cause (bad strategy push), emergency-stop everyone affected.

**Recover:**
- Work with user on broker reconciliation.
- Document for any compensation discussion (per T&C — we are not liable per ToS but acknowledge moral obligation if our bug caused harm; escalate to founders).
- Update detection rules.

---

### IR-5. Database Breach Suspected

**Sev:** SEV-1.

**Detect:**
- Alert: anomalous SELECT volume on `broker_credentials` or `users`.
- Alert: DB connections from unexpected IP.
- Alert: dump file in unexpected location on host.
- External notification.

**Contain:**
1. **Snapshot** current DB (for forensics) — to encrypted offline storage.
2. **Rotate DB credentials** immediately.
3. **Block DB access from compromised host(s)** at firewall.
4. **Force-disconnect all users' broker accounts** (assume creds compromised even if encrypted — assume KEK could be next).
5. **Switch to read-only mode** while investigating.

**Investigate:**
- pgaudit logs for what was accessed.
- App logs for SQL execution patterns.
- Was the access via app role (SQLi?) or direct DB (pg_hba bypass? leaked password?).

**Notify (within PDPA 72h):**
- Thai PDPC if PII exposed.
- Users affected (template ready).
- GDPR if EU users affected (also 72h).

---

### IR-6. Trading Engine Outage / Strategy Misfire

**Sev:** SEV-2 (impact: users may miss exits, take wrong entries).

**Detect:**
- Alert: engine heartbeat lost.
- Alert: order rejection rate spike.
- Alert: broker reconciliation diff (engine thinks open, broker says closed).

**Contain:**
1. **Switch engine to safe mode** (no new orders).
2. **Reconcile open positions** with broker — what really exists.
3. **Decide: hold or close-all** — based on market condition + magnitude.
4. **Communicate to affected users** within 15 min.

**Eradicate / Recover:**
- Fix root cause (broker disconnect? strategy bug? OOM?).
- Resume after smoke test on canary user.

---

### IR-7. Dependency Compromise / Supply Chain Attack

**Sev:** SEV-1 if RCE possible; SEV-2 otherwise.

**Detect:**
- CVE published affecting a direct dep.
- Snyk/Dependabot critical alert.
- News of compromised package (xz-style).

**Contain:**
1. **Identify version in use** (SBOM lookup).
2. **Pin to known-good version** OR fork patch.
3. **Rebuild + redeploy.**
4. **Inspect for backdoor activity**: outbound network logs since suspected compromise date.

**If compromise confirmed in our prod:**
- Treat as IR-1 (assume secrets leaked).
- Forensic snapshot.
- Rotate everything.

---

### IR-8. DDoS / Volumetric Attack

**Sev:** SEV-2.

**Detect:**
- Cloudflare alert.
- p99 latency spike.

**Contain:**
- Enable Cloudflare "Under Attack" mode.
- Increase rate limits temporarily.
- Identify pattern → custom WAF rule.

---

### IR-9. Insider Threat (admin abuse, leaver risk)

**Sev:** SEV-1.

**Procedure:**
- Revoke ALL access (Slack, GitHub, AWS, DB, server, password manager).
- Audit recent actions (admin log + git activity).
- Rotate all secrets the person had access to.
- Legal escalation.

---

### IR-10. Phishing of Our Users (impersonating us)

**Sev:** SEV-2.

**Procedure:**
- Identify the phish domain.
- File DMCA / abuse report with registrar + hosting.
- Notify users via in-app banner + email: "We will never ask you for your MT5 password via email/chat. Beware of impersonators."
- Investigate if any user fell for it → IR-3 for those users.

---

### Phase 2 Additions — see `incident-response-update.md`

- **IR-P2-1.** Stripe chargeback wave
- **IR-P2-2.** mt5-bridge compromised
- **IR-P2-3.** Live engine sending bad signals
- **IR-P2-4.** Subscription bypass exploit
- **IR-P2-5.** Email provider compromise

---

## 4. Communication Templates

### External breach notification (PDPA-compliant skeleton)

> Subject: Important Security Notice from [Company]
>
> Dear [user],
>
> We are writing to inform you of a security incident that may have affected your account. On [date UTC], we detected [brief, factual description of what happened]. Upon discovery we immediately [actions taken: rotated keys, revoked sessions, disconnected broker accounts]. The data potentially affected includes: [list categories — never specific values].
>
> Your immediate actions:
> 1. Re-authenticate at [URL].
> 2. Reset your password.
> 3. Reset your broker password (with your broker, not via us).
> 4. Enable 2FA if not already.
>
> What we are doing: [investigation, audit, remediation summary].
>
> If you have questions, contact: security@[domain]. We are reporting this incident to the relevant authorities as required by law.

### Status page incident template

> [Investigating | Identified | Monitoring | Resolved] — [short title]
> [Time UTC]: [Update]

---

## 5. Forensics quick reference

When SEV-1 incident occurs:
- Snapshot host (`tar` of `/var/log`, `journalctl -xb > journal.log`).
- Snapshot DB (`pg_dump -Fc` to encrypted offline storage).
- Snapshot Loki query: last 24h relevant patterns.
- Capture Sentry events.
- Take screenshots of dashboards.
- Save Cloudflare logs (export).
- **Do not modify** the original disks until forensics done.

---

## 6. Authorities & external contacts

| Who | When |
|-----|------|
| Thai PDPC | PII breach: within 72h |
| EU DPA (if EU users) | PII breach affecting EU users: within 72h |
| Stripe Risk team | Payment fraud / chargeback wave |
| External counsel | Any SEV-1, before public statement |
| Cyber insurance carrier | Once we have coverage (Phase-3) |
| Law enforcement (TICAC if cybercrime) | If criminal act suspected |

---

## 7. Post-mortem template

```
# Post-mortem: <incident name>

Date: <UTC>
Sev: <1/2/3>
Duration: <start → end UTC>
Customer impact: <quantified>

## Summary
<2-3 sentences>

## Timeline (UTC)
- HH:MM — event
- HH:MM — event
- ...

## Root cause(s)
<5 whys>

## What went well
- ...

## What went poorly
- ...

## Action items
| # | Action | Owner | Due | Status |

## Lessons learned
<bullet points to add to learning-log>
```

Blameless. Focus on systems, not people.

---

## 8. Drill schedule

- **Tabletop quarterly** — walk through a scenario (different one each quarter).
- **Chaos drill semi-annually** — actually trigger kill switch in staging mid-trade.
- **Pentest annually** — internal + external.
- **Backup restore drill quarterly** — verify RPO/RTO.
