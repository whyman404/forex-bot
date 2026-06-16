# EMA12 / EMA26 Crossover + RSI14 (BTC/USDT H4)

> Momentum swing trader for crypto. RSI50 filter to skip weak crosses.

**Asset:** BTC/USDT (spot)
**Timeframe:** H4
**Code:** `trading-engine/strategies/ema_rsi_swing.py`

---

## Spec

- **Long entry:** EMA12 crosses ABOVE EMA26 AND RSI14 > 50.
- **Short entry:** EMA12 crosses BELOW EMA26 AND RSI14 < 50.
- **SL:** swing low (last 10 candles) for longs / swing high for shorts.
  - Fallback: fixed 3% from entry, whichever is **closer** (tighter risk).
- **TP:** trailing exit when EMA12 crosses back, OR fixed 6%, whichever first.

---

## Mechanics

- Classic Appel-style MACD cross idea, simplified.
- **RSI > 50 filter** = "momentum agrees" — prevents shorting in a bull leg or longing in a bear leg.
- **Swing-low SL** = market-structure stop, not a fixed pip arbitrary number.

---

## Parameter table

| Param | Default | Notes |
|---|---|---|
| `ema_fast` | 12 | Convention. |
| `ema_slow` | 26 | Convention. |
| `rsi_period` | 14 | Convention. |
| `rsi_threshold` | 50 | Long > 50, short < 50. |
| `swing_lookback` | 10 | Candles for swing-low/high. |
| `sl_pct_cap` | 0.03 | 3% — risk cap if swing is too far away. |
| `tp_pct_cap` | 0.06 | 6% — 1:2 RR vs 3% cap. |
| `use_trailing_ema` | true | Trail with EMA26 cross-back. |

---

## Expected metrics

| Metric | Expected range |
|---|---|
| Win rate | **38–48%** |
| RR | 1 : 2 (capped) |
| Profit factor | **1.2 – 1.6** |
| Sharpe (ann.) | **0.6 – 1.1** |
| Max DD | **15 – 25%** (crypto vol is brutal) |
| Expectancy/trade | **0.2 – 0.4 R** |
| Avg trades/month | **4 – 10** (H4 timeframe → low freq) |

---

## Risk warnings

- **Weekend gaps:** BTC trades 24/7 but volume dries up over weekends. False crosses common Saturday → Monday.
- **Stablecoin de-peg events** (rare but devastating) — strategy doesn't account for them. Use exchange-level safeguards.
- **Crypto bear markets** (e.g. 2022-style): EMA crosses chop and RSI50 filter cuts entries but not enough. Expect DD up to 25%.
- **0.05% taker fee** assumption requires Binance VIP-0 or better. Tiers above reduce fees → more edge.

## Kill criteria

- 60-day PF < 1.0 AND DD > 20%.
- Exchange listing change / pair delisting.
- Crypto goes to a 6+ month range (e.g. mid-cycle accumulation) → expect underperformance, but don't kill unless DD > 20%.
