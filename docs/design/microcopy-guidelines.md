# Microcopy Guidelines — Trading Bot SaaS
**Author:** Iris Kaguya (UX/UI Designer)
**Date:** 2026-06-14
**Project:** Forex/Crypto Trading Bot Platform

---

## Core Principle: Honesty Over Hype

Every word in this product touches real money. Users who misread a label or misunderstand a modal may lose funds. Copy must be precise, honest about risk, and never imply certainty about outcomes.

---

## Non-Negotiable Rules

1. Never promise or imply future gains
2. Never use phrases that predict market performance
3. Risk disclaimer must appear wherever performance data is shown
4. Confirmation modals for every irreversible action
5. Paper trading is always labeled as simulated — never confuse it with real results
6. Use "up" and "down" not "profit" and "loss" in live contexts where outcome is still open

---

## Risk-Aware Copy Patterns

### Performance numbers — always disclaim

```
PROHIBITED:
"Win 42% of the time!"
"Earn 14% per year"
"Our bot made 142% last year"
"Best-performing strategy"
"Guaranteed returns"

REQUIRED — pair all performance data with context:
"Win rate: 42% (historical backtest Jan 2024 – Jun 2025)"
"Net return: +14.2% (backtest, no guarantee of future results)"
"Past performance does not guarantee future results."
"Backtest results are based on historical data and do not represent live trading outcomes."
```

### Backtest results page disclaimer (non-optional)

```
⚠ These results are based on historical market data. They reflect how this
strategy would have performed in the past under the tested parameters. Past
performance does not guarantee future results. Trading involves significant
risk of loss. Use paper trading before going live.
```

### Strategy cards — live data

```
PROHIBITED:
"Profitable strategy"
"Best strategy"
"Up 82% since launch"

REQUIRED:
"Today: ▲ +$82.30 (+0.80%)" — factual, not interpretive
"Total since activation: ▲ +$412.50 (+4.10%)"
Always: past performance data, not prediction
```

---

## Test Before Live — Language Patterns

The product should consistently discourage jumping to live trading without paper testing first.

### Strategy activation flow

```
Step 1 — OFF to PAPER:
"Start paper trading this strategy (simulated trades, no real money)"

Step 2 — PAPER to LIVE:
"Activate live trading (real trades on your Exness account)"
Button: [Activate — Real Trades]
Not:    [Go Live!] or [Start Trading!]
```

### Backtest results — activation CTAs

```
Primary CTA:
[Try on Paper Trading First — Recommended]

Secondary CTA:
[Activate Live Trading]  ← less prominent, below primary

Below both buttons:
"We recommend running a strategy on paper trading for at least 2 weeks before activating live trading."
```

### Dashboard onboarding — first-time user

```
Step 1 text (after broker connected):
"You're ready to explore. Start with paper trading to see how a strategy performs
before using real money. You can switch to live trading any time."

Not:
"Start trading now!"
"Your bot is ready — let's make money!"
```

---

## Confirmation Modals — Irreversible Actions

Every action that cannot be easily undone requires a confirmation modal. The modal must:
1. State clearly what will happen
2. State clearly what will NOT happen (especially for emergency stop)
3. Name the thing being acted on (not generic "this item")
4. Make Cancel the visually dominant/default action

### Emergency Stop — All Strategies

```
Title:    Stop all trading?
Body:     This will stop London Breakout, EMA + ADX, and 1 other strategy
          from placing new trades.

          ⚠ Open positions will not be closed automatically.
            You must close them manually in MT5.

Primary:  [Keep Running]
Danger:   [Stop All Strategies]
```

### Stop Single Strategy

```
Title:    Stop London Breakout?
Body:     This strategy will stop opening new trades. Any open positions
          will remain open and must be managed in your MT5 terminal.

Primary:  [Keep Running]
Danger:   [Stop This Strategy]
```

### Activate Live Trading

```
Title:    Activate live trading?
Body:     London Breakout will place real trades on your Exness MT5 account
          using real money.

          Please confirm you understand:
          [x] Automated trading involves risk of financial loss
          [x] This bot will place real trades using my real money
          [x] I am responsible for monitoring my account

          Checkboxes must all be checked before confirm is enabled.

Primary:  [Cancel]
Danger:   [I Understand — Activate Live Trading]
```

### Cancel Subscription

```
Title:    Cancel Pro subscription?
Body:     Your access continues until July 14, 2026. After that, live trading
          will stop and your account reverts to Free Trial limits.
          You can resubscribe at any time.

Primary:  [Keep My Subscription]  ← emphasized
Secondary:[Yes, Cancel]           ← text link, low emphasis
```

### Delete Account

```
Title:    Permanently delete your account?
Body:     This will:
          · Stop all active trading strategies immediately
          · Delete your account, all settings, and trade history
          · Cancel your Pro subscription (no refund)

          This cannot be undone.

          Type "DELETE" to confirm:
          [________________]

Primary:  [Cancel — Keep My Account]
Danger:   [Delete My Account]  ← disabled until text field matches
```

### Revoke API Key

