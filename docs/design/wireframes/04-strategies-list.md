# Wireframe 04 — Strategies List
**Author:** Iris Kaguya
**Date:** 2026-06-14
**Fidelity:** Mid-fi ASCII

---

## Desktop (1280px)

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Header with Emergency Stop]                                        │
└─────────────────────────────────────────────────────────────────────┘
┌──────┐  ┌─────────────────────────────────────────────────────────┐
│ NAV  │  │ Strategies                                               │
│      │  │                                                          │
│      │  │ Filter: [All ▾] [Status: All ▾] [Symbol: All ▾]        │
│      │  │                                                          │
│      │  │  6 strategies  |  2 LIVE  |  0 PAPER  |  4 OFF          │
│      │  │                                                          │
│      │  │  ┌───────────────────────────────────────────────────┐  │
│      │  │  │ 1. LONDON BREAKOUT                    ● LIVE      │  │
│      │  │  │ Symbol: XAUUSD  |  Timeframe: M15                 │  │
│      │  │  │                                                    │  │
│      │  │  │ ┌─────────────────────────────┐  ┌─────────────┐  │  │
│      │  │  │ │ Mini Equity Curve (30d)     │  │ TODAY P&L   │  │  │
│      │  │  │ │    ╱╲     ╱                 │  │ ▲ +$82.30   │  │  │
│      │  │  │ │___╱  ╲___╱                 │  │ +0.80%      │  │  │
│      │  │  │ └─────────────────────────────┘  │             │  │  │
│      │  │  │                                   │ Total P&L   │  │  │
│      │  │  │ Win Rate: 42%  PF: 1.72  DD: 11% │ ▲ +$412.50  │  │  │
│      │  │  │                                   └─────────────┘  │  │
│      │  │  │                              [View Detail]          │  │
│      │  │  └───────────────────────────────────────────────────┘  │
│      │  │                                                          │
│      │  │  ┌───────────────────────────────────────────────────┐  │
│      │  │  │ 2. NY KILLZONE                         ● LIVE     │  │
│      │  │  │ Symbol: XAUUSD  |  Timeframe: H1                  │  │
│      │  │  │                                                    │  │
│      │  │  │ ┌─────────────────────────────┐  ┌─────────────┐  │  │
│      │  │  │ │ Mini Equity Curve (30d)     │  │ TODAY P&L   │  │  │
│      │  │  │ │     ╱╲___╱╲___╱            │  │ ▲ +$60.20   │  │  │
│      │  │  │ │____╱                       │  │ +0.60%      │  │  │
│      │  │  │ └─────────────────────────────┘  │             │  │  │
│      │  │  │                                   │ Total P&L   │  │  │
│      │  │  │ Win Rate: 38%  PF: 1.65  DD: 13% │ ▲ +$298.00  │  │  │
│      │  │  │                                   └─────────────┘  │  │
│      │  │  │                              [View Detail]          │  │
│      │  │  └───────────────────────────────────────────────────┘  │
│      │  │                                                          │
│      │  │  ┌───────────────────────────────────────────────────┐  │
│      │  │  │ 3. EMA + ADX TREND                    ○ OFF       │  │
│      │  │  │ Symbol: XAUUSD  |  Timeframe: H4                  │  │
│      │  │  │                                                    │  │
│      │  │  │ ┌─────────────────────────────┐  ┌─────────────┐  │  │
│      │  │  │ │ Mini Equity Curve (30d)     │  │ TODAY P&L   │  │  │
│      │  │  │ │  (no live data — strategy   │  │ —           │  │  │
│      │  │  │ │   not active. Backtest      │  │ Not running  │  │  │
│      │  │  │ │   preview shown in gray)    │  │             │  │  │
│      │  │  │ └─────────────────────────────┘  │ All-time PF │  │  │
│      │  │  │                                   │ 1.85        │  │  │
│      │  │  │ Win Rate: 51%  PF: 1.85  DD: 9%  └─────────────┘  │  │
│      │  │  │                              [View Detail]          │  │
│      │  │  └───────────────────────────────────────────────────┘  │
│      │  │                                                          │
│      │  │  ┌───────────────────────────────────────────────────┐  │
│      │  │  │ 4. SMART MONEY CONCEPTS                ◑ PAPER    │  │
│      │  │  │ Symbol: BTCUSD  |  Timeframe: H4                  │  │
│      │  │  │                                                    │  │
│      │  │  │ ┌─────────────────────────────┐  ┌─────────────┐  │  │
│      │  │  │ │ Paper equity curve          │  │ TODAY       │  │  │
│      │  │  │ │   ╱╲  ╱╲__╱╲              │  │ PAPER: +$45  │  │  │
│      │  │  │ │__╱  ╲╱                    │  │ (simulated) │  │  │
│      │  │  │ └─────────────────────────────┘  └─────────────┘  │  │
│      │  │  │                                                    │  │
│      │  │  │ Win Rate: 44%  PF: 1.58  DD: 16%  [View Detail]   │  │
│      │  │  └───────────────────────────────────────────────────┘  │
│      │  │                                                          │
│      │  │  [Strategy 5 — OFF]  [Strategy 6 — OFF]  (collapsed)   │
└──────┘  └─────────────────────────────────────────────────────────┘
```

---

## Strategy Card Status Legend

```
Status indicators:
● LIVE  (filled circle, green)  — Bot placing real trades
◑ PAPER (half circle, amber)    — Bot running, no real orders
○ OFF   (empty circle, gray)    — Strategy inactive

