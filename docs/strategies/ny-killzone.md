# NY Killzone Reversal (XAU/USD)

> ICT-style "sweep the Asian extremes and reverse" within the NY open window.

**Asset:** XAU/USD
**Timeframe:** M5
**Code:** `trading-engine/strategies/ny_killzone.py`

---

## Spec

- **Window:** 13:30–16:00 GMT (NY equities open + first 2.5h).
- **Setup:**
  1. Price during the window must **sweep** the Asian session High or Low
     (defined as 22:00–07:59 GMT prior to today's London session).
  2. The M5 candle that swept must **close back inside** the Asian range.
  3. Enter **opposite** direction (reversal trade).
- **SL:** 30 pips beyond the swept extreme.
- **TP:** 60 pips → **1:2 RR**.
- One trade per session.

---

## Why it can work

- The Asian range is a magnet for "liquidity hunting" algos at session opens.
- A failed breakout (sweep + reject) is a classic reversal signature on gold.
- 1:2 RR means you can win less than 50% and still be profitable.

## Why it often doesn't

- **Strong trend days** (CPI release, geopolitical shock) → the sweep keeps going. Mid-2025 had several months where this strat bled.
- Low-vol days → no sweep, no signal. Zero trades is fine; forcing trades isn't.

---

## Parameter table

| Param | Default | Notes |
|---|---|---|
| `sl_pips` | 30 | Distance beyond the swept extreme. |
| `tp_pips` | 60 | 1:2 RR vs SL. |
| `max_trades_per_day` | 1 | Hard cap. |
| `spread_filter_pts` | 30 | Skip wide-spread fills. |

---

## Expected metrics

| Metric | Expected range |
|---|---|
| Win rate | **42–52%** |
| RR | 1 : 2 |
| Profit factor | **1.3 – 1.7** |
| Sharpe (ann.) | **0.7 – 1.2** |
| Max DD | **10 – 18%** |
| Expectancy/trade | **0.2 – 0.5 R** |
| Avg trades/month | **8 – 14** (low frequency) |

---

## Risk warnings

- **News calendar filter is critical.** Disable on FOMC, NFP, CPI release days. We integrate this in the OMS layer (not in the strategy code).
- **Asian range correctness:** the strategy relies on the Asian H/L being computed from the *correct* session window. Verify your data feed's tz handling.
- **Look-ahead:** signals fire on the close of the rejection candle. The runner reflects this — entries fill at the close, not the next bar's open.

## Kill criteria

- 30-day PF < 0.9.
- Drawdown > 12% on this strat alone.
- 60-day win rate < 35% — regime shift, re-validate.
