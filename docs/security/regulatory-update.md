# Regulatory Update — Phase 2

> Live trading triggers heightened regulatory attention. This is practitioner guidance; legal review required.
> **Author:** Argus Hayato | **Date:** 2026-06-15
> **Reads with:** `financial-and-regulatory-risk.md` (Phase 1).

---

## 1. Thai SEC Posture — Final Read

**Our positioning** (preserves regulatory exemption):
- We are a **technology tools provider** ("software tools for retail traders").
- We do **NOT custody funds** — broker (Exness) holds funds.
- We do **NOT give individual investment advice** — strategies are user-configured; default templates are educational examples.
- We do **NOT operate a marketplace** for copying signals (no leaderboards, no top-trader follow until separately regulated path is clear — Phase 3+).
- We are **NOT a broker** (no order matching, no liquidity provision).

**Probable status:** outside direct Thai SEC licensing for retail brokerage / asset management — analogous to widely-used trading-bot SaaS (3Commas, Cryptohopper, Algora etc.).

🔴 **Action**: consult Thai counsel **before public launch**. Recommended firms:
- **Baker McKenzie Thailand** — fintech/securities team.
- **Tilleke & Gibbins** — fintech / data privacy.
- **Local SEC-focused boutique** (Weerawong C&P, etc.).

Specifically ask:
- Does our service trigger any of: (a) digital asset business license under Royal Decree, (b) PORS / Mutual Fund Management license, (c) investment advisor license?
- Are there marketing restrictions (e.g., we cannot show performance numbers without specific disclaimer)?
- Do we need SEC notification even if exempt?
- AML/KYC obligations on subscription payments (Stripe handles much; we may have residual).

---

## 2. SEA Market — Per-Country Notes

| Country | Authority | Status | Approach |
|---|---|---|---|
| Thailand | SEC + BOT | Tools provider — likely exempt; consult counsel | Launch with disclaimer |
| Singapore | MAS | Tools may be exempt under "execution-only" tech provider; but MAS is strict. Capital Markets Services Act applies if we "deal in capital markets products." | Consult MAS legal before SG launch. Phase 3+ |
| Malaysia | SC Malaysia | Tools provider may be acceptable; advise + tool distinction sharp | Phase 3 |
| Indonesia | OJK + BAPPEBTI | BAPPEBTI regulates forex; commercial use of MT5 with retail clients may need registration | Block Indonesia until cleared |
| Philippines | BSP / SEC PH | Forex retail tightly restricted | Block PH until cleared |
| Vietnam | SSC | Forex retail trading is in legal gray; may be prohibited for retail | Block VN until cleared |

**Defaults for Phase 2:**
- Whitelist (allowed countries): Thailand + EU (with GDPR mode) + UK + Australia.
- Greylist (require additional disclosures, monitor): Singapore, Malaysia.
- Blacklist (BLOCK): United States, all of OFAC-sanctioned list, Indonesia, Philippines, Vietnam pending legal review.

---

## 3. United States — BLOCK

**Why:**
- **SEC** treats algo trading tools that involve advisory function as "investment adviser" requiring registration (Investment Advisers Act of 1940). Tools provider distinction is narrower than in TH.
- **CFTC + NFA** regulate retail forex tightly (CFTC Part 23 + NFA Bylaws). Foreign brokers serving US retail must be NFA-registered (Exness is NOT registered with NFA for US retail).
- **State-level money transmitter** rules may apply.
- **Tax reporting** burden on us if classified as "broker" for tax purposes (1099-B / 1099-MISC).
- **Litigation environment**: class actions on misleading performance claims are common in US.

**Enforcement:**
- **IP geo-block** US (Cloudflare WAF country block + WAF rule).
- **KYC signup question**: "Are you a US person (citizen, resident, GC holder)?" → if yes, block.
- **Stripe customer country** check; reject US-billed cards.
- **Terms of Service** explicitly: "Service not offered to US persons."

