# Disclaimers v2 — TradingView-Aware Updates

> Concrete text updates to user-facing legal docs to accommodate TradingView as a 3rd-party signal source.
> **Author:** Argus Hayato | **Date:** 2026-06-16
> **Status:** Lawyer-review required before shipping.
> **Reads with:** `tradingview-integration-risk.md`, `regulatory-update.md`, `gdpr-pdpa-compliance.md`.

---

## How to Read

Each section below provides:
- **(a) what changes,**
- **(b) template paragraph(s)** ready for legal review,
- **(c) trigger** that forces re-consent or banner.

Anything in `[BRACKETS]` is a placeholder for the legal team to finalize.

---

## 1. Privacy Policy — Section "Third-Party Data Sources"

### 1.1 What changes
- Add TradingView as a data source we query on the user's behalf.
- Explicitly state: **no PII is sent to TradingView.** We send only public ticker symbols + intervals.
- TradingView is NOT a data processor of our users' personal data — we are not "transferring" personal data to them. Listed as a third-party data source for transparency.

### 1.2 Template paragraph (insert after "Service Providers" subsection)

> **Third-Party Market Data Sources.** To compute technical-analysis signals, we query public market-data services on our servers, including TradingView (operated by TradingView, Inc.). When we query these services, **we transmit only public market identifiers (e.g., currency pair "EURUSD" and timeframe interval). We do not transmit your name, email, account identifier, IP address, or any other personal data.** These queries are originated from our backend infrastructure, not from your browser or device. We rely on these services for informational technical-analysis outputs only; they do not constitute investment advice. If a service becomes unavailable, the affected feature will be temporarily paused and you will be notified. See our Risk Disclosure for details on how signals are used.

### 1.3 Vendor list update (Annex / DPA index)

Add row to vendor table:

| Vendor | Purpose | Personal Data Processed | DPA in Place |
|---|---|---|---|
| TradingView, Inc. | Public market-data and technical-analysis aggregation | **None** — public symbol + interval only | N/A (no personal data shared) |

### 1.4 Cookie banner — NO CHANGE
- TV calls are server-side. No browser-side cookies from TV are placed on the user.
- Cookie banner remains unchanged.

### 1.5 Trigger
- Existing users do NOT need to re-accept Privacy Policy for this update alone (no personal-data change), but **must see an in-app notice** of the policy change with link to diff. If user enables a `tv_signal` strategy, see Risk Disclosure trigger below.

---

## 2. Terms of Service — New Section "Third-Party Signals"

### 2.1 What changes
- Insert a new section explicitly addressing 3rd-party signal sources.
- State user-set thresholds determine execution.
- Limitation of liability extends to 3rd-party data outages or errors.

### 2.2 Template section (insert as new top-level numbered section, e.g., Section 11)

> **11. Third-Party Signal Sources**
>
> **11.1 What we do.** The Service offers strategy templates that can be configured to use technical-analysis outputs from third-party services, including but not limited to TradingView (the "Third-Party Signals"). When you enable such a strategy, the Service will query the third-party source at intervals you configure and, **only if the output meets the thresholds you set,** transmit an order request to your broker via the integration you have authorized.
>
> **11.2 Not investment advice.** Third-Party Signals are informational technical-analysis outputs produced by the third party. **They are not investment advice, not personal recommendations, and not endorsements by Why Man 404.** The third party explicitly states that its outputs are informational, do not execute trades, do not manage money, and do not guarantee any result. Why Man 404 does not modify, supplement, or validate these outputs; we simply route them according to your configuration.
>
> **11.3 Your decision, your risk.** You acknowledge and agree that:
> - (a) **you have chosen** to enable a strategy that uses Third-Party Signals;
> - (b) **you have set** the thresholds at which signals trigger orders;
> - (c) **you bear the full risk** of any trading loss that results from the use of Third-Party Signals through the Service;
> - (d) **Why Man 404 is not responsible** for the accuracy, timeliness, completeness, or availability of Third-Party Signals;
> - (e) **Why Man 404 does not auto-tune** thresholds based on past performance; any changes to your configuration are made by you.
>
> **11.4 Service availability.** The third-party services from which we obtain signals may become unavailable, change their output format, change their underlying algorithms, or terminate access without notice. When this happens, the Service may pause affected strategies until the issue is resolved or an alternative is available. Why Man 404 has no contract or service-level agreement with the third-party sources and cannot guarantee continuous availability of Third-Party Signal features.
>
> **11.5 Liability cap.** To the maximum extent permitted by applicable law, Why Man 404's total liability arising from or in connection with Third-Party Signals — including but not limited to errors, omissions, delays, unavailability, or wrongful outputs — is limited as set forth in Section [10 / "Limitation of Liability"]. Nothing in this Section limits liability for gross negligence, willful misconduct, fraud, or other liability that cannot be excluded by law.
>
> **11.6 No representation regarding licensing.** Some third-party data sources we query may not have provided a formal commercial licensing arrangement to Why Man 404. If a source notifies us that our use is not permitted or rate-limits or blocks us, we will pause affected features and may offer affected users a pro-rata refund of the corresponding subscription period for the affected strategy family. This Section 11.6 does not waive any right of the third party against Why Man 404.

### 2.3 Trigger
- **Material change to ToS** → re-consent banner on next login; existing users cannot use the Service until they re-accept. (Existing Phase 2 mechanism — see Section 7 of `regulatory-update.md`.)
- **Version bump:** ToS v2026-Q3-TV.
- **Audit log:** old version + new version + timestamp + IP + UA per user.

---

## 3. Risk Disclosure — TradingView-Specific Section

