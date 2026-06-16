# Stripe PCI DSS Scope Analysis

> What PCI obligations we have. Spoiler: the lowest tier — by design.
> **Author:** Argus Hayato | **Date:** 2026-06-15
> **PCI DSS version:** v4.0 (effective)
> **Self-Assessment Questionnaire (SAQ):** target is **SAQ A**.

---

## 1. PCI Scope Position — Summary

We **never receive, process, store, or transmit** cardholder data (PAN, CVV, magstripe, full track).

**Integration model:** Stripe Checkout (Stripe-hosted page) — redirect or embedded iframe served entirely by Stripe.

**What we receive:**
- Webhook events (`event.id`, `customer.id`, `subscription.id`, `invoice.id`, prices, status, metadata we set).
- Customer ID for API calls.
- **NO PAN. NO CVV. NO expiry. NO card BIN.** (Stripe may surface `last4` + `brand` in API responses — these are NOT PCI-sensitive when handled this way.)

**Therefore:** PCI scope is **SAQ A** — the lowest applicable SAQ for merchants that outsource all card processing to a PCI DSS-validated third party and only handle data the third party explicitly says is out of scope.

---

## 2. Why Not SAQ A-EP?

**SAQ A-EP** applies to merchants who use a JavaScript embed/redirect that affects the security of cardholder data on the merchant page (e.g., Stripe Elements where merchant page hosts iframe but loads Stripe JS).

| Approach | SAQ | Our choice |
|---|---|---|
| Redirect to Stripe Checkout (hosted) | **SAQ A** | YES |
| Embedded Checkout (iframe, Stripe-hosted) | SAQ A | acceptable |
| Stripe Elements (Stripe JS on our page) | SAQ A-EP | NO (extra scope) |
| Custom card form sending to Stripe API | SAQ D (full) | NEVER |

**Decision:** use Stripe Checkout (redirect) for Phase 2. If we want a more "embedded" feel later, we use **Embedded Checkout** which preserves SAQ A.

**Rationale:** SAQ A reduces our PCI workload from ~329 requirements (SAQ D) to ~22 light requirements (SAQ A). It's the right move for a small team without dedicated PCI compliance staff.

---

## 3. SAQ A Requirements (v4.0) — Mapped to Our System

These are the requirements we must demonstrate. Most are met by our normal hygiene.

| # | Requirement | How we meet it |
|---|---|---|
| 2.2.7 | Default vendor credentials removed | OS + DB + Redis hardened; no default creds. |
| 6.4.3 | Manage scripts on payment page | Payment "page" is Stripe-hosted — N/A. Our checkout button is a redirect; no payment JS on our origin. |
| 8.2.1 | Strong authentication on systems touching cardholder env | We have no CHE — but we still use Argon2id + 2FA on user accounts. |
| 8.2.2 | Group/shared accounts forbidden | No shared accounts; per-user. |
| 8.2.4 | MFA on all non-console admin | Yes — TOTP + step-up for sensitive ops. |
| 8.3.1 | Strong cryptography for transmission | TLS 1.3 only. |
| 9.5.1 | Protect against skimming | N/A — no payment terminals. |
| 11.6.1 | Detect changes on payment pages | Detect changes on Stripe Checkout — Stripe's responsibility. We monitor only that our redirect-to-checkout URL is correct (CSP `connect-src` allowlist, Cypress smoke test). |
| 12.x | Information security policy | We maintain `secure-defaults.md`, `incident-response-playbook.md`. |
| 12.8.x | Service provider management | DPA with Stripe + annual review. Track Stripe's PCI compliance status. |

**Documentation requirement:** complete annual SAQ A and Attestation of Compliance (AOC) — Stripe provides templates.

---

## 4. Concrete Engineering Rules (Enforcement)

These rules KEEP us in SAQ A. Violating any of them upgrades our scope to SAQ A-EP or SAQ D.

### 4.1 What we MUST NOT do

