# London Breakout (XAU/USD)

> Asian-range breakout at the London open. Old-school but durable.

**Asset:** XAU/USD (gold)
**Timeframe:** M5 / M15
**Code:** `trading-engine/strategies/london_breakout.py`

---

## Spec

1. **Asian range** = High and Low of the period **22:00–07:59 GMT** (prior session).
2. At **08:00 GMT**, place an OCO pair:
   - **Buy Stop** at `asian_high + 5 pips`
   - **Sell Stop** at `asian_low − 5 pips`
3. Whichever fills first cancels the other.
4. **SL** = fixed 40 pips from fill.
5. **TP** = `max(60 pips, 1.5 × Asian range)` — chooseable.
6. **Filters:**
   - Skip if `spread > 30 pts` at 08:00.
   - Skip if `asian_range < 30 pips` (no momentum) or `> 200 pips` (likely overnight news).
   - **1 trade per session.**

---

## Mechanics

- Asian session is statistically the lowest-volatility window for gold. Range from 22:00 GMT (Sydney open) to 07:59 GMT (London pre-open) captures consolidation. Liquidity hunters often pierce one side at London open.
- The "1.5× range" TP is conservative — backtest shows the simple "60 pip fixed" TP is more robust because Asian ranges vary widely (30–250 pips).

---

## Parameter table

| Param | Default | Notes |
|---|---|---|
| `buffer_pips` | 5 | Pip buffer above/below Asian H/L for stop entry. |
| `sl_pips` | 40 | Fixed stop. |
| `tp_pips` / `tp_mode` | 60 / `fixed` | Or use `range_mult` with `tp_range_mult=1.5`. |
| `min_range_pips` | 30 | Skip days with tiny Asian range. |
| `max_range_pips` | 200 | Skip blow-out days. |
| `spread_filter_pts` | 30 | Skip if entry spread too wide. |
| `max_trades_per_day` | 1 | Hard cap. |

---

## Expected metrics (honest)

Based on literature + 2018–2025 backtest convention. Your mileage will vary.

| Metric | Expected range | What's good |
|---|---|---|
| Win rate | **38–48%** | 45%+ is excellent |
| RR (TP/SL) | 1.5 : 1 | Built into design |
| Profit factor | **1.2 – 1.6** | > 1.3 = keep running |
| Sharpe (ann.) | **0.5 – 1.0** | > 0.8 = solid |
| Max DD | **8 – 18%** | Cap at 20% in risk manager |
| Expectancy/trade | **0.15 – 0.35 R** | > 0.2 R = profitable long term |
| Avg trades/month | **15 – 22** | Excludes filtered days |

> **Anything above these ranges = check for look-ahead bias or overfit.**

---

## Risk warnings

- **News days:** NFP, FOMC, CPI → breakouts often fail because the move was a *news spike*, not London momentum. Add an economic-calendar filter before live.
- **Sunday open:** Avoid if your broker quotes thin Sunday opens — Asian range gets distorted.
- **Spread spikes:** Exness gold spread can widen from 20 → 60 pts during news. The `spread_filter_pts=30` skip is essential.
- **Cluster of losers expected:** 4–6 in a row is normal. Don't kill the strategy until it underperforms its WF stats by 2σ for 60+ days.

---

## Kill criteria

Stop running this strategy and re-validate when ANY of:

- 30-day **Profit Factor < 0.9**.
- 30-day **win rate < 30%** (statistical regime shift).
- **Drawdown > 12%** of account → check correlation with other strategies.
- Broker changes Gold contract spec (rare but matters).
