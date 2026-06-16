# Personas — Trading Bot SaaS
**Author:** Iris Kaguya (UX/UI Designer)
**Date:** 2026-06-14
**Project:** Forex/Crypto Trading Bot Platform

---

## Method

Built from composite user archetypes derived from publicly documented retail trader behavior patterns (nngroup, broker research, TradingView community). Validated against the three core subscription tiers: Free Trial, Pro Monthly, Lifetime.

---

## P1 — "The Beginner" — Warit S.

**Age:** 28
**Occupation:** Marketing executive, Bangkok
**Tech level:** Medium — comfortable with mobile apps, unfamiliar with trading terminals
**Device primary:** Mobile first, desktop second
**Plan target:** Free Trial → Pro Monthly

### Bio
Warit heard about algorithmic trading on a finance YouTube channel. He opened an Exness account but finds MT5 confusing. He wants to automate trading without having to understand every parameter. He is willing to pay if the bot "just works" and he can trust it.

### Goals
- Start trading without deep technical knowledge
- See results quickly to validate whether automation is worth paying for
- Understand what the bot is doing without reading documentation
- Know when to panic (and how to stop everything safely)

### Frustrations
- MT5 interface is overwhelming — too many buttons, too many panels
- Cannot tell if a strategy is "working" or just randomly making money
- Scared of losing money due to misconfiguration he does not understand
- Signup flows that ask for 10 fields before showing any value

### Behaviors
- Checks app on mobile during lunch and evening commute
- Reads performance numbers first, reads labels only when confused
- Trusts green = good, red = bad without reading metric names
- Will abandon a setup flow if it takes more than 3 minutes

### Mental model
Trading bot = "set and forget autopilot with a big red stop button I can hit anytime."

### Key UX needs
- 1-click strategy activation with sensible defaults
- Plain-language status: "Bot is running — 2 trades open — up 1.2% today"
- Emergency stop prominently visible always
- Onboarding that explains one thing per step, not a wall of text
- Mobile-optimized dashboard with large tap targets

### Quote
"I don't want to become a trader. I want the bot to trade for me while I do my real job."

---

## P2 — "The Active Retail Trader" — Priya M.

**Age:** 34
**Occupation:** Freelance digital consultant, part-time trader
**Tech level:** High — uses TradingView daily, understands indicators, has tried EAs before
**Device primary:** Desktop (two monitors), checks mobile for alerts
**Plan target:** Pro Monthly → Lifetime

### Bio
Priya has been manual trading for 3 years and wants to move toward semi-automation. She has strong opinions about strategy parameters. She wants to customize lot sizes, adjust risk per trade, and toggle strategies on and off based on market conditions. She distrusts black boxes.

### Goals
- Customize strategy parameters to match her risk profile (0.5% risk per trade, max 3 concurrent)
- Compare strategy performance side by side
- Run backtests on her own date ranges before going live
- Get real-time alerts without having to keep the dashboard open

### Frustrations
- Platforms that do not let her see the equity curve per strategy
- Hidden fees or vague performance reporting
- Backtests that do not account for spread or slippage
- "Simple mode" that strips features she needs

### Behaviors
- Spends 30–60 minutes on desktop reviewing performance after market close
- Adjusts parameters seasonally (e.g., tighter stops during high-impact news)
- Reads all metric cards — Sharpe, drawdown, win rate — not just P&L
- Will open DevTools if she suspects data is faked

### Mental model
Trading bot = "a co-pilot I can override, with full instrument visibility."

### Key UX needs
- Parameter form with validation and tooltips that explain what each value does
- Side-by-side strategy comparison view
- Backtest with slippage/spread inputs; equity curve + drawdown chart
- Notification settings: trade open, trade close, daily summary, drawdown alert
- Transparent data: show raw numbers, not just percentages

### Quote
"Show me the drawdown curve before you show me the win rate. That is where the truth is."

---

## P3 — "The Aspiring Quant" — Krit N.

**Age:** 39
**Occupation:** Senior software engineer, systematic trading as side project
**Tech level:** Expert — Python, SQL, has built MT4 EAs before, reads academic papers
**Device primary:** Desktop (large monitor), terminal access
**Plan target:** Lifetime (one-time investment mindset)

### Bio
Krit treats trading as an engineering problem. He evaluates platforms by reading API docs and checking if backtest results are reproducible. He wants to export trade data, call the API programmatically, and eventually build custom strategies on top of the platform. He will not pay for anything he cannot verify.

### Goals
- Access raw trade data via API or CSV export
- Run backtests with detailed tick-level precision and see full trade log
- Understand the exact execution logic of each strategy
- Integrate platform data with his own Google Sheets / Python analysis pipeline
- API key management for programmatic access

### Frustrations
- "Performance metrics" with no methodology documentation
- Platforms that do not let you export trade history
- Backtests with survivorship bias or look-ahead bias not disclosed
- Rate-limited APIs without clear documentation

### Behaviors
- Will read the entire settings page before activating anything
- Tests the API with curl before trusting the UI
- Checks latency and execution timestamps on every trade
- Refers other engineers to platforms that are technically honest

### Mental model
Trading bot = "infrastructure I run — I need access, transparency, and raw data."

### Key UX needs
- Full backtest report: equity curve, monthly P&L heatmap, trade-by-trade log with entry/exit price, spread, commission, slippage
- API key management with scoped permissions (read / trade / admin)
- CSV/JSON export for all historical data
- Strategy methodology page explaining signal logic and execution assumptions
- Changelog for strategy parameter updates

### Quote
"If I cannot reproduce the backtest result myself, I will not run it live with real money."

---

## Summary Matrix

| Dimension | P1 Warit (Beginner) | P2 Priya (Active) | P3 Krit (Quant) |
|---|---|---|---|
| Technical depth | Low | High | Expert |
| Primary device | Mobile | Desktop | Desktop |
| Decision driver | Simplicity, safety | Control, transparency | Data access, reproducibility |
| Plan target | Free → Pro | Pro → Lifetime | Lifetime |
| Most feared thing | Misconfiguring and losing money | Black box results | Unreproducible backtest |
| Emergency stop priority | Visible always, 1 tap | Quick access, confirmable | Keyboard shortcut + API |
| Backtest needs | None at start | Equity curve + metrics | Full trade log + methodology |
| Customization | Defaults only | Parameter-level | API + export |
