# Wireframe 03 — Dashboard (Main Overview)
**Author:** Iris Kaguya
**Date:** 2026-06-14
**Fidelity:** Mid-fi ASCII

---

## Desktop (1280px)

```
┌─────────────────────────────────────────────────────────────────────┐
│ HEADER (sticky, 64px)                                               │
│ [Logo]  Dashboard  Strategies  Backtest  Billing  Settings          │
│                                          [Notifications] [Avatar ▾] │
│                                  [! STOP ALL TRADING] ← always here │
└─────────────────────────────────────────────────────────────────────┘

┌──────┐  ┌─────────────────────────────────────────────────────────┐
│ NAV  │  │ MAIN CONTENT                                             │
│ (SB) │  │                                                          │
│      │  │  Dashboard                  [Last updated: 14:32:01 +07]│
│ [=]  │  │                                                          │
│ Dash │  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│      │  │  │ ACCOUNT BAL. │ │ TODAY P&L    │ │ OPEN TRADES  │   │
│ [▦]  │  │  │              │ │              │ │              │   │
│ Str. │  │  │ $10,245.30   │ │ ▲ +$142.50  │ │ 3 trades     │   │
│      │  │  │ Exness MT5   │ │ +1.42%      │ │ 2 buy 1 sell │   │
│ [⟳]  │  │  │ #12345678    │ │             │ │              │   │
│ Back │  │  └──────────────┘ └──────────────┘ └──────────────┘   │
│      │  │                                                          │
│ [💳] │  │  ┌──────────────┐ ┌──────────────┐                     │
│ Bill │  │  │ ACTIVE STRAT.│ │ RECENT SIGNAL│                     │
│      │  │  │              │ │              │                     │
│ [⚙]  │  │  │ 2 of 6       │ │ XAUUSD BUY  │                     │
│ Set. │  │  │ running live │ │ 14:31:45     │                     │
│      │  │  │ 4 inactive   │ │ Entry: 2341  │                     │
│      │  │  └──────────────┘ └──────────────┘                     │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  ACCOUNT EQUITY CURVE (30 days)                         │
│      │  │                                                          │
│      │  │  ┌─────────────────────────────────────────────────┐   │
│      │  │  │                                           ╱      │   │
│      │  │  │                              ___╱╲___╱╲╱        │   │
│      │  │  │                    ___╱╲____╱                    │   │
│      │  │  │          ___╱╲____╱                              │   │
│      │  │  │ ____╱___╱                                        │   │
│      │  │  │ May 15  May 22  May 29  Jun 7   Jun 14          │   │
│      │  │  │ [1W] [1M] [3M] [YTD]  ← timeframe selector      │   │
│      │  │  └─────────────────────────────────────────────────┘   │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  ACTIVE STRATEGIES                                       │
│      │  │                                                          │
│      │  │  ┌─────────────────────────────────────────────────┐   │
│      │  │  │ London Breakout  ●LIVE  Today: ▲+$82.30 +0.8%  │   │
│      │  │  │ [mini spark chart ────────────╱─ ]              │   │
│      │  │  └─────────────────────────────────────────────────┘   │
│      │  │  ┌─────────────────────────────────────────────────┐   │
│      │  │  │ EMA + ADX        ●LIVE  Today: ▲+$60.20 +0.6%  │   │
│      │  │  │ [mini spark chart ──────────────╱──╲──╱─ ]      │   │
│      │  │  └─────────────────────────────────────────────────┘   │
│      │  │                                                          │
│      │  │  [View all strategies →]                                │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  RECENT SIGNALS (last 10)                               │
│      │  │                                                          │
│      │  │  Time       Symbol  Side  Entry    Exit     P&L         │
│      │  │  14:31:45   XAUUSD  BUY   2341.0   —        (open)      │
│      │  │  13:12:00   XAUUSD  SELL  2339.5   2337.0   ▲+$25.0    │
│      │  │  11:45:22   BTCUSD  BUY   68420    68550    ▲+$13.0    │
│      │  │  09:30:15   XAUUSD  BUY   2338.0   2335.0   ▼-$30.0    │
│      │  │                                    [View full history] │
└──────┘  └─────────────────────────────────────────────────────────┘
```

