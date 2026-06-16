# Financial & Regulatory Risk Flags

> Non-legal advice (we are not lawyers). Flags + recommended posture + items requiring **lawyer review before public launch**.
> **Author:** Argus Hayato | **Date:** 2026-06-14

---

## 0. Summary posture (recommended)

**Position ourselves as a TOOLS / SOFTWARE company, not an investment advisor.**

Key principles:
1. **User keeps custody** — user's MT5 account at Exness; we never hold user funds.
2. **No discretionary management** — user opts into strategies, can pause/stop anytime, kill switch.
3. **No performance claims as guarantees** — show backtest with all caveats, never "guaranteed profit".
4. **Disclaim heavy** — risk warning on signup, T&C, on every strategy page.
5. **Geo-fence aggressively** — block jurisdictions where status is unclear (US, EU restricted, Japan, etc.) until lawyer review.

This is the **lower-risk path** for a small team. The "higher" path (becoming licensed) is years of cost and regulatory burden — defer.

---

## 1. Thailand SEC (ก.ล.ต.)

### What applies
- **SEC Notification on algorithmic trading** primarily targets **licensed intermediaries** (brokers, asset managers, fund managers) — they must register their algos with SEC and have risk controls.
- **We are NOT a licensed broker**, **NOT a fund manager**, **NOT an investment advisor** (must check the definition under พ.ร.บ.หลักทรัพย์ฯ).
- We are a **software tool** that user connects to their broker.

### Likely status: ALLOWED with conditions
- We do NOT touch user's money or custody securities.
- We do NOT give "investment advice" (we provide a tool; user chooses to enable a strategy).
- We do NOT solicit investors with promised returns (DO NOT advertise like that).

### Watchpoints
- **Forex / CFD trading itself in Thailand is in grey area.** Thai SEC permits trading via licensed brokers only; Exness is offshore. Many Thai retail traders use offshore brokers; SEC does not enforce against retail users but has warned. **We do not facilitate the broker relationship** — user signs up with Exness on their own. Make this explicit.
- If we publish performance claims targeting Thai users, we could be deemed "investment advisor" → license required. **DO NOT publish performance as marketing.** Show data inside the product to logged-in users only with disclaimers.
- **Watch for crypto** — Thai SEC has Digital Asset Act 2018 regulating exchanges, brokers, and "digital asset fund managers". A bot that trades crypto on behalf of users could pull us into scope. Mitigate by: user connects own Binance, we never custody. Still, lawyer to confirm before crypto goes live.

### Recommendation
- **Lawyer review (Thai securities/fintech)** before public launch — confirm "tools provider" classification.
- **Add explicit T&C clause:** user warrants they are eligible to trade with their broker; we provide software only.
- **Geo-detect** Thailand and show local Thai-language disclaimer.

---

## 2. Acting as "Investment Advisor" risk (everywhere)

### Trigger lines (DO NOT cross)
- Publishing performance with implied promise ("our bot makes 30%/month") — promotional, soliciting reliance → advisor.
- Personalized recommendations based on user's specific situation → advisor.
- Managing user funds discretionarily → broker / asset manager.

### Safe practices
- Strategies are **products with documented mechanics**, not "advice."
- Performance shown is **historical / backtest with prominent disclaimers**:
  - "Past performance does not guarantee future results."
  - "Backtest results may not be achievable in live trading due to slippage, spreads, broker conditions."
  - "Trading carries substantial risk of loss including loss of principal."
- **User makes the decision** to enable each strategy; we provide info, they choose.
- **No "trust us with your money"** language anywhere. Ever.

### Marketing red lines
- "Guaranteed", "risk-free", "never lose", "passive income guaranteed", "95% win rate" (the README already flags this).
- Showing only winning trades, cherry-picked timeframes, no drawdown.
- Affiliate / IB schemes pushing users to specific brokers — **possible kickback regulation issue**.

---

## 3. Stripe Acceptable Use Policy

### Likely status: ALLOWED
- Trading bot / trading software is **generally permitted** under Stripe's ToS as long as:
  - We sell **software / subscription**, not "investment opportunity".
  - We do NOT custody user funds via Stripe.
  - We are NOT a money transmitter.
  - We do not promise returns on a payment.

### Watchpoints
- Stripe lists "investment services without proper license" as **restricted**. Our tools-positioning matters here.
- **Crypto trading**: Stripe has nuanced rules around digital assets. Selling software that helps users trade crypto on their own exchange is fine; facilitating crypto purchase via Stripe is restricted.
- **Marketing**: if Stripe sees promo claiming guaranteed returns, they may pause account.

### Recommendation
- Apply with clear company description: "SaaS subscription for trading automation software; users connect their own broker accounts; we do not custody funds or guarantee performance."
- Review Stripe Restricted Businesses list quarterly.
- Have Omise as Thailand fallback (already planned).
- **Do NOT use Stripe Connect** to push payouts to users — keep it pure subscription billing.

---

## 4. Exness Broker API / ToS

### Status: PERMITTED via MT5
- Exness supports **MetaTrader 5 + EA (Expert Advisors)** and API for retail traders. Automated trading via MT5 is a sanctioned use case (their entire platform supports it).
- We use MT5 terminal as the connector; user authorizes via their own MT5 login.