Note: Status uses shape + color + text label — never color alone.
```

---

## Strategy Card — Expanded States

```
LIVE STRATEGY with open trade:
┌───────────────────────────────────────────────────────────────┐
│ 1. LONDON BREAKOUT                              ● LIVE        │
│ Symbol: XAUUSD  |  Timeframe: M15  |  1 open trade           │
│                                                               │
│ ┌─────────────────────────────┐  ┌──────────────────────┐   │
│ │ Mini Equity (30d)           │  │ TODAY P&L             │   │
│ │    ╱╲     ╱                 │  │ ▲ +$82.30  +0.80%    │   │
│ │___╱  ╲___╱                 │  │                       │   │
│ └─────────────────────────────┘  │ Open: XAUUSD BUY     │   │
│                                   │ Entry: 2341.5         │   │
│ Win Rate: 42%  PF: 1.72  DD: 11% │ Unrealized: ▲+$14.2  │   │
│                                   └──────────────────────┘   │
│                                               [View Detail]  │
└───────────────────────────────────────────────────────────────┘

OFF STRATEGY (no trades):
┌───────────────────────────────────────────────────────────────┐
│ 3. EMA + ADX TREND                              ○ OFF         │
│ Symbol: XAUUSD  |  Timeframe: H4                             │
│                                                               │
│ ┌─────────────────────────────────────────────────────────┐  │
│ │ This strategy is not running. View backtest results     │  │
│ │ or activate to paper/live trade.                        │  │
│ │                                                         │  │
│ │ Backtest (Jan–May 2025):  PF: 1.85 | DD: 9%            │  │
│ │ [Activate → Paper]  [Activate → Live]  [View Detail]   │  │
│ └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

---

## Mobile (375px) — Card layout

```
┌─────────────────────────────┐
│ Strategies                  │
│ [All ▾] [Status ▾]          │
│ 2 LIVE  0 PAPER  4 OFF      │
│                              │
│ ┌───────────────────────┐   │
│ │ London Breakout ●LIVE │   │
│ │ XAUUSD  M15           │   │
│ │ ─────────────────╱─── │   │
│ │ ▲ Today: +$82.30      │   │
│ │ PF: 1.72  DD: 11%     │   │
│ │           [Detail  →] │   │
│ └───────────────────────┘   │
│                              │
│ ┌───────────────────────┐   │
│ │ NY Killzone    ●LIVE  │   │
│ │ XAUUSD  H1            │   │
│ │ ────────────╱╲──╱──── │   │
│ │ ▲ Today: +$60.20      │   │
│ │ PF: 1.65  DD: 13%     │   │
│ │           [Detail  →] │   │
│ └───────────────────────┘   │
└─────────────────────────────┘
```

---

## Design notes

- Status indicator uses shape + color + text — colorblind and screen reader safe
- P&L uses arrow + sign + color — never color alone
- OFF strategies show backtest preview numbers so users (P2, P3) can evaluate before activating
- PAPER mode clearly labeled "simulated" — never confuse paper P&L with real money
- Metrics (Win Rate, PF, DD) shown on card — P2 Priya reads these before anything else
- Empty state (trial user, no strategies unlocked): show "Upgrade to access all 6 strategies" CTA
- Sort: by status (LIVE first) by default, sortable by today P&L, total P&L
