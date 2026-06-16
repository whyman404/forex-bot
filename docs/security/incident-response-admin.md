# Incident Response — Admin Security

**Owner:** Argus Hayato (Security on-call)
**Last updated:** 2026-06-16
**Severity scale:** SEV-1 (critical, immediate) → SEV-4 (low)

> Containment first, eradication second, recovery third. Forensics throughout. Never delete evidence.

---

## Scenario 1 — Admin Account Compromised (SEV-1)

### Indicators
- Login from unusual country / new device
- Failed step-up TOTP attempts on admin account
- Audit log shows actions admin denies performing
- Sudden mass broadcast / kill switch toggle from one admin
- Admin reports password / TOTP secret leaked
- Email account of admin compromised (recovery path)

### Containment (within 5min)
1. **Lock the admin account immediately**
   - `UPDATE users SET is_active=false, force_password_change=true WHERE id=<admin_id>`
   - Revoke all JWT sessions via JTI denylist
   - Disable TOTP secret (force re-enroll)
2. **Revoke admin role temporarily** (`role: 'user'`) — even if account is locked, defense in depth
3. **Kill switch consideration**: if compromise suspected to be active during trading hours → engage kill switch (with co-approval if another admin available)
4. **Add admin IP to bot mode at Cloudflare** for the suspected attacker IP
5. **Snapshot DB** for forensics (RDS snapshot, S3 audit_log copy)

### Investigation (within 1h)
- Query `audit_log WHERE actor_id=<admin> AND ts > now() - 24h`
- Map every action performed; classify legit vs suspicious
- Cross-reference IP + UA from sessions
- Check Redis for active sessions
- Check email logs for delivery to attacker addresses
- Check broker / external API logs for outbound actions
- Pull CDN logs for full request history
- Forensic image of admin's workstation (if available)

### Eradication
- Reset admin's password (via separate admin)
- Re-enroll TOTP (new secret + new backup codes)
- Rotate `JWT_SECRET` if multi-admin compromise suspected (invalidates ALL sessions)
- Rotate `KEK` if broker credential decryption suspected (re-encrypt all wrapped DEKs)
- Patch attack vector (XSS, dependency, etc.)

### Recovery
- Restore admin access ONLY after:
  - Password rotated, TOTP re-enrolled
  - Workstation cleaned / replaced
  - Post-incident review approves return