🔴 **Hard gate:** if a US person is detected post-signup → suspend account + cancel subscription + refund pro-rata.

---

## 4. Sanctioned + Restricted Jurisdictions

OFAC + EU + UN sanctions lists at minimum:
- Russia, Belarus (post-2022 sanctions expansion).
- Iran, Cuba, North Korea, Syria.
- Crimea, Donetsk, Luhansk regions.
- Venezuela (selected).
- Updated quarterly: check OFAC SDN + EU consolidated list.

**Enforcement:**
- **IP geo-block** at edge (Cloudflare).
- **Sanctions name screening on signup** — match against OFAC SDN + EU consolidated list. Use service (ComplyAdvantage, Refinitiv) or open data (OpenSanctions.org).
- **PEP screening** (Politically Exposed Persons) — flag for manual review, do not auto-onboard.
- **AML rules**: if subscription payment exceeds threshold or pattern suggests structuring → review + report to authorities as required.

---

## 5. Marketing + Performance Disclosures

🔴 **Hard rule:** every numerical performance display includes:
> "Past performance does not guarantee future results. Trading carries risk of capital loss."

Applies to:
- Backtest results displayed to user.
- Strategy template marketing pages.
- Email campaigns.
- Social media posts.
- Founder-personal accounts when discussing the product (avoid spreading personal trade results as endorsement).

**Don't publish** backtest results in **public** marketing without disclaimer + footnote describing:
- Time period.
- Asset class.
- Was it walk-forward or in-sample?
- Did it include fees / slippage?
- Was it a single backtest or distributional?

**Don't make:**
- "Guaranteed returns" claims (ever).
- "X% per month" claims (ever).
- "Risk-free" anything (ever).
- "Better than [competitor]" comparisons without evidence.

**Email marketing**: separate consent + unsubscribe; never include backtest numbers without same disclaimers.

---

## 6. AML / KYC Considerations

**Lite KYC (Phase 2):**
- Verified email at signup.
- Country self-declaration.
- IP / payment country cross-check.
- Sanctions + PEP screening on signup.
- Stripe handles card-side KYC (cardholder address, name, identity verification by issuing bank).

**Full KYC (Phase 3 if needed):**
- Government ID (passport / national ID).
- Selfie liveness.
- Address proof.
- Tier-based limits (subscription tier vs verification tier).
- Use service (Onfido, Veriff, Sumsub, ShuftiPro).

**AML transaction monitoring:**
- Subscription payments aren't customer funds — Stripe handles; we don't transmit money to/from users.
- However: refunds + chargebacks pattern → monitor for abuse (covered in IR-P2-1).

---

## 7. User Acceptance / Consent Audit

At signup:
- [ ] T&C accept (version tracked).
- [ ] Privacy Policy accept (version tracked).
- [ ] Risk Disclosure scroll-to-bottom + tick (version tracked).
- [ ] Country declaration.
- [ ] "I am not a US person" tick.
- [ ] "I am not on a sanctions list" tick.
- [ ] Marketing consent (separate, opt-in).
- [ ] Audit log entry: timestamp + IP + UA + versions accepted.

On material change to ToS/Privacy/Risk:
- Re-consent banner on next login; user cannot use service until acknowledged.
- Audit log entry.

Before enabling live mode:
- [ ] Re-acknowledge risk disclosure (live-trading-specific).
- [ ] 2FA verified.
- [ ] Typed confirmation ("ENABLE LIVE TRADING").
- [ ] Audit log entry.

---

## 8. Liability Framing

Our ToS asserts:
- We are a technology provider.
- User is responsible for trades placed by their bot.
- User is responsible for risk management (we provide tools, including kill switch).
- We do not guarantee profitability or any return.
- We do not guarantee continuous availability (planned + unplanned downtime possible).
- Liability cap: most jurisdictions allow contractual cap; TH + EU enforce reasonable bounds (gross negligence / willful misconduct cannot be excluded).

