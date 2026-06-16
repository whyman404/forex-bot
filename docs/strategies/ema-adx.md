# EMA50 + ADX14 Trend (XAU/USD H1)

> Classic trend-follower: filter for direction (EMA50) + trend strength (ADX14).

**Asset:** XAU/USD
**Timeframe:** H1
**Code:** `trading-engine/strategies/ema_adx_trend.py`

---

## Spec

- **Long entry:** `close > EMA50` AND `ADX14 > 25` AND `+DI > −DI`.
- **Short entry:** `close < EMA50` AND `ADX14 > 25` AND `−DI > +DI`.
- **SL:** `ATR14 × 1.5` from entry.
- **TP:** `ATR14 × 3.0` (1:2 RR) — or trailing stop at `ATR14 × 2.0`.

---

## Mechanics

- **EMA50** = trend direction filter. Long only above, short only below. Reduces fighting the trend.
- **ADX14 > 25** = trend STRENGTH filter. Without this, EMA crosses whipsaw in chops.
- **+DI / −DI** = direction confirmation. Aligns entry with prevailing directional movement.
- **ATR-based exits** = adaptive to volatility regime. A 40-pip SL in 2020 ≠ 40-pip SL in 2024.

---

## Parameter table

| Param | Default | Notes |
|---|---|---|
| `ema_period` | 50 | Don't optimize — convention; overfit factory if you do. |
| `adx_period` | 14 | Same. |
| `adx_threshold` | 25 | Standard "strong trend" threshold. |
| `atr_period` | 14 | Standard. |
| `sl_atr_mult` | 1.5 | Tighter (1.0) → more stop-outs. Wider (2.0) → fewer trades but bigger losses. |
| `tp_atr_mult` | 3.0 | 1:2 RR. |
| `use_trailing_atr` | false | Enable trailing stop instead of fixed TP. |
| `trail_atr_mult` | 2.0 | Distance behind price for trailing stop. |

---

## Expected metrics

| Metric | Expected range |
|---|---|
| Win rate | **35–45%** (trend follower — wins less often, wins bigger) |
| RR | 1 : 2 |
| Profit factor | **1.2 – 1.5** |
| Sharpe (ann.) | **0.5 – 1.0** |
| Max DD | **12 – 22%** (trend followers DD hard in chops) |
| Expectancy/trade | **0.15 – 0.35 R** |
| Avg trades/month | **8 – 16** |

---

## Risk warnings

- **Chop regimes** (May–July 2025 was a great example): you get 6–8 small losers in a row as EMA50 oscillates and ADX hovers around 25. The ADX threshold helps but isn't bulletproof.
- **Gold-specific:** macro headlines (Fed pivots, geopolitical) can cause SL gaps. ATR-based sizing helps but doesn't prevent gap risk.
- **Don't curve-fit `ema_period`.** Renaissance traders went bankrupt finding the "best EMA". Pick a convention (50) and live with it. Walk-forward test only the *strategy*, not its parameters.

## Kill criteria

- 60-day PF < 1.0 AND DD > 15%.
- ADX > 25 stops happening for 30+ days (no trends → no signals → no edge).
- > 60 days flat → consider regime change. Re-evaluate.
