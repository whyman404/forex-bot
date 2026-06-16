# Incident Response — Phase 2 Additions

> New scenarios for the Phase 2 surface. Read alongside `incident-response-playbook.md`.
> **Author:** Argus Hayato | **Date:** 2026-06-15
> **Cadence:** add playbook entry within 24h of any new Phase 2 incident type encountered.

---

## IR-P2-1. Stripe Chargeback Wave

**Sev:** SEV-2 (financial impact + reputation); SEV-1 if pattern indicates organized fraud or systemic issue.

**Detect:**
- Stripe dashboard alert: chargeback rate > threshold (Stripe escalates at 0.7%; 1% triggers risk programs).
- Webhook flood of `charge.dispute.created`.
- Spike in `customer.subscription.deleted` correlated with chargebacks.

**Contain (first 60 min):**
1. **Snapshot Stripe dashboard** + export disputes for forensics.
2. **Identify common dimension** across disputed charges:
   - Geography? Same IP block?
   - Sign-up cohort (recent vs old accounts)?
   - Payment method (BIN ranges, prepaid card pattern)?
   - Strategy or plan involved?
3. **Pause new signups from suspect cohort** (geo, BIN range) — temporary WAF rule.
4. **Downgrade affected users** immediately on chargeback (entitlement = false).
5. **Investigate refund-then-keep-using pattern** (AS-P2-9) — any users still active after refund? Audit `is_premium(user_id)` for each refunded user.

**Investigate:**
- Card testing attack (small charges then chargeback)?
- Stolen card usage (carders test on us)?
- Legitimate dissatisfaction (recent strategy failure caused user losses)?
- Refund abuse (use service, chargeback to claw back)?

**Eradicate:**
- If carders / fraud → add Stripe Radar custom rules; block BIN ranges; require Stripe Identity for higher-tier subscription.
- If product issue → fix the underlying complaint; reach out to affected users.
- If refund-then-keep pattern → patch the entitlement check that allowed continued use.

**Recover:**
- Reconcile entitlements with Stripe subscription state (run daily job manually).
- Engage Stripe risk team if rate stays high; they have specialists.
- Comm to users if any false-downgrades happened (apology + restore).

**Notify:**
- Stripe risk team (proactive — sooner is better).
- Internal stakeholders.

---

## IR-P2-2. mt5-bridge Compromised

**Sev:** SEV-1 always.

**Detect:**
- Alert: bridge token used from unexpected IP (not backend).
- Alert: HMAC nonce replay attempted.
- Alert: order placed with magic number not matching expected (user, strategy) hash.
- Alert: orders placed while backend says "no live signals sent."
- User reports trades they didn't authorize.
- Windows event log: unexpected process started under `mt5-bridge-svc`.
- Sysmon: unusual outbound network from bridge VPS.

**Contain (immediate, within minutes):**
1. **Rotate `BRIDGE_TOKEN` immediately** — old token now invalid; attacker locked out of API.
2. **Disconnect all users' live trading via backend kill-all-live endpoint** — engine stops sending signals.
3. **Issue MT5 broker-side `LogOut`** for every connected user (the `MetaTrader5` Python API has logout; force all sessions to end).
4. **Force-rotate every user's MT5 password** — communicate via separate channel (in-app + email): "We have reset your connection for security; please reconnect with a fresh MT5 password set with your broker."
5. **Network isolation**: pull bridge VPS off Tailnet (or disable Tunnel) until clean.
6. **Forensic snapshot** of bridge VPS: full disk image, memory dump if practical, all logs.

**Investigate:**
- How did attacker get token? RDP brute (event log)? Insider (HR)? Token in screenshot (Slack/email scan)?
- What did they do? List every order placed during compromise window; cross-reference with backend signal log; orphan orders = attacker.
- Did they exfil credentials? Decrypt-at-rest unlikely (KEK in memory only); but check process memory access logs.

