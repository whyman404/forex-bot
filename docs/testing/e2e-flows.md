# E2E Flows — Playwright

**Owner:** Themis Saori
**Tool:** Playwright (chromium primary; webkit + firefox in nightly)
**Updated:** 2026-06-14

These are the **only** flows kept as E2E. Everything else is unit/integration. Each flow corresponds to a high-value user journey. If any flow fails in CI, the build cannot deploy.

---

## Conventions

- File pattern: `e2e/<flow>.spec.ts`
- Page Object Model under `e2e/pages/`
- Test data factory under `e2e/fixtures/`
- All waits are condition-based (`expect(locator).toBeVisible()`, `page.waitForURL`) — `page.waitForTimeout()` is **banned** (lint rule).
- Stripe in test mode with Stripe test cards (`4242…`, `4000000000000341` for fail).
- Email captured via Mailpit running in CI sidecar.
- Each test cleans up its own user (or runs against ephemeral DB via testcontainers).
- Tests must run in parallel; each owns its own email + workspace.

---

## Flow 1 — Signup → Email verification → Trial

`e2e/signup-and-trial.spec.ts`

```
Given a new visitor on /signup
When they submit valid email + strong password
Then a verification email lands in Mailpit
And clicking the link redirects to /dashboard
And the trial banner shows "14 days remaining"
And the user has tier = trial in DB
```

Edge cases (separate it() blocks):
- Weak password → form blocks (no submit).
- Existing email → friendly error, no PII leak.
- Verification link expired → resend works.
- Verification link reused → "already verified" friendly state.

---

## Flow 2 — Login → Connect broker (mock) → Strategy list

`e2e/login-and-connect-broker.spec.ts`

```
Given a verified user on /login
When credentials are correct
Then redirect to /dashboard

When they click "Connect Broker" → "Exness MT5"
And submit account + server + password (mocked broker)
Then the test-connection call returns success within 5s
And the broker_account row exists in DB encrypted (cred field starts with "enc:")
And the strategy list page shows 6 strategies + "ready to start"
```

Negative:
- Bad credentials → user-facing error, no stack trace shown, secret never echoed back.

---

## Flow 3 — Run backtest → See results

`e2e/run-backtest.spec.ts`

```
Given user on /strategies/london-breakout
When they pick range 2024-01-01..2024-12-31 + click "Run Backtest"
Then progress shows then completes within 30s (cached fixture)
And the report card shows PF, Sharpe, Max DD, slippage row, walk-forward fold table
And clicking "Show trades" reveals trade list with timestamps in UTC
```

Assert: report card **does not** show PF without slippage row (would imply dishonest report).

---

## Flow 4 — Subscribe via Stripe checkout → Unlock

`e2e/subscribe-stripe.spec.ts`

```
Given a trial user on /pricing
When they click "Upgrade to Pro" and complete Stripe checkout with 4242…
Then redirected back to /billing/success
And dashboard tier badge shows "Pro"
And user.tier = pro in DB
And a stripe_event row exists with type=checkout.session.completed
```

Negative + edge:
- Card declined (`4000000000000002`) → friendly error, tier unchanged.
- 3DS required (`4000000000003220`) → 3DS prompt, then success.
- Cancel checkout → returned to /pricing, tier unchanged.
- Replay the same webhook event ID → no duplicate side effects (idempotency).

---

## Flow 5 — Start strategy (paper) → See signal → Kill switch → Confirmed stopped

`e2e/start-paper-and-kill.spec.ts` — **highest-priority E2E. Block release on failure.**

```
Given Pro user with paper broker connected
When they start "Gold London Breakout" with paper amount 1000
Then strategy status shows "Running" within 3s

And a signal is injected via test hook (window.__testInjectSignal)
And a paper trade appears in the trade tape within 5s

When they click the prominent "Kill Switch" button
And confirm in the modal
Then strategy status shows "Stopped" within 2s
And no new orders are placed in the next 30s (poll trade tape)
And strategy_instance.status = stopped in DB
And strategy_instance.stopped_at is set
And an audit_log row records who clicked, when, from which IP
```

Plus a11y check on the kill switch modal: focus trap, ESC closes, button reachable by Tab, screen reader announces "Stop strategy. Press Enter to confirm".

---

## Flow 6 — 2FA enroll + verify

`e2e/2fa-enroll-and-verify.spec.ts`

```
Given Pro user on /settings/security
When they click "Enable 2FA"
Then a TOTP QR + secret is shown
And entering a valid TOTP (computed via otplib in test) completes enrollment
And 10 backup codes are shown once

When they log out and back in
Then they are prompted for TOTP
And valid TOTP unlocks; invalid blocks
And after 5 invalid attempts, account is locked for 15min
```

---

## Flow 7 — Password reset

`e2e/password-reset.spec.ts`

```
Given a registered user on /login
When they click "Forgot password" + submit email
Then a reset email lands in Mailpit within 5s

When they click the link
Then they reach /reset-password with token in URL
And submitting a new strong password succeeds
And they can log in with the new password
And the old password no longer works
And the reset link cannot be reused
```

---

## Flow 8 — Billing portal access

`e2e/billing-portal.spec.ts`

```
Given a Pro subscriber on /billing
When they click "Manage subscription"
Then they are redirected to Stripe Customer Portal
And the portal context is their customer id (not another user's)
```

IDOR check: if user A tries to call `/billing/portal?customer_id=<user B id>`, response is 403.

---

## CI orchestration

```yaml
e2e:
  needs: [backend-build, frontend-build]
  steps:
    - run: docker compose -f compose.ci.yml up -d  # backend + frontend + postgres + redis + mailpit + broker-mock
    - run: pnpm playwright install --with-deps
    - run: pnpm playwright test --reporter=html
    - if: failure()
      run: pnpm playwright show-report  # uploaded as artifact
```

- Retry: 1 retry on CI only (after a flake we open a bug, fix root cause; we do not raise retries to mask flake).
- Trace: full trace on failure attached as artifact.
- Video: on failure.
- Sharding: 4 shards in CI.

---

## Out of scope (intentionally not E2E)

- Admin panel CRUD → integration tests.
- Strategy parameter form edge cases → unit on the form component.
- Internationalization → snapshot tests.
- Mobile webview → manual smoke per release (Phase 3).