- Notify users impacted (impersonation log shows who was accessed):
  - "Your account was reviewed by an admin between X and Y. We have completed an internal security review. No further action required from you." (don't reveal compromise scope publicly until investigation done)
- Send dashboard notice + email to user base if mass broadcast / kill switch involved

### Post-Incident
- Root cause analysis (RCA) within 7 days
- Update detection rules
- Tabletop exercise repeated within 30 days
- Disclosure if PII/regulatory triggered (GDPR/PDPA 72h)

---

## Scenario 2 — Insider Threat (Admin Acts Maliciously) (SEV-1/2)

### Indicators
- Admin reads audit log of unrelated user repeatedly
- Admin exports user list outside normal hours
- Admin impersonates users with no ticket reason
- Admin disables monitoring or attempts to delete audit_log
- Multiple step-up TOTP requests on sensitive actions
- Admin attempts self-grant via approval bypass

### Containment
1. Second admin (or security lead) reviews suspect admin's activity
2. If credible → revoke admin role pending review (not lock account — preserve forensics)
3. Multi-admin approval to demote (n=2)
4. Add suspect admin to "elevated monitoring" — 100% audit, all actions reviewed

### Investigation
- Pull all `audit_log` rows for suspect's actor_id last 90 days
- Statistical anomaly review: action frequency vs other admins
- HR partnership (legal hold on workstation, email, chat)
- Comparative analysis: did suspect's actions correlate with external events (e.g. customer complaints, financial losses)

### Mitigation Going Forward
- Immutable audit log (hash-chain + S3 Object Lock) — already in §3.4 of admin-security.md
- Dual-control on critical (n-of-m) — already enforced
- SOC review of admin actions weekly
- Quarterly admin access review — remove dormant
- Legal: NDA + acceptable use policy signed at onboarding

---

## Scenario 3 — Mass User Lockout (SEV-1)

### Indicators
- Spike in support tickets "I can't log in"
- Mass `users.is_active=false` change in audit log
- Bulk password reset event in audit log
- Spike in failed login attempts (because passwords forcibly reset)

### Containment (within 10min)
1. Identify scope: which users, by which admin, what action
2. Halt further changes:
   - Disable bulk endpoints temporarily
   - Lock suspect admin (see Scenario 1)
3. Status page update: "investigating login issues"

### Recovery
1. **Rollback strategy** depends on action:
   - If `is_active` flipped: SQL replay from audit_log `before_state` → restore
   - If password reset: invalidate all forced-reset tokens, send new password reset emails (legitimate flow)
   - If TOTP wiped: users re-enroll via support ticket with ID verification
2. Restore from DB snapshot if audit-log replay insufficient (PITR available)
3. Comms: email all affected users with reassurance + new login link

### Post-Incident
- Add rate limit on bulk admin actions (already specified in admin-security.md)
- Bulk action > N users now requires multi-admin approval
- Add canary user account that, when affected, alerts SOC

---

## Scenario 4 — Audit Log Tampering Attempt (SEV-1)

### Indicators
- Hash-chain integrity check fails (nightly job alerts)
- INSERT failures on audit_log table
- Unexpected DB role / permission changes

### Containment
1. Halt all admin endpoints (graceful 503) until investigation
2. Compare last known good hash with current — find tampering window
3. Snapshot DB

### Investigation
- Postgres logs (pg_audit) for queries on audit_log
- DB role audit: who has UPDATE/DELETE on the table (should be NONE app-side)
- Restore from S3 backup with Object Lock — compare diff

### Recovery
- Restore audit_log to verified state from immutable backup
- Re-enable admin endpoints only after investigation

---

## Scenario 5 — Step-Up TOTP Service Outage (SEV-2)

### Indicators
- Redis down or unreachable
- Mass `stepup_failed` errors despite valid codes
- Admins report TOTP rejected

### Containment
- All destructive admin ops auto-block (fail-closed by design) — this is correct
- Admins continue with non-destructive (read, support response)

### Recovery
- Restore Redis (cluster failover, restart)
- DO NOT bypass TOTP — if needed urgently, single-admin breakglass with another's approval ON-CALL (out-of-band confirmation)
- Audit any actions taken during outage

---

## Scenario 6 — Mass Broadcast Misuse (SEV-1)

### Indicators
- Broadcast template overridden in audit
- Recipient list larger than usual
- Outbound links not in allowlist
- Spike in user reports "phishing email from you"

### Containment
1. Halt email provider sending API token (rotate immediately at provider)
2. Pull broadcast content from audit
3. Public statement on status page + dashboard within 30min

### Mitigation
- DMARC reports — track spoof attempts
- User comms via separate channel (in-app banner) clarifying official email signature
- For users who clicked malicious link: force password reset + TOTP re-enroll + broker credential rotation

---

## Common Forensics Checklist

- [ ] Snapshot DB (PITR token, S3 audit backup)
- [ ] Redis dump (sessions, step-up state)
- [ ] CDN access logs (timestamp window ± 24h)
- [ ] Email provider logs (sent + delivered + clicked)
- [ ] Workstation image (if endpoint involved)
- [ ] All audit_log rows for suspect actor_id last 90 days
- [ ] Slack/PagerDuty alert history
- [ ] Multi-admin approval queue snapshots

---

## Communications Templates

### Internal (Slack #incidents)
```
SEV-1: Admin account suspected compromise
Detected: <time>
Indicators: <bullets>
Action so far: <bullets>
On-call: @argus
Bridge: <link>
```

### External (status page)
```
We are investigating an issue affecting login. We will share updates every 30min.
```

### User notification (if PII or financial impact)
```
On <date>, we detected unusual activity on a small number of accounts.
We have completed a security review and applied additional protections.
If you notice unfamiliar activity on your account, please contact support.
We are committed to transparency and will share a full post-mortem.
```

---

## On-Call Roster (placeholder)

| Role | Primary | Backup |
|---|---|---|
| Security lead | Argus (whyman404@) | TBD |
| Engineering lead | TBD | TBD |
| Comms | TBD | TBD |

Page via PagerDuty `forex-bot-sev1` schedule.

---

## References
- `/docs/security/admin-security.md`
- `/docs/security/threat-model-admin.md`
- `/docs/security/incident-response-playbook.md` (general)
