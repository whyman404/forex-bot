# TradingView Integration — Risk Analysis (Round 3)

> Comprehensive security + legal + operational risk for adopting `tradingview-mcp` + `tradingview-ta` as a signal source for live trades.
> **Author:** Argus Hayato | **Date:** 2026-06-16
> **Reads with:** `threat-model-phase2.md`, `regulatory-update.md`, `secrets-audit.md`, `incident-response-update.md`, `secure-defaults.md`.
> **Scope:** Phase 3a — TradingView technical-analysis signals (`tv_signal` strategy family). NOT Phase-3b (alt providers / Yahoo Finance cross-check).

---

## TL;DR

We import recommendation strings ("STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL") from `tradingview-ta` (community lib that reverse-engineers TradingView's public scanner) and route them through our live-gate to place real orders via mt5-bridge. Five distinct risk classes emerge: (1) liability shift from informational-only upstream, (2) silent API drift, (3) ToS / scraping legal grey, (4) data staleness, (5) supply-chain on a community lib. None is a hard block if mitigations below are in place. **Verdict: conditional GO with new section-TV gates added to the live-trading launch checklist.**

---

## 1. Liability Shift — From "informational" to "live trades on user money"

### 1.1 The shift
- `tradingview-mcp` upstream is explicit: *"Not financial advice... It does not execute trades, manage money, or guarantee any result."*
- We take those informational outputs and translate them into real orders on user MT5 accounts.
- A reasonable plaintiff argument: *"Why Man 404 chose to act on TradingView outputs that were never intended for live execution; if the signal was wrong, Why Man 404 owns the loss."*

### 1.2 Risk
- **User-side blame attaches to us, not TradingView.** TradingView's disclaimer protects TradingView, not us. We are a separate downstream actor making an independent decision to execute.
- **In TH:** consumer protection law (CPA B.E. 2522) + civil liability still applicable. Our existing "tools provider" framing helps but is weaker when the signal source itself is informational.
- **In EU/UK:** GDPR + consumer rights + national investment-services rules (MiFID II's distinction between "investment advice" vs "general info"). We must NOT cross into "personal recommendation" territory.

### 1.3 Mitigations (must-do, not optional)
| # | Mitigation | Owner | Status |
|---|---|---|---|
| L-1 | **Consent v2 with TV-specific clause** — user must re-accept before any `tv_signal` strategy goes live. See `disclaimers-v2.md`. | Zeus + Argus | required |
| L-2 | **UI labels every TV-sourced signal/order** with "Source: TradingView (informational, not advice). User chose threshold." | Atlas + Kairos | required |
| L-3 | **ToS section TV** — explicit clause that signals are 3rd-party informational; we do not endorse; user bears trading risk; user-set thresholds determine execution. See `disclaimers-v2.md`. | Zeus | required |
| L-4 | **User-controlled thresholds** — we ship default templates (e.g., "STRONG_BUY on 4H + 1H agreement → 0.01 lot") but **do not auto-tune** them based on past performance. User edits = explicit acknowledgment. | Kairos + Atlas | required |
| L-5 | **No marketing claim "TradingView-powered profitable signals"** — frame as "TradingView technical analysis aggregator integrated into your bot." | Zeus | required |
| L-6 | **No leaderboard / copy-trading on TV strategies** in Phase 3a — keeps us out of "personal recommendation" zone. | Zeus | required |

**Residual risk:** medium-low. User can still sue; we have layered defenses. Insurance (cyber + E&O) recommended in Phase 3.

---

## 2. Signal Authenticity — Silent API drift + no contract with TV

### 2.1 The reality
- `tradingview-ta` (PyPI: `tradingview-ta`) is a **community-maintained library** that calls TradingView's `scanner.tradingview.com` endpoint. **We have no contract with TradingView.**
- TradingView can change their endpoint, response schema, or scoring algorithm without notice. The lib reverse-engineers; it does not consume a stable public API.
- The aggregate "recommendation" is computed from ~26 indicators (RSI, MACD, MA, Ichimoku, etc.). If TV adjusts weights, our strategy's behavior changes silently.

### 2.2 Risk scenarios
- **R-2.1 — Endpoint URL changes** → `tradingview-ta` raises exception → our engine sees errors → if not halted, falls back to last cached signal or "no signal." Bad either way.
- **R-2.2 — Schema field renamed / removed** → silent KeyError in our adapter → either crash (good — visible) or default-to-NEUTRAL (bad — silent skew).
- **R-2.3 — TV adjusts indicator weights or adds new ones** → "STRONG_BUY" now means a slightly different distribution of underlying conditions; our backtest is stale.
- **R-2.4 — TV blocks our IP or User-Agent** → all queries fail → strategies degrade. We have no SLA to invoke.
- **R-2.5 — TV silently returns wrong data** (cached/stale/poisoned) → we trade on bad info. Rare but possible.

### 2.3 Mitigations
| # | Mitigation | Owner | Status |
|---|---|---|---|
| A-1 | **TV health endpoint** — query a known stable symbol (`EURUSD`, `1h` interval) every 2 min; expect non-error; record latency. | Kairos | required |
| A-2 | **Halt on consecutive failures** — N=3 consecutive health-check failures → auto-halt all `tv_signal` strategies (engine flag) + alert. | Kairos + Argus | required |
| A-3 | **Schema validation** — Pydantic model for the recommendation response (`RECOMMENDATION`, `BUY`, `SELL`, `NEUTRAL` counts, `summary`, `oscillators`, `moving_averages`). Reject on schema mismatch with explicit log. | Kairos | required |
| A-4 | **Pin & test** — `tradingview-ta>=3.3,<4.0`; lockfile via `uv`/`pip-tools`; CI runs adapter against a recorded fixture + a live smoke-test daily. | Kairos | required |
| A-5 | **Surface to user** — UI badge "TV signal source: healthy / degraded / unavailable"; degraded → user-visible banner; unavailable → strategy auto-pauses. | Atlas + Kairos | required |
| A-6 | **Adapter is replaceable** — abstract `SignalSource` interface; TV is one implementation; Yahoo Finance / paid TV API can be swapped in Phase 4. | Kairos | required |
| A-7 | **Multi-TF agreement** — default templates require 4H + 1H agreement (or similar); single-TF signal alone is high-risk. Reduces poisoning blast. | Kairos | recommended |

**Residual risk:** medium. Halting on detect is fast; the unknown is **silent wrong data** (poisoning). Multi-TF + Phase-4 cross-source defends.

---

## 3. Rate Limits / Terms of Service — Scraping legal grey

### 3.1 The reality
- TradingView's Terms of Use, as of last review, restrict automated access of public-facing pages without explicit API agreement.
- `tradingview-ta` uses TV's **scanner endpoint** — which TV exposes publicly via `scanner.tradingview.com` and is consumed by their own widget. This is grey-zone: it's a public HTTP endpoint without authentication, but reusing it programmatically may violate ToS.
- **TradingView has issued cease-and-desist** to projects/companies that scraped at scale in the past. They have not, to our knowledge, prosecuted small community-lib users — but precedent exists.
- The community lib explicitly disclaims: *"Use at your own risk; respect TradingView's Terms of Service."*

### 3.2 Risk scenarios
- **R-3.1 — IP block** — TV puts our backend egress IP on a deny-list. All strategies stop overnight.
- **R-3.2 — Cease-and-desist letter** to Why Man 404 ("stop using our endpoint without commercial agreement"). We comply or face civil action.
- **R-3.3 — Cease-and-desist combined with reputation damage** — TV publicly names violators occasionally.
- **R-3.4 — Volume burst triggers TV rate limit** — 429s start coming back → strategies fail.

### 3.3 Mitigations
| # | Mitigation | Owner | Status |
|---|---|---|---|
| T-1 | **Aggressive caching** — same symbol+interval combo cached server-side for 60s (Redis); user previews share cache. | Kairos + Mnemosyne | required |
| T-2 | **Throttle** — max 4 concurrent TV requests at a time; 0.8s spacing between batches; per-user preview rate-limit 6/min. | Kairos | required |
| T-3 | **User-Agent identification** — set a stable `User-Agent: WhyMan404-Bot/0.7 (+https://whyman404.com/contact)` so TV can reach us before banning us. (Transparent good-faith.) | Kairos | recommended |
| T-4 | **Document in ADR** — `docs/architecture/adr-XXXX-tradingview-signal-source.md` records the trade-off, risk, and exit plan. Owners: Daedalus + Argus + Zeus. | Daedalus | required |
| T-5 | **Plan B documented** — if TV blocks us or sends C&D, fallback is: (a) pause `tv_signal` strategies, (b) offer affected users a refund pro-rata for that strategy month, (c) evaluate paid TV API (~$15-50/user/mo) or alt source (Yahoo Finance + custom aggregator). | Zeus + Daedalus | required |
| T-6 | **Monitor for 429/403/451** — log + alert; treat as early warning. | Kairos | required |
| T-7 | **Pursue official TV API conversation** — once user base > 100, reach out to TradingView business team for proper licensing. | Zeus | post-launch |

**Residual risk:** medium. Mitigations don't eliminate ToS risk — they reduce blast radius (cache + throttle) and ensure we can pivot. Worst-case = strategy-family becomes unavailable; users compensated; no existential threat to the platform.

---

## 4. Data Freshness — Stale signal = wrong trade

### 4.1 The reality
- TV's scanner aggregates indicators on rolling windows. The `generated_at` timestamp may lag wall-clock by tens of seconds to a few minutes depending on cache layers.
- Forex moves fast — a "STRONG_BUY" computed 8 minutes ago may be invalid now if a news event hit.
- Our engine runs at strategy-defined intervals (e.g., every 5 min). Without a freshness check, we could place an order on a signal that's already invalid.

### 4.2 Mitigations
| # | Mitigation | Owner | Status |
|---|---|---|---|
| F-1 | **Embed `generated_at`** in signal record at ingest time. Use server-side `datetime.now(UTC)` at successful TV response, not the strategy's tick time. | Kairos | required |
| F-2 | **Max-age check** in live gate — `signal_age <= 300s` (5 min) or reject with audit. | Kairos | required |
| F-3 | **Halt strategy if > 5 min stale** for 3 consecutive ticks → halt + alert. (No fallback to "use it anyway".) | Kairos + Argus | required |
| F-4 | **Surface to user** — UI shows signal age badge on every TV-sourced strategy card. | Atlas | required |

**Residual risk:** low if F-1..F-3 are wired. The remaining risk is "TV returns a value labeled as fresh but actually cached upstream" — addressed by health-check + multi-TF agreement.

---

## 5. Supply Chain — Community libs + their transitive deps

### 5.1 The reality
- `tradingview-mcp-server` (MCP server, Node-based depending on impl) and `tradingview-ta` (Python) are community projects. Single-maintainer or small-team. Smaller attack surface for the project, but also less testing.
- **A malicious or compromised release** could inject altered signals, exfiltrate, or RCE us.
- Their transitive deps (e.g., `requests`, `pandas`, `pydantic` in Python; `axios`, `node-fetch` in Node) carry their own CVE risk.

### 5.2 Mitigations
| # | Mitigation | Owner | Status |
|---|---|---|---|
| S-1 | **Pin exact versions** — `tradingview-ta==3.3.0` (or current); `tradingview-mcp-server@0.7.x` with explicit minor pin. Lockfile committed. | Kairos | required |
| S-2 | **SBOM update** — `docs/security/sbom-update.md` lists both with source, security contact, last audit date. CycloneDX SBOM artifact stored. | Argus | required |
| S-3 | **Dependabot / Renovate** — weekly updates with security label triage; never auto-merge security PRs without human review (the worst attacks land in "security fix" releases). | Kairos | required |
| S-4 | **Repo scan on install** — `pip-audit` + `trivy fs` in CI on the lockfile; fail on Critical/High. | Argus + Kairos | required |
| S-5 | **Run in isolated process** — TV adapter runs in a separate worker; cannot read MT5 credentials; cannot touch broker_credentials DB rows. Least-privilege per service. | Daedalus | required |
| S-6 | **No exec / no shell** — TV response is parsed via Pydantic; never `eval`/`exec`/`pickle.loads`. Code review enforces. | Argus | enforced via lint |
| S-7 | **Watch upstream** — subscribe to `tradingview-ta` GitHub releases; subscribe to `tradingview-mcp` releases; security contact email on file. | Kairos | required |

**Residual risk:** low-medium. Community lib supply-chain is inherently weaker than vendored official lib. Isolation (S-5) caps blast radius.

---

## 6. Information Exposure — User's interests leaked via TV calls

### 6.1 The reality
- When user previews a TV scan, the symbol+interval combo goes over the wire to TV. TV (or a network observer between us and TV) can see which symbols our users are interested in (aggregate by IP).
- A scraper attacking **our** preview endpoint could enumerate "which symbols WhyMan404 supports" → low-value intel.

### 6.2 Risk
- **R-6.1 — Aggregate interest leak to TV.** Already true for any user using TradingView website directly; we don't add unique PII. We only send public ticker info.
- **R-6.2 — Our preview API enumerated** by competitor.

### 6.3 Mitigations
| # | Mitigation | Owner | Status |
|---|---|---|---|
| I-1 | **No PII in TV calls** — only ticker symbol + exchange + interval. Never user ID, email, IP-passthrough. Backend acts as a single client to TV. | Kairos | enforced |
| I-2 | **Per-user rate limit** on our preview endpoint — 6/min default. | Kairos | required |
| I-3 | **Cache shared** — same symbol+interval cache serves multiple users; reduces per-user query rate to TV. | Kairos + Mnemosyne | required |
| I-4 | **Privacy Policy** lists TradingView as a 3rd-party data source — anonymous request (no user data). See `disclaimers-v2.md`. | Zeus + Argus | required |

**Residual risk:** very low.

---

## 7. STRIDE Summary on `tv_signal` Component

| Threat | Description | Mitigation |
|---|---|---|
| **S**poofing | Attacker spoofs TV response to inject signal | Server-side calls only; backend is the only TV client; HMAC backend↔engine; multi-TF agreement |
| **T**ampering | TV response altered in transit | TLS to TV; certificate validation (no `verify=False`); schema validation; max-age check |
| **R**epudiation | User claims "I didn't agree to TV signals" | Consent v2 + audit log per acceptance + ToS section + UI labels per signal |
| **I**nfo disclosure | User's symbol interests exposed | No PII in calls; per-user rate-limit prevents external enumeration |
| **D**oS | TV blocks us OR scraper hammers our preview | Cache + throttle to TV; per-user rate limit; degrade gracefully (halt strategy, not full app) |
| **E**oP | TV adapter compromise → MT5 access | Worker isolation (S-5); least-priv DB role; cannot read broker_credentials |

---

## 8. Pre-Launch Gate (added to live-trading-launch-checklist.md Section TV)

🔴 TV1 `tv_disclaimer_consent_signed` v2 in user record before any `tv_signal` strategy can go live.
🔴 TV2 TV health endpoint reachable in last 5 min; auto-halt on 3 consecutive failures wired + tested.
🔴 TV3 `tv_strategy_min_paper_days` = 14 with TV-source signals (not local-indicator signals) before user can flip live.
🔴 TV4 Schema validation Pydantic model deployed; CI fixture test green.
🔴 TV5 Throttle (4 concurrent, 0.8s spacing) deployed + verified under load.
🔴 TV6 Cache (60s server-side per symbol+interval) deployed + hit-rate observable.
🔴 TV7 ADR `adr-XXXX-tradingview-signal-source.md` filed with exit plan.
🔴 TV8 Privacy Policy + ToS updated; lawyer-reviewed; live to users.
🔴 TV9 SBOM updated with `tradingview-mcp` + `tradingview-ta` pinned versions; provenance recorded.
🔴 TV10 IR playbook IR-P2-6 (TV API down) + IR-P2-7 (TV silent wrong data) signed off.
🟡 TV11 Cross-source verification (Yahoo Finance / alt) plan documented for Phase 4.
🟡 TV12 Reached out to TradingView business team for licensing conversation.

---

## 9. Risk Register Update

| ID | Risk | Sev (CVSS-ish) | Mitigation status | Residual | Owner |
|---|---|---|---|---|---|
| TV-R1 | Liability shift onto us | High → Medium with L1-L6 | required | medium-low | Zeus + Argus |
| TV-R2 | TV API breaks/changes silently | High → Medium with A1-A7 | required | medium | Kairos + Argus |
| TV-R3 | ToS violation / C&D / IP block | Medium → Low with T1-T7 + Plan B | required | medium | Zeus + Daedalus |
| TV-R4 | Stale signal → bad trade | Medium → Low with F1-F4 | required | low | Kairos |
| TV-R5 | Supply chain compromise | Medium → Low with S1-S7 + isolation | required | low-medium | Kairos + Argus |
| TV-R6 | Info exposure (low) | Low → very low | required | very low | Argus |

---

## 10. Sign-off

Argus Hayato (Security): ____________ Date: ____________
Zeus Ryujin (PM/Legal): _____________ Date: ____________
Daedalus Souta (Tech): _____________ Date: ____________
Kairos (Trading Engine): ____________ Date: ____________

Any 🔴 in Section 8 not green → NO `tv_signal` LIVE FLAG for any user.
