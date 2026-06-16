# Wireframe 05 — Strategy Detail
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
│ NAV  │  │ ← Back to Strategies                                     │
│      │  │                                                          │
│      │  │ London Breakout                              ● LIVE      │
│      │  │ XAUUSD / M15  |  Exness MT5  |  Running since Jun 1     │
│      │  │                                                          │
│      │  │ [Run Backtest]  [Edit Params]  [Stop Strategy ■]        │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  PERFORMANCE SUMMARY                                     │
│      │  │                                                          │
│      │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│      │  │  │TODAY P&L │ │TOTAL P&L │ │PROFIT    │ │MAX       │  │
│      │  │  │▲+$82.30  │ │▲+$412.50 │ │FACTOR    │ │DRAWDOWN  │  │
│      │  │  │+0.80%    │ │+4.10%    │ │1.72      │ │11.2%     │  │
│      │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│      │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│      │  │  │WIN RATE  │ │SHARPE    │ │TOTAL     │               │
│      │  │  │42%       │ │1.18      │ │TRADES    │               │
│      │  │  │(42/100tr)│ │(annual.) │ │100       │               │
│      │  │  └──────────┘ └──────────┘ └──────────┘               │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  EQUITY CURVE (live — 30 days)                          │
│      │  │                                                          │
│      │  │  ┌─────────────────────────────────────────────────┐   │
│      │  │  │ $10,412 ─────────────────────────────────────   │   │
│      │  │  │                                         ╱       │   │
│      │  │  │                                    ____╱        │   │
│      │  │  │                      ╱╲___╱╲______╱             │   │
│      │  │  │             ╱╲______╱                           │   │
│      │  │  │ $10,000 ───╱                                    │   │
│      │  │  │  May 15     May 22     May 29     Jun 14        │   │
│      │  │  │ [7D] [1M] [3M] [All]    Hover: Jun 14 $10,412  │   │
│      │  │  └─────────────────────────────────────────────────┘   │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  LIVE MODE TOGGLE                                        │
│      │  │                                                          │
│      │  │  Current mode:  ● LIVE TRADING                          │
│      │  │                                                          │
│      │  │  [Switch to Paper]  [Stop Strategy ■]                   │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  STRATEGY PARAMETERS                                     │
│      │  │                                                          │
│      │  │  ┌──────────────────────────────────────────────────┐  │
│      │  │  │ Lot Size         [0.01      ] ↑↓  (0.01–1.00)   │  │
│      │  │  │ Risk per trade   [1.0%      ] ↑↓  (0.5%–3.0%)   │  │
│      │  │  │ Stop Loss (pips) [25        ] ↑↓                 │  │
│      │  │  │ Take Profit (pip)[50        ] ↑↓  RR: 1:2.0 ✓   │  │
│      │  │  │ Max open trades  [2         ] ↑↓                 │  │
│      │  │  │ Session filter   [London: 07:00–10:00 UTC    ▾] │  │
│      │  │  │                                                   │  │
│      │  │  │ [Save Parameters]    [Reset to defaults]         │  │
│      │  │  │                                                   │  │
│      │  │  │ ⚠ Changing parameters on a live strategy will   │  │
│      │  │  │   apply to the next trade, not open positions.   │  │
│      │  │  └──────────────────────────────────────────────────┘  │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  TRADE HISTORY (this strategy)                          │
│      │  │                                                          │
│      │  │  #    Time        Side  Lots   Entry    Exit     P&L    │
│      │  │  100  14:31:45   BUY   0.01   2341.5   (open)   ▲+$14  │
│      │  │  99   13:12:00   SELL  0.01   2339.5   2337.0   ▲+$25  │
│      │  │  98   11:45:22   BUY   0.01   2338.0   2341.0   ▲+$30  │
│      │  │  97   09:30:15   BUY   0.01   2340.0   2335.0   ▼-$50  │
│      │  │                                                          │
│      │  │  [Load more]  [Export CSV]  [Export JSON]              │
└──────┘  └─────────────────────────────────────────────────────────┘
```

---

## Parameter Edit — Validation States

```
VALID:
│ Lot Size   [0.01] ↑↓     ✓ Valid
│ Risk/trade [1.0%] ↑↓     ✓ Valid  RR: 1:2.0

WARNING (high risk):
│ Risk/trade [3.5%] ↑↓
│ ⚠ Risk above 3% per trade increases drawdown risk.
│   Recommended: 0.5%–2%

ERROR (out of bounds):
│ Lot Size   [5.00] ↑↓
│ ✕ Maximum lot size for your account balance is 0.50

UNSAVED CHANGES:
│ [Save Parameters]  ← highlighted / enabled
│ [Discard changes]
│ ● Unsaved changes — parameters not applied yet
```

---

## Mobile (375px) — Scrollable detail

```
┌─────────────────────────────┐
│ ← London Breakout  ●LIVE   │
│                              │
│ XAUUSD / M15                │
│ Running since Jun 1         │
│                              │
│ [Run Backtest][Stop ■]      │
│                              │
│ ┌──────────┐ ┌──────────┐  │
│ │TODAY P&L │ │TOTAL P&L │  │
│ │▲+$82.30  │ │▲+$412.50 │  │
│ └──────────┘ └──────────┘  │
│ ┌──────────┐ ┌──────────┐  │
│ │PF: 1.72  │ │DD: 11.2% │  │
│ └──────────┘ └──────────┘  │
│                              │
│ EQUITY CURVE                 │
│ ┌───────────────────────┐   │
│ │     ╱╲___╱╲______╱   │   │
│ │____╱                  │   │
│ │ May 15        Jun 14  │   │
│ └───────────────────────┘   │
│ [7D][1M][3M][All]           │
│                              │
│ MODE: ● LIVE TRADING        │
│ [Switch to Paper]           │
│ [Stop Strategy ■]           │
│                              │
│ PARAMETERS  [Edit]           │
│ Lot: 0.01  Risk: 1%         │
│ SL: 25 pips  TP: 50 pips    │
│                              │
│ TRADE HISTORY               │
│ [Export CSV]                 │
│ 100  BUY 2341.5 (open) ▲   │
│ 99   SELL 2339.5 →2337 ▲   │
│ 98   BUY 2338.0 →2341 ▲    │
│ 97   BUY 2340.0 →2335 ▼    │
│ [Load more]                  │
└─────────────────────────────┘
```

---

## Design notes

- "Stop Strategy" button on detail page is for single-strategy stop — distinct from Emergency Stop All in header
- Params form: P1 Warit sees defaults and a "Restore defaults" button; P2 Priya can edit all fields
- RR ratio auto-calculates from SL and TP — shown inline as validation feedback
- Changing params on a live strategy shows explicit warning about effect timing (next trade, not current)
- Trade history: P3 Krit needs Export CSV/JSON — always visible, not behind a settings menu
- Chart tooltip: keyboard accessible — arrow keys move along equity curve, value announced to screen reader
- Win rate shown with absolute count (42% = 42 of 100) — raw numbers for P2/P3 trust
