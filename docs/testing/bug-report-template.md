# Bug Report Template

> Goal: developer reads once → can reproduce and fix. No second message needed.

Copy this template into a GitHub Issue, fill every field, attach evidence.

---

## Title

`[area] short imperative summary` — e.g. `[trading-engine] London Breakout signals on flat day after DST boundary`

---

## Severity & Priority

- **Severity:** P0 (catastrophic, data loss / money loss / security) / P1 (major, no workaround) / P2 (major, workaround exists) / P3 (minor)
- **Priority:** same scale (severity ≠ priority — explain if different)
- **Component / Area:** trading-engine | backend | frontend | billing | infra | security | a11y | perf

## Environment

- **Build / version / commit SHA:**
- **Environment:** dev | staging | paper-prod | prod
- **Browser / OS / device** (if frontend):
- **Broker** (if trading): MT5 mock / Exness demo / Exness live / Binance testnet / Binance live
- **Stripe mode:** test / live
- **User role / tier:**
- **Time of occurrence (UTC):**

## Steps to Reproduce

Numbered, atomic, copy-pastable. Include exact inputs.

1. …
2. …
3. …

If automatable, include the test case path or curl/k6 command.

## Expected

What should happen, per spec / acceptance criteria / common sense.

## Actual

What happened. Quote exact error message. Paste relevant log lines (with timestamps).

## Evidence

- [ ] Screenshot or short screen recording (mp4 / gif < 30 MB)
- [ ] Server log excerpt with request id
- [ ] Network HAR for frontend bugs
- [ ] Stack trace
- [ ] DB row snapshot (anonymized) if state-related
- [ ] Sentry / Loki link

## Impact

- Who is affected (% of users / specific tier / specific flow)
- Frequency (always / sometimes / rare / once)
- Workaround (if any)
- Money / safety impact (if any) — e.g. "could cause user to over-leverage"

## Hypothesis (optional)

If you have a root-cause guess, write it. Tag the suspected file.

## Related

- Linked issues / PRs
- Linked test case ID
- Linked design / spec

## Acceptance for fix

How we know it's fixed — usually a specific automated test added.

---

### Example (filled)

```
Title: [billing] Replayed Stripe webhook double-applies tier upgrade

Severity: P0  Priority: P0  Area: billing
Env: staging, commit a3f9bcd, Stripe test mode

Steps:
1. POST /webhooks/stripe with event_id evt_test_001 (checkout.session.completed payload attached)
2. POST same body 10s later
Expected:
- 1st call: user.tier→pro, stripe_event row inserted
- 2nd call: 200 acknowledged, NO additional side effect
Actual:
- 2nd call: user.tier set again, second stripe_event row inserted, 2x audit_log
Evidence:
- log.txt (attached)
- db_snapshot.json (attached, 2 rows for same event_id)
Impact: any retried Stripe webhook could cause duplicate writes; minor for tier, severe if used for refunds
Hypothesis: missing unique constraint on stripe_event.event_id + missing pre-check
Acceptance: add UNIQUE(event_id), 409 conflict path, new test in test_billing_webhook.py WB-03
```