### 3.1 What changes
- New subsection: "Use of Third-Party Technical Analysis."
- Plain-language warning, larger font in the rendered UI.

### 3.2 Template paragraph

> **Use of Third-Party Technical Analysis.** Some strategies offered by the Service rely on technical-analysis outputs produced by third-party providers, including TradingView. **These outputs are informational only and do not constitute investment advice or a personal recommendation.** They are not produced by Why Man 404; we receive them from the third party and route them according to the thresholds you configure. The third party may change its calculation methodology, may experience outages, or may become unavailable to us at any time without notice. You understand and accept that **acting on third-party technical-analysis outputs carries the same risk of loss as any other trading decision, and possibly more risk if the output is delayed, stale, or computed differently than at the time of your initial strategy configuration.** Past results derived from such outputs (whether shown in backtests or live performance) do not guarantee future results.

### 3.3 Trigger — REQUIRED RE-CONSENT
- When the user enables their first `tv_signal`-family strategy in live mode:
  - **Modal**: full text of Section 11 of ToS + the Risk Disclosure paragraph above.
  - **Scroll-to-bottom required** to enable the accept button.
  - **Typed confirmation:** "I UNDERSTAND THIRD PARTY SIGNALS" — exact match.
  - **Audit log entry:** `tv_disclaimer_consent_signed = {version: "2026-Q3-TV", timestamp, ip, ua}`.
- Without this entry, the live-gate (Section TV1 of launch checklist) blocks any `tv_signal` order.

### 3.4 Subsequent material changes to TV provider / data sources
- If we add a new source (e.g., Yahoo Finance in Phase 4) → version bump + re-consent.
- If TV substantially changes its methodology in a way we are aware of → notice + offer to disable.

---

## 4. DPA / Vendor List Update

### 4.1 Action
- Add TradingView to internal vendor register (`docs/security/vendor-register.md` or equivalent).
- **No DPA required** (no personal data shared).
- Mark as "Data Source — Public Market Data" not "Data Processor."
- Security contact email: see TradingView contact page; subscribe to their status page if available.

### 4.2 Annual vendor review
- Argus reviews TV vendor status during quarterly compliance review.
- If TV publishes terms changes that affect our usage → recompute risk in `tradingview-integration-risk.md` Section 3.

---

## 5. Cookie Banner

**NO CHANGE.** TV calls are entirely server-side. No browser cookies set; no third-party scripts loaded; no client SDK from TV. The existing cookie banner with granular controls remains.

If we ever embed TV widgets client-side (Phase 4+) → reopen cookie banner review; categorize as "Functional / Analytics" depending on widget behavior.

---

## 6. Marketing Pages

### 6.1 Do say
- "WhyMan404 integrates TradingView's technical-analysis outputs into your bot."
- "Use TradingView's STRONG_BUY / BUY / SELL / STRONG_SELL signals to drive your strategy."
- "Configure your own thresholds — when to act and when to skip."

### 6.2 Do NOT say
- "TradingView-powered profits" — implies endorsement / guarantee.
- "Signals proven by TradingView" — implies validation we don't have.
- "Better than manual TradingView trading" — comparative claim without evidence.
- Numerical performance using TV signals without the standard disclaimer block.

### 6.3 Required footer on any TV-related marketing
> Past performance does not guarantee future results. TradingView technical-analysis outputs are informational and do not constitute investment advice. Use of the Service involves risk of capital loss. See our Risk Disclosure for details.

---

## 7. Audit / Compliance Trail

For each user who enables a `tv_signal` strategy:

```
audit_log entry: {
  event: "tv_disclaimer_consent_signed",
  user_id: <uuid>,
  version: "2026-Q3-TV",
  tos_version_accepted: "v2026-Q3",
  privacy_version_accepted: "v2026-Q3",
  risk_disclosure_version_accepted: "v2026-Q3-TV",
  typed_phrase: "I UNDERSTAND THIRD PARTY SIGNALS",  // (hashed if PII concern)
  timestamp: <utc>,
  ip: <user_ip>,
  ua: <user_agent>,
  source: "in-app modal",
}
```

Live-gate query before placing any `tv_signal` order:
```sql
SELECT * FROM audit_log
WHERE user_id = :u
  AND event = 'tv_disclaimer_consent_signed'
  AND version >= 'current_tv_version'
ORDER BY created_at DESC LIMIT 1;
```

If no row → order blocked, user redirected to consent modal.

---

## 8. Open Questions for Counsel

- Q1: In TH — does "third-party signal" framing trigger any additional disclosure under the SEC / BOT? (Likely no, but confirm.)
- Q2: In EU/UK — does our "user-set thresholds" framing keep us out of MiFID II "personal recommendation"? Recommend explicit confirmation.
- Q3: TradingView ToS — does our use of `scanner.tradingview.com` via `tradingview-ta` violate their terms? What is the C&D response plan if so?
- Q4: Is a separate "Third-Party Sources Addendum" preferred over inline ToS section, for easier amendment?
- Q5: Liability cap text in Section 11.5 — is it enforceable in TH + EU?

---

## 9. Sign-off

Lawyer review: ____________ Date: ____________
Argus Hayato (Security): __________ Date: ____________
Zeus Ryujin (PM/Legal): ___________ Date: ____________

Ship blockers:
- [ ] Privacy Policy template paragraph reviewed + finalized.
- [ ] ToS Section 11 reviewed + finalized.
- [ ] Risk Disclosure paragraph reviewed + finalized.
- [ ] Modal copy + UX reviewed by Atlas + Iris (UX).
- [ ] Audit-log schema for `tv_disclaimer_consent_signed` migrated.
- [ ] Live-gate query for TV1 implemented + tested.
