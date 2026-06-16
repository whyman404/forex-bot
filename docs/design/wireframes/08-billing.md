# Wireframe 08 — Billing
**Author:** Iris Kaguya
**Date:** 2026-06-14
**Fidelity:** Mid-fi ASCII

---

## Desktop — Current Plan (Pro Monthly)

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Header with Emergency Stop]                                        │
└─────────────────────────────────────────────────────────────────────┘
┌──────┐  ┌─────────────────────────────────────────────────────────┐
│ NAV  │  │ Billing                                                  │
│      │  │                                                          │
│      │  │  ┌──────────────────────────────────────────────────┐   │
│      │  │  │ CURRENT PLAN                                      │   │
│      │  │  │                                                   │   │
│      │  │  │ Pro Monthly                          ✓ Active     │   │
│      │  │  │ $XX.XX / month                                    │   │
│      │  │  │                                                   │   │
│      │  │  │ Renews: July 14, 2026                             │   │
│      │  │  │ Payment: Visa ending 4242                         │   │
│      │  │  │                                                   │   │
│      │  │  │ [Upgrade to Lifetime]  [Update Payment Method]    │   │
│      │  │  │ [Cancel Subscription]  (link, lower emphasis)     │   │
│      │  │  └──────────────────────────────────────────────────┘   │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  PLAN USAGE                                              │
│      │  │                                                          │
│      │  │  ┌──────────────────────────────────────────────────┐   │
│      │  │  │ Strategies       6 / 6 available (all unlocked)  │   │
│      │  │  │ Live strategies  2 of 6 running                  │   │
│      │  │  │ Backtest runs    14 this month                   │   │
│      │  │  │ API access       Included                        │   │
│      │  │  └──────────────────────────────────────────────────┘   │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  UPGRADE TO LIFETIME                                     │
│      │  │                                                          │
│      │  │  ┌──────────────────────────────────────────────────┐   │
│      │  │  │ Lifetime access — one payment, no monthly fee    │   │
│      │  │  │                                                   │   │
│      │  │  │ Everything in Pro, plus:                          │   │
│      │  │  │ · API key management (scoped access)             │   │
│      │  │  │ · CSV/JSON export for all trade history          │   │
│      │  │  │ · Priority support                               │   │
│      │  │  │ · All future strategy updates                    │   │
│      │  │  │                                                   │   │
│      │  │  │ $XXX.XX — one time, no auto-renewal              │   │
│      │  │  │                                                   │   │
│      │  │  │ [Upgrade to Lifetime  →]                         │   │
│      │  │  └──────────────────────────────────────────────────┘   │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  INVOICE HISTORY                                         │
│      │  │                                                          │
│      │  │  Date           Description            Amount   Status  │
│      │  │  Jun 14, 2026   Pro Monthly             $XX.XX  ✓ Paid  │
│      │  │  May 14, 2026   Pro Monthly             $XX.XX  ✓ Paid  │
│      │  │  Apr 14, 2026   Pro Monthly             $XX.XX  ✓ Paid  │
│      │  │                                                          │
│      │  │  [Jun 14 receipt PDF ↓]                                 │
│      │  │  [May 14 receipt PDF ↓]                                 │
│      │  │  [Apr 14 receipt PDF ↓]                                 │
│      │  │                                                          │
│      │  │  [Load all invoices]                                     │
└──────┘  └─────────────────────────────────────────────────────────┘
```

---

## Plan Comparison — Upgrade Flow

```
┌──────────────────────────────────────────────────────────────────┐
│ Choose Your Plan                                                 │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ FREE TRIAL   │  │   PRO        │  │  LIFETIME    │          │
│  │              │  │  MONTHLY     │  │              │          │
│  │ 14 days      │  │  [POPULAR]   │  │  Best value  │          │
│  │              │  │              │  │              │          │
│  │ Free         │  │ $XX/month    │  │ $XXX once    │          │
│  │              │  │              │  │              │          │
│  │ ✓ 1 strategy │  │ ✓ 6 strat.  │  │ ✓ 6 strat.  │          │
│  │ ✓ Paper only │  │ ✓ Live + pp  │  │ ✓ Live + pp  │          │
│  │ ✗ Live trade │  │ ✓ Backtest   │  │ ✓ Backtest   │          │
│  │ ✗ Backtest   │  │ ✗ API access │  │ ✓ API access │          │
│  │ ✗ API        │  │ ✗ Export     │  │ ✓ Export     │          │
│  │              │  │ ✓ Cancel any │  │ No monthly   │          │
│  │              │  │   time       │  │ fee ever     │          │
│  │ Current plan │  │              │  │              │          │
│  │              │  │ [Choose Pro] │  │ [Choose LT]  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│ All plans: Stripe-secured payments.                              │
│ Pro: Cancel anytime before renewal to stop future charges.       │
│ Lifetime: Single charge. No auto-renewal. No hidden fees.        │
└──────────────────────────────────────────────────────────────────┘
```

---

## Free Trial State

```
┌───────────────────────────────────────────────────────────────┐
│ CURRENT PLAN                                                  │
│                                                               │
│ Free Trial                                    ⏱ Active       │
│ 0 days — 14 days remaining                                    │
│                                                               │
│ [████████████████████░░░░░░░░░░░] 71% used                  │
│                                                               │
│ Trial ends: June 28, 2026                                     │
│                                                               │
│ [  Upgrade to Pro — Keep Access  ]                            │
│ [  Upgrade to Lifetime           ]                            │
│                                                               │
│ Trial limitations:                                            │
│ · 1 strategy (EMA + ADX only)                                 │
│ · Paper trading only — no live orders                         │
│ · No backtest access                                          │
│ · No API access                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## Cancel Subscription Modal

```
┌──────────────────────────────────────────────┐
│ Cancel Pro Monthly Subscription?             │
│                                              │
│ Your access continues until July 14, 2026.  │
│ After that, all live trading will stop and  │
│ you will revert to Free Trial limits.        │
│                                              │
│ You can resubscribe at any time.             │
│                                              │
│ [  Keep My Subscription  ]  ← primary       │
│ [  Yes, Cancel           ]  ← danger/link   │
└──────────────────────────────────────────────┘
```

---

## Design notes

- "Cancel Subscription" is a text link, not a button — lower visual weight discourages accidental cancel
- Cancel modal default action is "Keep" — safe default for irreversible action
- Lifetime plan: "one payment, no auto-renewal" copy repeated 3 times across page — critical for trust (P3 Krit)
- Invoice PDFs: Stripe-hosted receipt links — no custom PDF generation needed
- Usage metrics (strategies used, backtest runs) help user feel value — supports retention
- Payment method update goes to Stripe's hosted form — no card data touches our servers
- Thai baht pricing via Omise fallback: show local currency if user billing address is Thailand