**Eradicate:**
- Rebuild Windows VPS from clean image (don't trust the compromised host).
- Re-deploy bridge from signed artifact.
- New token, new MT5 install, new everything.
- Patch the entry vector (e.g., reset RDP creds, lock down further).

**Recover:**
- Comm to users (template in `incident-response-playbook.md`).
- Reconcile broker history with each user; compensate for harm caused by our breach (escalate to founders).
- File breach notification (PDPC, EU DPA) if user data affected — within 72h.

**Lessons:**
- Was Tailscale/Tunnel in place? If not, install.
- Was token rotation cadence shorter than incident? Improve.
- Was MT5 terminal correctly logged out? Improve.

---

## IR-P2-3. Live Engine Sending Bad Signals

**Sev:** SEV-1 (live financial impact).

**Detect:**
- Reconciliation job alert: broker vs our records diff.
- Alert: trade exec latency anomaly.
- User reports unexpected positions.
- Alert: orders placed outside expected market hours.
- Alert: lot sizes > expected per user.

**Contain (immediate):**
1. **Engine global kill** — pause all live strategies. (Engine config flag + Redis publish.)
2. **Bridge halt** — even if engine misbehaves, bridge refuses new orders (`/admin/halt`).
3. **Position assessment per user**: list open positions; decide hold vs close (default: hold if market open, close if abnormal).
4. **Communicate to users within 15 min** — status page + email: "Trading paused, no action needed, investigating."

**Investigate:**
- Recent strategy deploy? Recent params change? (audit log)
- Recent dependency upgrade?
- Bad market data feed? (broker data anomaly)
- Strategy bug (e.g., divide-by-zero, off-by-one)?
- Hostile (AS-P2-4)? Run integrity check on strategy bundle (cosign verify).
- Race condition / TOCTOU?

**Eradicate:**
- Revert to last known good strategy version.
- If params corruption suspected → restore params from last verified snapshot.
- Patch + redeploy through full review (CODEOWNERS + 2-approver).
- Canary in paper for N hours before resume live.

**Recover:**
- Per-user post-mortem on positions: close gracefully, hold to natural exit, or take immediate loss based on best for user.
- Compensation policy: founders' call; document.
- Public post-mortem within 5 business days.

**Lessons:**
- Was the canary period long enough?
- Was the test coverage sufficient?
- Did integrity check (cosign) catch the issue?

---

## IR-P2-4. Subscription Bypass Exploit

**Sev:** SEV-2 (financial leak); SEV-1 if also gives live trading access.

**Detect:**
- Audit anomaly: user has `is_premium=true` but no matching Stripe subscription.
- Reconciliation job (S7 in pre-launch checklist) finds orphan entitlement.
- User report (rare; users don't usually report having free premium).
- External vuln disclosure.

**Contain:**
1. **Identify mechanism**: webhook spoof? Race condition? Code bug? Insider DB update?
2. **Patch the vulnerability** before further entitlements granted.
3. **Reconcile**: every user without matching Stripe subscription → downgrade.
4. **Audit log review**: how many users affected? For how long?
5. **Decide**: silent fix (small impact) vs disclosure (large impact / user-trust angle).

**Investigate:**
- Was it webhook spoof? (AS-P2-1) → signature check working?
- Was it idempotency bypass? (replay) → idempotency table working?
- Was it client-controllable metadata? → tighten resolution to Stripe API source.
- Was it insider DB write? → audit log + actor identification.

**Eradicate:**
- Patch + redeploy.
- Add regression test.
- Add monitoring rule (e.g., orphan entitlements alert in <1h, not next-day).

**Recover:**
- Affected users (legitimate ones): treat fairly (offer free month or similar).
- Bad actors: revoke + ban + log.
- Notify Stripe risk if pattern matches abuse case they track.

**Lessons:**
- Could this be detected sooner? Improve alerting.
- Strengthen reconciliation cadence (every 1h vs nightly).

---

## IR-P2-5. Email Provider Compromise

**Sev:** SEV-1 (mass user impact possible).

**Detect:**
- Provider notifies us (best case).
- Anomaly: outbound email volume spike from our domain.
- DMARC `rua` reports show spike of fails not from our IPs.
- User reports receiving suspicious email purporting to be us.
- Security press / industry alert.

**Contain (within 30 min):**
1. **Rotate provider API token** immediately.
2. **Stop all outbound** via that provider — temporary pause.
3. **Audit recent send history** (last 30 days): list all emails sent + recipients + templates.
4. **Identify suspicious sends** that we did NOT initiate (compare to our app's send-log).
5. **Switch to backup provider** if we have one (Phase 3 recommendation; for Phase 2, accept degraded service during incident).
6. **In-app banner**: "We are investigating an email security incident. Do not click any password-reset email received in the last X hours; instead, request a new reset via the app." Notify via in-app (not email — provider compromised).

**Investigate:**
- What did attacker send? (provider audit log)
- What did attacker read? (if API has read scope — should NOT, per email-security.md)
- Are recipient lists exfiltrated? (PII breach — notify)
- How did they get the token?

**Eradicate:**
- New provider account (if needed) or repair existing.
- Rotate everything.
- Audit our internal access (who has provider creds; can list be smaller?).

**Recover:**
- User comm via in-app + status page; offer second-channel verification for high-value ops (until trust rebuilt).
- Force password reset for any user who clicked a suspicious link in our investigation window.
- DMARC/SPF check (had any forged-from-us mail been published? Hopefully `p=reject` blocked).
- File breach notification if PII reading happened (72h).

**Lessons:**
- Did we have IP allowlist on provider token? If not, add.
- Did the token have minimum scope?
- Was rotation cadence shorter than incident? Improve.
- Plan for backup provider (Phase 3).

---

## Common Patterns Across Phase 2 Incidents

- **Money + automation = SEV-1 by default.** Don't downgrade unless certain.
- **Trust no single signal** during detect/contain — confirm with two sources before public statement.
- **Pause first, investigate second.** Reversing wrong pause is cheap; recovering from bad trades is not.
- **User comm honesty**: brief, factual, action-oriented. No marketing language during incident.

---

## Sign-off

These playbooks added to the master `incident-response-playbook.md` (Phase 2 update). Run tabletop on each within Q3 2026.

Argus Hayato: ____________ Date: ____________