---

## Mobile (375px) — Stacked layout

```
┌─────────────────────────────┐
│ [Logo]  [Notifications] [=]│ ← hamburger
│ [! STOP ALL TRADING ]      │ ← full-width, always visible
└─────────────────────────────┘

┌─────────────────────────────┐
│ Dashboard        14:32 +07  │
│                              │
│ ┌───────────┐ ┌───────────┐ │
│ │BALANCE    │ │TODAY P&L  │ │
│ │$10,245.30 │ │▲ +$142.50 │ │
│ │Exness MT5 │ │+1.42%     │ │
│ └───────────┘ └───────────┘ │
│ ┌───────────┐ ┌───────────┐ │
│ │OPEN TRADES│ │ACTIVE STR.│ │
│ │3 trades   │ │2 running  │ │
│ │2B / 1S    │ │4 inactive │ │
│ └───────────┘ └───────────┘ │
│                              │
│ EQUITY CURVE                 │
│ ┌───────────────────────┐   │
│ │          ╱            │   │
│ │  ___╱╲__╱             │   │
│ │ ╱                     │   │
│ │ May     Jun    Jun 14 │   │
│ └───────────────────────┘   │
│ [1W] [1M] [3M] [YTD]        │
│                              │
│ ACTIVE STRATEGIES            │
│ ┌───────────────────────┐   │
│ │London Breakout ●LIVE  │   │
│ │▲ +$82.30 today  →     │   │
│ └───────────────────────┘   │
│ ┌───────────────────────┐   │
│ │EMA + ADX       ●LIVE  │   │
│ │▲ +$60.20 today  →     │   │
│ └───────────────────────┘   │
│ [View all strategies]        │
│                              │
│ RECENT SIGNALS               │
│ 14:31 XAUUSD BUY  (open)    │
│ 13:12 XAUUSD SELL ▲+$25     │
│ 11:45 BTCUSD BUY  ▲+$13     │
│ [View all signals]           │
└─────────────────────────────┘

BOTTOM NAV
┌───┬───┬───┬───┬───┐
│ ≡ │ ▦ │ ⟳ │ 💳│ ⚙ │
│Dsh│Str│Bck│Bil│Set│
└───┴───┴───┴───┴───┘
```

---

## Overview Card States

```
NORMAL STATE:
┌──────────────┐
│ TODAY P&L    │
│ ▲ +$142.50   │  ← arrow symbol PLUS green color (not color only)
│ +1.42%       │
└──────────────┘

NEGATIVE STATE:
┌──────────────┐
│ TODAY P&L    │
│ ▼ -$58.20    │  ← arrow symbol PLUS red color (not color only)
│ -0.57%       │
└──────────────┘

LOADING STATE:
┌──────────────┐
│ TODAY P&L    │
│ [████████]   │  ← skeleton loader, no stale value shown
│ [████]       │
└──────────────┘

NO BROKER CONNECTED:
┌──────────────────────────────┐
│ Connect your broker to see   │
│ live data.                   │
│ [Connect Exness MT5 →]       │
└──────────────────────────────┘
```

---

## Design notes

- Emergency Stop always in header — not in any dropdown or settings page
- P&L uses arrow + sign + color — never color alone (accessibility: P1 Warit on sunlit phone, colorblind users)
- Overview cards use JetBrains Mono for numbers — monospaced for alignment and readability
- Equity curve is interactive: hover tooltip shows date + value, keyboard accessible (arrow keys)
- Sidebar nav collapses to icon-only at medium breakpoints, hides to bottom nav on mobile
- "Last updated" timestamp always visible — users need to know data freshness in live trading context
- Empty state (no strategies active): show CTA to activate strategy, not blank space