| Rule | If violated → |
|---|---|
| Don't accept card data in any of our forms | SAQ D |
| Don't proxy card data through our backend (even briefly) | SAQ D |
| Don't load Stripe.js to collect card on our origin (Stripe Elements) | SAQ A-EP |
| Don't log webhook payloads that contain `last4` indefinitely | Slight scope impact (not PCI but PII discipline) |
| Don't store `last4` / `brand` outside Stripe Customer record cached for billing display only | low scope impact, but minimize |
| Don't accept card via phone / chat / email | SAQ C-VT or D |
| Don't allow admin to view full PAN via Stripe dashboard absent business need | Stripe-side control, but ensure team has minimum role |

### 4.2 What we MUST do

- **CSP** `connect-src` includes `https://api.stripe.com` and `https://checkout.stripe.com` only as needed; **NO** wildcards.
- **Webhook handler** verifies signature + idempotency (see `threat-model-phase2.md` AS-P2-1).
- **Stripe API key** is a **restricted key** with the minimum necessary scopes:
  - Read: Customer, Subscription, Invoice, PaymentIntent.
  - Write: Customer (create/update), Subscription (create/update/cancel), Checkout Session (create).
  - **NOT GRANTED:** refund, transfer, payout, balance read.
  - Refunds done from Stripe dashboard manually by founder with audit log.
- **Webhook secret** distinct from API key.
- **No raw card data anywhere** — verify via repo grep on terms: `card_number`, `cardNumber`, `pan`, `cvv`, `cvc`, `exp_month`, `exp_year` (when used as input form names) — these MUST NOT appear in any form/POST handler.
- **Annual SAQ A** completion — Argus + Zeus.

### 4.3 Customer-facing pages

- Pricing page → button → `POST /api/v1/billing/checkout-session` → backend creates Stripe Checkout Session via Stripe API → return `url` → frontend `window.location = url`.
- After payment → Stripe redirects to `<our-domain>/billing/success?session_id={CHECKOUT_SESSION_ID}` → backend confirms session via Stripe API + provisions (webhook-driven primarily; success page is UX only).
- After cancel → `<our-domain>/billing/cancel` → no state change.

### 4.4 Customer Portal

- Use **Stripe Billing Customer Portal** (Stripe-hosted) for: update card, cancel subscription, download invoice. Keeps card management out of our scope.
- `POST /api/v1/billing/portal-session` → backend creates portal session → frontend redirects.

---

## 5. Compliance Evidence Artifacts

To carry forward as audit evidence:

1. **This document** (`stripe-pci-scope.md`) — declares scope and rationale.
2. **Stripe AOC** (download annually from Stripe Dashboard).
3. **Stripe DPA** (signed, on file).
4. **Architecture diagram** showing card data flowing user → Stripe (NOT through us).
5. **Repo grep evidence**: CI job verifies no card-input field names exist anywhere in `frontend/`.
6. **CSP screenshot** — proves no card-collecting JS loaded on our origin.
7. **Annual SAQ A** completion + AOC.

---

## 6. What Happens If We Outgrow SAQ A

Triggers that would move us out of SAQ A:

- Adding **Stripe Elements** (card form on our page) → SAQ A-EP. Decision must be reviewed.
- Adding **phone payments** (taking card over voice) → SAQ C-VT.
- Storing card data ourselves → SAQ D. **DON'T.**
- Accepting tokenized cards from another processor and routing → varies.

Before any of these changes, run a scope review with Argus + Zeus + legal.

---

## 7. PSD2 / SCA Note (EU)

If we sell to EU users, Strong Customer Authentication (SCA) applies. Stripe Checkout handles this natively (3DS2 challenge). We must:
- Use Stripe Checkout (we already are).
- Pass enough customer info that SCA can be routed correctly.
- Surface friction to users in UX (e.g., subscription renewals may sometimes need re-auth — Stripe handles this).

---

## 8. Sign-off

- [ ] Stripe Checkout integration uses redirect / embedded (NOT Elements).
- [ ] No card input fields anywhere in our codebase (grep verified in CI).
- [ ] Webhook handler signature + idempotency tested.
- [ ] Restricted API key in use; refund scope NOT granted.
- [ ] DPA signed and on file.
- [ ] Annual SAQ A scheduled.

Argus Hayato: ____________ Date: ____________
Zeus Ryujin: _____________ Date: ____________
