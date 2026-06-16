# Grid Bot (BTC/USDT M15/H1)

> Mean-reversion ladder. High win-rate per leg, BUT inventory risk is real.

**Asset:** BTC/USDT
**Timeframe:** M15 / H1
**Code:** `trading-engine/strategies/grid_bot.py`

---

## ⚠️ READ THIS FIRST

Grid bots have a seductive marketing pitch — "95% win rate!" — but this is the
**most dangerous** of the six strategies in this system. The win rate is high
because each leg's TP is ~1% away. But every **un-closed** position is
inventory you're stuck holding while price trends against you.

**One sustained trend day can wipe out months of accumulated grid profits.**

**Mandatory rule:** Hard SL at **±15% from center**. We do **not** ship this
strategy without a kill switch. If a user disables the SL, the system refuses
to run the strategy.

---

## Spec

- **Center anchor:**
  - `vwap` → daily VWAP, recomputed at 00:00 UTC.
  - `ema50` → EMA50 on the same timeframe (smoother, slower to re-anchor).
- **Levels:** 10 buy-limit BELOW center + 10 sell-limit ABOVE center.
- **Spacing:** 1.0% per level.
- **TP per leg:** +1.0% (i.e. price reaches next-higher level).
- **Hard SL:** if price moves 15% beyond center in either direction:
  1. Close ALL open grid positions.
  2. Cancel ALL pending grid orders.
  3. Disable the strategy until manual review.

---

## Mechanics

- Designed for **mean-reverting / ranging** regimes — sideways markets are gold for grid.
- In a trend regime: buy-side fills accumulate as price drops; if price keeps dropping, you hold N losing positions. The 15% hard SL is your floor.
- VWAP center re-anchors daily → grid follows slow drift, less likely to be way off-center.

---

## Parameter table

| Param | Default | Notes |
|---|---|---|
| `center_mode` | `vwap` | Or `ema50` (smoother, slower). |
| `n_levels` | 10 | Per side. 20 total. |
| `spacing_pct` | 0.01 | 1.0% between levels. |
| `tp_pct` | 0.01 | TP = next grid line. |
| `hard_sl_pct` | 0.15 | 15% from center. **DO NOT REMOVE.** |
| `rebalance_hourly` | false | Re-anchor more frequently if true. |

---

## Expected metrics (HONEST)

| Metric | Expected range |
|---|---|
| Win rate **per leg** | **85 – 95%** (this is what marketing screenshots show) |
| Profit factor | **1.0 – 1.3** (margin of safety: thin) |
| Sharpe | **0.3 – 0.7** (yes, lower than people think) |
| Max DD | **15 – 35%** (kills account if SL not enforced) |
| Expectancy/leg | small positive in range, large negative in trend |
| Avg trades/month | **40 – 80** legs (very active) |

> **The 95% per-leg win rate is REAL — but the 1-in-20 losing leg can be 5–10× larger than the wins.**

---

## When to enable, when to disable

**Enable** when:
- BTC realized 30-day vol is low-to-moderate (e.g. < 60% annualized).
- Price has been oscillating around a moving average for ≥ 2 weeks.
- No major macro event scheduled (FOMC, halving event, ETF news).

**Disable** when:
- Major trend just started (e.g. ATH break, new bear leg).
- Vol regime spike (>80% annualized 30-day vol).
- Drawdown on the strat > 10%.

This is the strategy where **regime detection** matters most. Future iteration: add HMM-based regime filter to auto-pause/resume.

---

## Kill criteria

- **Hard SL hit at any time.** Manual re-validation required before re-enable.
- 30-day P&L < 0 AND open inventory > 50% of grid capacity.
- BTC enters confirmed trend regime (e.g. weekly ADX > 30).
