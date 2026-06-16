# Donchian Channel Breakout (BTC/USDT H1)

> Turtle-style trend follower. 20-bar entry, 10-bar exit.

**Asset:** BTC/USDT
**Timeframe:** H1
**Code:** `trading-engine/strategies/donchian_breakout.py`

---

## Spec

- **Long entry:** `close > Donchian(20).upper` (highest high of last 20 bars, computed on prior bars).
- **Short entry:** `close < Donchian(20).lower`.
- **Exit:** trailing — close when `close` crosses the opposite `Donchian(10)` boundary.
- **SL:** opposite `Donchian(10)` (the Turtle rule: stop becomes your trailing exit).
- **Risk:** 2% per trade (vs 1% default — trend-followers tolerate higher per-trade risk because of low win rate).

---

## Mechanics

- The Donchian channel = rolling max/min. A "20-bar high" means the market made a new 20-period extreme — classic momentum signal.
- The 10-bar exit channel is tighter, so wins ride longer than losses. This asymmetry is the entire edge.
- Reference: Richard Dennis / William Eckhardt's *Turtle Traders* (1980s). Updated for crypto on H1 timeframe.

---

## Parameter table

| Param | Default | Notes |
|---|---|---|
| `entry_period` | 20 | Donchian for entry. |
| `exit_period` | 10 | Donchian for exit + SL. |
| `risk_per_trade_pct` | 2.0 | Higher than other strats — typical for trend followers. |

---

## Expected metrics

| Metric | Expected range |
|---|---|
| Win rate | **30 – 40%** (low — wins are big though) |
| RR | Variable; **avg win ≈ 2.5× avg loss** |
| Profit factor | **1.2 – 1.5** |
| Sharpe (ann.) | **0.4 – 0.9** |
| Max DD | **20 – 30%** (yes, this hurts) |
| Expectancy/trade | **0.2 – 0.4 R** |
| Avg trades/month | **6 – 12** |

> A Donchian strat with **win rate > 45%** is suspicious — likely look-ahead bias.

---

## Risk warnings

- **6+ consecutive losers is normal.** This is the price of catching the 1 trade that makes the year. If you can't psychologically tolerate this, do not run.
- **Drawdown depth.** Turtle strategies historically saw 30–40% DD even in their golden era. Our 15% circuit breaker (in `risk/manager.py`) will likely trip — set strategy DD limit higher (e.g. 25%) or skip.
- **Crypto-specific risk:** flash crashes can fill exit at a much worse price than the displayed `exit_lo` — this is captured in our slippage model but not perfectly.

## Kill criteria

- 12 consecutive losers (statistically rare; suggests regime change).
- 90-day PF < 1.0 AND DD > 25%.
- BTC volatility (e.g. measured by 30-day BVOL) collapses below the level the strategy was calibrated for — Donchian needs vol to work.