### Watchpoints
- **Exness ToS**: user's responsibility to comply with their account terms. We should remind user.
- **Investor password vs trader password**: investor password = read-only; trader = full trade. **If we only need read for reporting, ask user for investor password — minimize blast radius.** (For order placement we need trader password.)
- **High-frequency trading**: most retail brokers (incl. Exness) have anti-HFT rules. Our strategies are not HFT, but verify per strategy.
- **VPS region** can matter for execution; document choice.

### Recommendation
- Onboarding flow asks for trader password ONLY when "live trading" is enabled; offer read-only mode using investor password.
- Reminder to user: "By connecting your broker, you confirm this complies with your broker's terms of service."

---

## 5. Required disclosures (user-facing)

### Must appear (visible, not just buried)
1. **Signup page risk warning** (full screen, must scroll + tick):
   > "Trading forex, CFDs and crypto carries substantial risk of loss and is not suitable for all investors. Up to 100% of capital can be lost. You may lose more than your initial deposit (in leveraged products). Past performance, including backtest results, does not guarantee future returns. This platform is a software tool; we are not a broker, fund manager, or investment advisor. You are responsible for your own trading decisions."
2. **Strategy page disclaimer** (visible above performance):
   > "Backtest is hypothetical; live results will differ due to spread, slippage, and broker conditions. No profit is guaranteed."
3. **T&C** — drafted by lawyer. Must include:
   - We are a software tool, not an advisor.
   - User is solely responsible for trading decisions and losses.
   - We may pause / stop service for any reason (regulatory, technical, billing).
   - Liability cap to subscription fee paid.
   - Arbitration / jurisdiction clause (Thailand law; for international users consider neutral seat).
4. **Privacy Policy** — PDPA (Thailand) + GDPR (if EU users) — what we collect (email, MT5 server name, encrypted creds, trade history), retention, deletion rights, data processor (Stripe, Sentry, etc.).
5. **DPA** (Data Processing Agreement) with Stripe, Sentry, Cloudflare — they offer standard ones.
6. **Cookie banner** — strict, only essential cookies by default if EU users allowed.
7. **AML / KYC-lite notice** — we collect email + name + country; we may decline service to sanctioned jurisdictions.

### Geo-block (recommended, starting Phase-2)
- Block: US (SEC + CFTC strict), Canada (provincial regulators), EU (MiFID II + ESMA leverage rules), UK (FCA), Japan (FSA), Singapore (MAS), Australia (ASIC) — until lawyer review.
- Allow: Thailand (with disclaimers), SE Asia (case-by-case), LATAM (case-by-case).
- Detection: IP geo + signup country + occasional re-check; ToS forbids VPN circumvention.

---

## 6. Anti-money laundering / KYC-lite

### Why we need it (even as a tools company)
- Even SaaS providers may face AML scrutiny if used as part of fraud schemes.
- Stripe enforces some KYC at payment level (we benefit from this).

### Minimum (KYC-lite)
- Email verification.
- Country at signup.
- Sanctions list screening: name + country vs OFAC / EU / UN consolidated list (use a service like Sanctions.io). On match → block + manual review.
- Suspicious activity:
  - Multiple accounts same payment method.
  - Account creation followed immediately by chargeback.
  - Refund-and-rejoin pattern.

### Reporting
- Document any blocked attempt for our own records.
- We are not a financial institution → not subject to SAR filing in most jurisdictions, but consult lawyer for Thailand-specific AML rules.

---

## 7. Liability & insurance

### Recommendations
- **Liability cap** in T&C: equal to total fees paid in past 12 months.
- **Disclaimer of consequential damages**: "We are not liable for trading losses incurred from use of the platform."
- **Force majeure** clause: broker outage, exchange outage, market disruption.
- **E&O / Tech E&O insurance** (Phase-3): protects against claims of negligence in software. Annual premium small for SaaS; worth it before scaling.
- **Cyber insurance** (Phase-3): covers breach response cost.
- **D&O insurance** for founders once Co. is incorporated.

---

## 8. Corporate structure (recommended)

- **Incorporate as a Thai Co. Ltd.** with English name like "FBot Technologies Co., Ltd." — positions as a **tech company**, not a financial services entity.
- Articles of incorporation: "software development and SaaS provision" — NOT "investment advisory" or "asset management".
- Separate operating entity from any personal trading activity.
- Founders' personal liability protected (LLC equivalent).
- Open business bank account, not personal.

---

## 9. Action items before public launch

| # | Item | Owner | Phase |
|---|------|-------|-------|
| 1 | Engage Thai securities/fintech lawyer | Zeus | Pre-Phase-3 |
| 2 | T&C, Privacy Policy, DPA (lawyer-drafted) | Zeus + lawyer | Phase-2 |
| 3 | Risk warning gate on signup | Eos + Atlas | Phase-1 end |
| 4 | Strategy page disclaimer | Eos | Phase-1 |
| 5 | Geo-block + jurisdiction allowlist | Atlas + Hestia | Phase-2 |
| 6 | OFAC sanctions check on signup | Atlas | Phase-2 |
| 7 | Incorporate (Thai Co. Ltd) | Zeus | Pre-Phase-3 |
| 8 | DPA executed w/ Stripe, Sentry, CF | Zeus | Phase-2 |
| 9 | E&O + Cyber insurance | Zeus | Phase-3 |
| 10 | Quarterly review of Stripe / Exness ToS | Argus | Continuous |

---

## 10. Disclaimer of this document

This memo is **not legal advice**. It is an engineering / security perspective on regulatory risks. **Before public launch, engage a qualified attorney** in Thailand (securities + tech), and additional counsel for any other jurisdiction we operate in.
