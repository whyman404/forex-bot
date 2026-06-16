# Wireframe 06 — Backtest
**Author:** Iris Kaguya
**Date:** 2026-06-14
**Fidelity:** Mid-fi ASCII

---

## Desktop — Config Panel (before run)

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Header with Emergency Stop]                                        │
└─────────────────────────────────────────────────────────────────────┘
┌──────┐  ┌─────────────────────────────────────────────────────────┐
│ NAV  │  │ Backtest                                                 │
│      │  │                                                          │
│      │  │ Strategy: [London Breakout         ▾]                   │
│      │  │                                                          │
│      │  │ ┌──────────────────────────────────────────────────┐    │
│      │  │ │ CONFIGURATION                                     │    │
│      │  │ │                                                   │    │
│      │  │ │ Symbol     [XAUUSD              ▾]               │    │
│      │  │ │ Timeframe  [M15                 ▾]               │    │
│      │  │ │                                                   │    │
│      │  │ │ Date Range                                        │    │
│      │  │ │ From [2024-01-01  ] To [2025-06-14  ]           │    │
│      │  │ │      (calendar picker)   (calendar picker)       │    │
│      │  │ │ Duration: 17 months, 4,320 candles ✓             │    │
│      │  │ │                                                   │    │
│      │  │ │ Initial Capital   [$10,000.00     ]              │    │
│      │  │ │ Lot Size          [0.01           ] ↑↓           │    │
│      │  │ │ Risk per trade    [1.0%           ] ↑↓           │    │
│      │  │ │ Stop Loss (pips)  [25             ] ↑↓           │    │
│      │  │ │ Take Profit (pips)[50             ] ↑↓  RR 1:2  │    │
│      │  │ │ Max concurrent    [2              ] ↑↓           │    │
│      │  │ │                                                   │    │
│      │  │ │ Advanced settings [+]                             │    │
│      │  │ │   Spread (pips)   [2.0            ] ↑↓           │    │
│      │  │ │   Slippage (pips) [0.5            ] ↑↓           │    │
│      │  │ │   Commission/lot  [$7.00          ]              │    │
│      │  │ │                                                   │    │
│      │  │ │ ⚠ Results use historical data only. They do not │    │
│      │  │ │   guarantee future trading performance.           │    │
│      │  │ │                                                   │    │
│      │  │ │            [    Run Backtest    ]                │    │
│      │  │ └──────────────────────────────────────────────────┘    │
└──────┘  └─────────────────────────────────────────────────────────┘
```

---

## Desktop — Running State

```
┌──────┐  ┌─────────────────────────────────────────────────────────┐
│ NAV  │  │ Backtest — Running                                       │
│      │  │                                                          │
│      │  │  London Breakout / XAUUSD / M15                         │
│      │  │  Jan 2024 – Jun 2025                                     │
│      │  │                                                          │
│      │  │  ┌──────────────────────────────────────────────────┐   │
│      │  │  │  Calculating...                                   │   │
│      │  │  │                                                   │   │
│      │  │  │  [████████████████████░░░░░░░░] 64%              │   │
│      │  │  │                                                   │   │
│      │  │  │  Processing: May 2025 data                        │   │
│      │  │  │  Elapsed: 8s  |  Estimated: 4s remaining          │   │
│      │  │  │                                                   │   │
│      │  │  │  [Cancel]  ← always available                     │   │
│      │  │  └──────────────────────────────────────────────────┘   │
└──────┘  └─────────────────────────────────────────────────────────┘
```

---

## Desktop — Results Page

```
┌──────┐  ┌─────────────────────────────────────────────────────────┐
│ NAV  │  │ Backtest Results — London Breakout / XAUUSD / M15       │
│      │  │ Jan 2024 – Jun 2025  |  Spread: 2.0  Slippage: 0.5      │
│      │  │                                                          │
│      │  │ [Modify Params] [New Backtest] [Export CSV] [Export JSON]│
│      │  │                                                          │
│      │  │  SUMMARY METRICS                                         │
│      │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│      │  │  │NET PROFIT│ │PROFIT    │ │MAX       │ │SHARPE    │  │
│      │  │  │▲+$1,420  │ │FACTOR    │ │DRAWDOWN  │ │RATIO     │  │
│      │  │  │+14.20%   │ │1.72      │ │▼-11.2%   │ │1.18      │  │
│      │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│      │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│      │  │  │WIN RATE  │ │TOTAL     │ │AVG WIN   │ │AVG LOSS  │  │
│      │  │  │42%       │ │TRADES    │ │+$48.20   │ │-$28.50   │  │
│      │  │  │(252/600) │ │600       │ │(per trade│ │per trade)│  │
│      │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  EQUITY CURVE                                            │
│      │  │                                                          │
│      │  │  ┌─────────────────────────────────────────────────┐   │
│      │  │  │ $11,420 ────────────────────────────────────╱──  │   │
│      │  │  │                                        ╱╲__╱     │   │
│      │  │  │                             ╱╲___╱╲__╱           │   │
│      │  │  │                   ╱╲___╱╲__╱                     │   │
│      │  │  │       ╱╲___╱╲____╱                               │   │
│      │  │  │ $10,000 ─╱                                       │   │
│      │  │  │  Jan 24  Apr 24  Jul 24  Oct 24  Jan 25  Jun 25  │   │
│      │  │  └─────────────────────────────────────────────────┘   │
│      │  │                                                          │
│      │  │  DRAWDOWN CHART                                          │
│      │  │  ┌─────────────────────────────────────────────────┐   │
│      │  │  │   0% ──────────────────────────────────────────  │   │
│      │  │  │        ╲   ╲              ╲        ╲             │   │
│      │  │  │         ╲___╲╱╲___╱       ╲_______ ╲____╱       │   │
│      │  │  │ -11.2%                              (max DD)     │   │
│      │  │  └─────────────────────────────────────────────────┘   │
│      │  │                                                          │
│      │  │  MONTHLY P&L HEATMAP                                     │
│      │  │  ┌──────┬──────┬──────┬──────┬──────┬──────┐          │
│      │  │  │      │ Jan  │ Feb  │ Mar  │ Apr  │ May  │          │
│      │  │  ├──────┼──────┼──────┼──────┼──────┼──────┤          │
│      │  │  │ 2024 │+2.1% │-0.8% │+3.2% │+1.5% │+2.8% │          │
│      │  │  │ 2025 │+1.9% │+2.3% │-1.2% │+3.1% │+0.9% │          │
│      │  │  └──────┴──────┴──────┴──────┴──────┴──────┘          │
│      │  │  (Positive months: light green fill, Negative: light red│
│      │  │   + text label always shows % — not color alone)        │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  TRADE LIST (600 trades)                                 │
│      │  │                                                          │
│      │  │  #    Date      Side  Entry    Exit    Pips   P&L       │
│      │  │  600  2025-06-14 BUY  2341.0  2349.0  +8.0  ▲+$32.0   │
│      │  │  599  2025-06-13 SELL 2345.0  2340.0  +5.0  ▲+$20.0   │
│      │  │  598  2025-06-12 BUY  2338.0  2334.0  -4.0  ▼-$16.0   │
│      │  │  ...                                                     │
│      │  │                                                          │
│      │  │  [← Prev]  Page 1 of 60  [Next →]  [Export all CSV]   │
│      │  │                                                          │
│      │  │  ─────────────────────────────────────────────────────  │
│      │  │  [Activate This Strategy → Paper]                       │
│      │  │  [Activate This Strategy → Live]                        │
│      │  │  ⚠ Results are historical. Past performance does not   │
│      │  │    guarantee future results. Use paper trading first.   │
└──────┘  └─────────────────────────────────────────────────────────┘
```

---

## Mobile — Config (375px)

```
┌─────────────────────────────┐
│ ← Backtest                  │
│                              │
│ Strategy:                   │
│ [London Breakout       ▾]   │
│                              │
│ Symbol: [XAUUSD        ▾]   │
│ TF:     [M15           ▾]   │
│                              │
│ From: [2024-01-01  📅]      │
│ To:   [2025-06-14  📅]      │
│ Duration: 17 months ✓        │
│                              │
│ Capital:  [$10,000   ]      │
│ Lot size: [0.01      ]      │
│ Risk:     [1.0%      ]      │
│ SL:       [25 pips   ]      │
│ TP:       [50 pips   ] 1:2  │
│ Max trades:[2        ]      │
│                              │
│ [+ Advanced]                 │
│                              │
│ ⚠ Historical data only.     │
│   Not a future guarantee.   │
│                              │
│ [     Run Backtest    ]      │
└─────────────────────────────┘
```

---

## Design notes

- Advanced settings (spread, slippage, commission) collapsed by default — P3 Krit expands, P1 Warit never sees
- Disclaimer appears on config form AND on results page — not one or the other
- Monthly heatmap: colors (green/red) always accompanied by percentage text — never color alone
- Trade list is paginated, not infinite scroll — P3 Krit needs to jump to specific dates
- Export buttons visible immediately on results — not in a settings sub-menu
- Activation CTAs at bottom of results are "Paper" first, then "Live" — encourages testing (P1 Warit)
- Backtest job runs server-side — user can navigate away, notified on completion (bell icon)
- Error state: if backtest data unavailable for selected date range, explain which dates are available