```
Title:    Revoke prod-read-key?
Body:     Any scripts or integrations using this key will immediately
          lose access. This cannot be undone — you will need to create
          a new key.

Primary:  [Keep This Key]
Danger:   [Revoke Key]
```

---

## Error Messages — Honest and Actionable

### Connection errors

```
PROHIBITED:
"Something went wrong"
"Error: 401"
"Failed"

REQUIRED — explain what, why if possible, what to do:
"Could not connect to Exness MT5. Check your account number and password."
"Cannot reach Exness-MT5Real8. Check the server name or try again."
"Connection timed out. This may be temporary — try again in a moment."
```

### Bot / strategy errors

```
"London Breakout could not open a trade. Reason: insufficient margin."
"Strategy stopped unexpectedly. Check your Exness account for details."
"Broker connection lost. Trading is paused. Reconnect to resume."
Not: "Error" or "Strategy failed"
```

### Payment errors

```
"Your card was declined. Please try a different payment method."
"Payment could not be processed. No charge was made to your card."
Not: "Payment error 402" or "Transaction declined"
```

---

## Labels — Trading Context Precision

### P&L display

```
Today P&L:    ▲ +$142.50 (+1.42%)   ← factual, no "profit/gain" framing
              ▼ -$58.20 (-0.57%)    ← factual, no "loss" in the label itself
              — (not running)

Open trade:   Unrealized: ▲ +$14.20  ← "unrealized" is critical — not yet real
              Not: "Profit: $14.20" — it hasn't closed

Balance:      Account balance: $10,245.30
              Not: "Your earnings"
```

### Strategy status labels

```
● LIVE        Real trades — your money is at risk
◑ PAPER       Simulated trades — no real money
○ OFF         Not running — no trades placed
! ERROR       Strategy stopped — action required
```

### Buttons — action clarity

```
PROHIBITED ambiguous labels:
"Submit"
"OK"
"Go"
"Confirm"  (alone, without object)

REQUIRED — verb + object:
"Save Parameters"       not "Save"
"Stop This Strategy"    not "Stop"
"Connect Broker"        not "Connect"
"Export Trade History"  not "Export"
"Update Password"       not "Update"
"Delete My Account"     not "Delete"
```

---

## Notification and Alert Copy

### Trade alerts

```
Trade opened:
"London Breakout opened a BUY trade on XAUUSD at 2341.5 (Jun 14, 14:31)"

Trade closed — profit:
"London Breakout closed XAUUSD BUY. Result: ▲ +$25.00. Exit: 2346.5"

Trade closed — loss:
"London Breakout closed XAUUSD BUY. Result: ▼ -$30.00. Exit: 2335.0"

Not: "You made $25!" or "Trade won!"
```

### Drawdown alert

```
Subject: [Alert] London Breakout drawdown reached 5%
Body: London Breakout strategy has reached a 5% drawdown from its peak
      equity. Review your settings or consider reducing position size.
      
      Current equity: $9,750.00 (Peak: $10,263.00, -5.0%)
      
      This is an automated alert. No action has been taken.
      [Review Strategy] [Stop Strategy] [Manage Notifications]
```

### System alerts

```
Broker disconnected:
"Your Exness MT5 connection was lost at 15:47. Trading is paused.
 Reconnect to resume. Open positions remain open in MT5."

New login alert:
"A new login to your account was detected. Chrome browser, Bangkok TH,
 Jun 14, 2026 at 14:32. If this was not you, secure your account now."
[It was me]  [Secure My Account]
```

---

## Placeholder Text — Not Instructions

```
PROHIBITED (instructions as placeholder — disappears on type):
Email field placeholder: "Enter your email address"
Password placeholder:    "Must be at least 8 characters"

REQUIRED:
Email placeholder:    "you@example.com"  (format example)
Password placeholder: "Password"         (field name only)
Lot size placeholder: "0.01"             (default value example)

Instructions go in visible label or helper text, not placeholder.
```

---

## Copy for P1 Warit (Beginner) — Plain Language Adaptation

When a setting affects risk but has a technical name, provide a plain-language helper:

```
Technical label: "Lot Size"
Helper text:     "The size of each trade. 0.01 = 1 micro lot = smallest possible.
                  Larger lots = larger potential gain and larger potential loss."

Technical label: "Max Drawdown"
Helper text:     "The largest drop in account value from peak to low point.
                  Lower is better. 20% means the account once dropped 20% from its highest value."

Technical label: "Profit Factor"
Helper text:     "Total profit divided by total loss. Above 1.0 means the strategy made more than it lost.
                  1.72 means for every $1 lost, $1.72 was gained."
```

---

## Copy Tone

```
DO:
- Direct and clear
- Specific about what will happen
- Honest about uncertainty and risk
- Respectful — no condescension
- Action-oriented ("Save", "Connect", "Stop")

DO NOT:
- Excited / promotional ("Amazing!", "Let's go!", "Crush it!")
- Minimizing risk ("Just", "Simply", "Easy as")
- Vague ("Something went wrong", "An error occurred")
- Promising outcomes ("You will earn", "Your strategy will profit")
- Technical jargon without explanation for P1 Warit contexts
```
