# Reality Check: Why 95% Win Rate Is the Wrong Goal

> Written for the user, in plain language, with respect.
> — Kairos Toki, Quant Engineer

---

## TL;DR

You asked for a bot that wins 95% of trades. **A 95% win rate is technically
achievable, but it's almost always a trap.** What you actually want is a bot
that is **consistently profitable**, with **drawdowns small enough that you
don't quit when it has a bad month.** Those are different goals — and the
metrics for one are not the metrics for the other.

This document explains why, and what to look at instead.

---

## The math problem

Imagine two strategies:

| | Strategy A | Strategy B |
|---|---|---|
| Win rate | **95%** | **45%** |
| Average win | $20 | $300 |
| Average loss | **$500** | $200 |
| Trades / month | 100 | 20 |
| **Net P&L / month** | **−$600** | **+$300** |

Strategy A wins 95 trades × $20 = $1,900.
Strategy A loses 5 trades × $500 = $2,500.
**Net: −$600. A LOSING strategy with a 95% win rate.**

Strategy B wins 9 × $300 = $2,700.
Strategy B loses 11 × $200 = $2,200.
**Net: +$500. A WINNING strategy with 45% win rate.**

The metric that matters is not how *often* you win, but how much you win
*when you win* versus how much you lose *when you lose*. This is captured in
**expectancy** and **profit factor**.

---

## What metrics professionals actually use

| Metric | What it tells you | Good value |
|---|---|---|
| **Expectancy (R)** | Avg profit per trade, expressed in units of risk | **> 0.2 R** |
| **Profit Factor** | Gross wins ÷ gross losses | **> 1.5** |
| **Sharpe Ratio** | Return per unit of volatility (annualized) | **> 1.0** |
| **Sortino Ratio** | Like Sharpe but only penalizes downside vol | **> 1.2** |
| **Max Drawdown** | Worst peak-to-trough loss | **< 20%** |
| **Calmar Ratio** | Annual return ÷ max drawdown | **> 0.5** |

Notice: **win rate is not on this list.** It's a vanity metric.

---

## How "95% win rate" claims usually work

When someone advertises a 95% bot, they're almost always doing one of these:

1. **No stop loss.** They let losers run forever, "waiting for bounce." This works until it doesn't — and when it stops, the account is gone.
   - **Example:** Martingale grid bots ("just add another buy if it goes down"). They win 95 trades in a row, then the 96th wipes the account.

2. **Tiny TP, huge SL.** They take 1-pip profit, accept 100-pip loss. The math says they will lose money long-term even with a 95% win rate (see Strategy A above).

3. **Cherry-picked period.** Tested only on a 3-month trending market and showed amazing results. Then deployed in the next regime and bled.

4. **Survivorship bias.** Shows you the bot that won, ignores the 9 that blew up.

We don't ship any of these.

---

## What we deliver instead

| Strategy | Realistic win rate | Profit factor target | Max DD target |
|---|---|---|---|
| London Breakout | 38–48% | 1.2–1.6 | ≤ 18% |
| NY Killzone | 42–52% | 1.3–1.7 | ≤ 18% |
| EMA50 + ADX | 35–45% | 1.2–1.5 | ≤ 22% |
| EMA + RSI Swing | 38–48% | 1.2–1.6 | ≤ 25% |
| Donchian Breakout | 30–40% | 1.2–1.5 | ≤ 30% |
| Grid Bot | 85–95% per leg | 1.0–1.3 (overall) | ≤ 35%* |

\* Grid bot drawdown is high because the high win rate masks tail risk. We
enforce a 15% hard kill-switch to prevent ruin.

Combined across a portfolio (run multiple strategies):
- **Expected win rate: 45–55%**
- **Expected Profit Factor: 1.4–1.6**
- **Expected Sharpe: 0.8–1.3 annualized**
- **Expected Max DD: 15–20%**

---

## What this means for you

- You will have **losing weeks**. Often. They are not bugs — they are part of the strategy's distribution.
- You will have **losing months**. 1 out of 4–5 is normal.
- A "good" year on this system is **+20% to +60%** with **−15% drawdown along the way**. Anyone who promises more without those caveats is either lying or about to blow up.
- The path matters: a year that ends +30% but went through a −40% drawdown is **worse** than a year that ends +20% with a −10% drawdown — even though the final number is smaller — because in the first one you'd have panicked and turned off the bot.

---

## How we'll show progress

Every backtest report and every monthly live retrospective will show **all** of:
1. Win rate (we still report it — it's just not the primary number).
2. Profit factor.
3. Sharpe + Sortino.
4. Max drawdown + drawdown duration.
5. Expectancy per trade in R.
6. Trade count.

You'll have **full transparency**. If a strategy degrades, you'll see it
within 30 days and we can adjust or kill it together.

---

## What we ask of you

- Trust the **process**, not the **last 5 trades**. The edge plays out over 100+ trades.
- Set realistic expectations with anyone you onboard to the platform (this matters for SaaS positioning).
- Pre-commit to your kill criteria. Before going live, write down "if drawdown hits X%, I will pause and review" — and let the bot enforce it.

We're not here to sell a fantasy. We're here to build something that **survives** so it can **compound**. That's the real prize.

— Kairos
