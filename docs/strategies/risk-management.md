# Risk Management — Master Doc

> The non-negotiable rules that protect the account. Every strategy obeys these.
> — Kairos Toki, Quant Engineer

---

## Why this exists

A profitable strategy with bad risk management blows up. A break-even strategy
with great risk management survives long enough to be improved. **Risk is the
first system we build, not the last.**

---

## The three numbers that matter

| Limit | Default | Purpose | Code |
|---|---|---|---|
| **Per-trade risk** | **1%** of equity (hard cap 2%) | Bounds single-trade damage | `risk/position_sizing.py` |
| **Daily loss limit** | **5%** of equity | Forces a reset after a bad day | `risk/manager.py` |
| **Max drawdown circuit** | **15%** from peak equity | **Auto-kills the bot** | `risk/manager.py` |

Once max DD is hit, the bot is **disabled**. Only manual restart can re-enable
— after the user reviews trades and confirms intent.

---

## Per-trade sizing

We use **fixed fractional sizing** as the default:

```
position_size = (account_equity × risk_pct) / (sl_distance × pip_value_per_unit)
```

- `risk_pct` = 1% default per strategy.
- `sl_distance` = price distance to stop loss (NOT pips — converted to price).
- `pip_value_per_unit` = from `data/symbols.py` (XAUUSD = $10/pip/lot, BTCUSDT = $1/pip/unit).

For trend followers (Donchian) we allow **2%** because their win rate is lower
but their winners are bigger — Kelly math justifies it.

### ATR-based sizing (alternative)

```
sl_distance = ATR14 × 1.5
position_size = fixed_fractional(account, 1%, sl_distance)
```

Adapts to current volatility regime automatically. Used by EMA50+ADX.

### Kelly (capped at 25%)

Available via `risk.position_sizing.kelly_fractional()`. We default to **0.25×
full Kelly** because edge estimates are noisy. NEVER full Kelly — full Kelly
assumes you know your true edge. You don't.

---

## Daily loss limit

When realized P&L for the UTC day ≤ −5% of equity, the manager blocks new
entries until 00:00 UTC. Open positions are NOT force-closed (let them play
out naturally).

**Why?** A 5% down day is statistically rare but possible. Continuing to trade
after a 5% loss often turns 5% into 15% because of revenge-trading psychology.
Even for a bot, freezing entries enforces the discipline.

---

## Max-drawdown circuit breaker

```
drawdown_pct = (1 - current_equity / peak_equity) × 100
if drawdown_pct >= 15.0:
    disable_bot()
    close_all_positions()  # optional, user-configurable
```

This is the **non-negotiable** floor. If the strategy logic is wrong, if a
regime has shifted, if the broker has data issues — this catches everything.

Recovery from 15% DD requires +17.6% to break even. That's a real but
recoverable amount. Recovery from 50% DD requires +100% — that almost never
happens in practice.

---

## Lot-size limits per account size

To prevent absurd order sizes on small accounts:

| Account size | Max lot per trade (XAUUSD) | Max lot (BTCUSDT) |
|---|---|---|
| $500 – $2,000 | 0.05 | 0.02 |
| $2,000 – $10,000 | 0.20 | 0.05 |
| $10,000 – $50,000 | 1.00 | 0.20 |
| $50,000+ | per-risk-pct only | per-risk-pct only |

These are belt-and-suspenders; the risk_pct calculation should already produce
sensible lots, but if a parameter is misconfigured, this cap prevents disasters.

---

## Max open positions / correlation

- **Max open positions:** 6 across all strategies.
- **Max per symbol:** 1 (no pyramiding without explicit per-strategy opt-in).
- **Correlation buckets:**
  - `gold_block` = {XAUUSD, XAGUSD} — max 2 concurrent.
  - `btc_block` = {BTCUSDT, BTCUSD} — max 2 concurrent.

If you long XAUUSD via London Breakout while you're also long XAUUSD via
EMA+ADX, you've doubled your gold exposure without doubling your account.
The correlation cap prevents this.

---

## Kill switch behavior

When the kill switch trips:

1. **Disable new entries** across all strategies.
2. **Cancel all pending orders.**
3. **Optionally close all open positions** (default: yes; user-configurable).
4. **Send notification** (email + Discord webhook + UI banner).
5. **Persist disabled state** so a restart doesn't silently re-enable.

The bot can ONLY be re-enabled via:
- Manual UI action with confirmation, OR
- API call with auth + reason text logged.

We do not auto-recover. The user must confirm they understand what happened.

---

## What we monitor live (continuous)

- **Realized P&L (today / week / month)**.
- **Open exposure** per symbol + per asset class.
- **Current drawdown** vs peak.
- **Margin level** (MT5) / **available balance** (Binance).
- **Spread anomalies** — if XAUUSD spread > 100 pts, pause entries.
- **Latency** — order send → fill latency. If > 500ms 95th percentile, alert.

These feed Prometheus → Grafana (see Hestia's deployment doc).

---

## Strategy-level kill criteria

Each strategy doc has its own kill criteria (e.g. "30-day PF < 0.9"). These
are evaluated **monthly** in the retrospective. The risk manager doesn't
auto-kill strategies for performance — that's a human decision, informed by
the data.

The risk manager DOES auto-kill the **bot** for account-level damage (15% DD).

---

## What we DON'T do

- **No martingale.** Doubling down after a loss = guaranteed account death given enough time.
- **No SL removal "to let it bounce."** If your strategy needs no SL to win, your strategy doesn't have an edge — it has a hidden tail.
- **No "all-in" sizing.** No single trade should cost more than 2% of equity. Period.
- **No leverage above 1:30 default.** Even on MT5 where 1:500 is offered. Higher leverage doesn't make a bad strategy good; it makes a marginal strategy fatal.

---

## Summary

Risk management is what turns a bot from a casino into a business. Everything
else — strategy ideas, indicators, fancy ML — is downstream of this.

Treat these rules as load-bearing walls of the system. Do not let users
disable them in the UI. Make them adjustable only within sensible bands (e.g.
per-trade risk allowed 0.5–2.0%, never higher).

— Kairos