🔴 **Legal review essential** — enforceability of liability caps varies by jurisdiction.

Cyber + E&O insurance (when budget allows) provides backup beyond contractual cap.

---

## 8b. Third-Party Signal Sources (Phase 3a — TradingView)

> Added 2026-06-16 in connection with TradingView integration. Reads with `tradingview-integration-risk.md` + `disclaimers-v2.md`.

**Position:** acting on third-party informational signals does NOT make us an investment adviser in TH or most SEA jurisdictions, **provided** we:
- (a) do not modify, supplement, or curate the signals (we route as-is);
- (b) do not present individual recommendations to specific users ("you should buy");
- (c) user **chose** the strategy template and **set** thresholds (no auto-tuning by us);
- (d) we disclose clearly that signals are 3rd-party and informational only;
- (e) we do not earn revenue tied to signal accuracy or to a referral from the data source.

**Risk if we cross any of (a)-(e):** could be treated as "personal recommendation" (MiFID II in EU) or "investment advice" (TH SEC), triggering licensing requirements.

### Required disclaimer wording (every TV-related UI surface)

> *"TradingView signals are informational only and do not constitute investment advice. Past performance does not guarantee future results."*

Applies to:
- Strategy template marketing pages.
- Strategy configuration screen.
- Signal preview screen.
- Per-signal log entry (shorter form: "Source: TradingView — informational").
- Backtest result screens using TV signals.
- Email notifications mentioning TV-driven trades.
- Risk Disclosure document (full Section — see `disclaimers-v2.md` Section 3.2).

### Geo-block restated

The TradingView feature does NOT change geo-block:
- US — **BLOCKED** (existing).
- Sanctioned jurisdictions — **BLOCKED** (existing).
- ID / PH / VN — **BLOCKED** pending legal review (existing).
- TH / EU / UK / AU / SG / MY — TV feature available subject to country's existing tier.

### Marketing constraint

Performance numbers from TV-signal strategies require the same disclaimer block as any other backtest (see Section 5).
**Additionally:** label as "Computed using TradingView technical analysis. Why Man 404 does not validate or endorse these results."

### Action items

🔴 **R10** Thai counsel notified of TV integration; written opinion on whether third-party signal routing affects exemption status.
🔴 **R11** EU counsel notified — confirm MiFID II "personal recommendation" boundary is preserved by user-set thresholds model.
🔴 **R12** Required disclaimer wording deployed on every TV UI surface.
🔴 **R13** Cease-and-desist response plan documented (`tradingview-integration-risk.md` Section 3.3 Plan B).

---

## 9. What to Push Off Until We Talk to Counsel

- Public marketing with performance numbers (delay until disclosure language reviewed).
- Affiliate / referral program (consider securities-promotion rules).
- Copy-trading feature (definitely regulated in most jurisdictions).
- Tokenized rewards / NFT badges (securities + token regulation).
- Operating outside our home jurisdiction with on-the-ground entity (CMP / financial-service licensing).
- Press releases about strategy returns.

---

## 10. Action Items Before First Live User

🔴 **R1** Thai counsel consulted; written opinion on file.
🔴 **R2** Geo-block enforced (US, sanctioned jurisdictions, Indonesia/Philippines/Vietnam pending).
🔴 **R3** Sanctions + PEP screening service contracted + integrated.
🔴 **R4** ToS, Privacy Policy, Risk Disclosure published + lawyer-reviewed.
🔴 **R5** Performance disclaimers on every display.
🔴 **R6** "Not a US person" gate at signup.
🔴 **R7** Live-mode consent flow (typed confirmation + 2FA + signed audit) implemented.

🟡 **R8** Cyber + E&O insurance quoted.
🟡 **R9** Singapore / Malaysia counsel consulted (Phase 3 prep).

---

## Sign-off

Argus Hayato: ____________ Date: ____________
Zeus Ryujin: _____________ Date: ____________
External Counsel: ________ Date: ____________
