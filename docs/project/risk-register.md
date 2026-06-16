# Risk Register — Forex/Crypto Trading Bot Platform

**Owner:** Zeus Ryujin
**Date:** 2026-06-14
**Cadence:** Reviewed every sprint retro; new risks logged within 24h of discovery

## Scoring rubric

**Probability:** LOW (< 20%), MEDIUM (20-60%), HIGH (> 60%)
**Impact:**
- LOW = recoverable in < 1 day, no user impact
- MEDIUM = recoverable in 1-7 days, partial user impact, ≤ 5% scope shift
- HIGH = > 1 week recovery, major user impact, or 5-25% scope shift / cost overrun
- CRITICAL = project / business existence threat (regulator, lawsuit, mass user loss, reputational ruin)

**Risk Score:** Probability × Impact, prioritized by score then by CRITICAL impact first.

---

## Risk Matrix Summary

| ID | Category | Risk | Prob | Impact | Score | Owner |
|----|----------|------|------|--------|-------|-------|
| R01 | Technical | MT5 Windows VPS connectivity / latency / disconnect | MEDIUM | HIGH | **H** | Hestia |
| R02 | Technical | Windows VPS instability (MT5 terminal crash, RDP loss) | MEDIUM | HIGH | **H** | Hestia |
| R03 | Technical | Exness broker rate limit / IP block on algo traffic | LOW | HIGH | M | Hestia |
| R04 | Technical | Time sync drift causing wrong-bar entries | LOW | MEDIUM | L | Hestia |
| R05 | Strategy | Overfit: backtest looks great, live underperforms | HIGH | HIGH | **CRITICAL** | Kairos |
| R06 | Strategy | Regime change (vol collapse, central bank shift) breaks edge | MEDIUM | HIGH | **H** | Kairos |
| R07 | Strategy | Edge decay (alpha discovered by others, spreads narrow) | HIGH | MEDIUM | **H** | Kairos |
| R08 | Regulatory | Thai SEC tightens rules on retail algo SaaS / requires license | LOW | CRITICAL | **H** | Zeus |
| R09 | Regulatory | SEA cross-border: MY/VN/PH have differing rules on bot SaaS | MEDIUM | HIGH | **H** | Zeus |
| R10 | Regulatory | Securities Act exposure if labeled as "investment advice" | LOW | CRITICAL | **H** | Zeus |
| R11 | Financial | User real-money loss → lawsuit / public backlash | MEDIUM | CRITICAL | **CRITICAL** | Zeus |
| R12 | Security | Credential leak (broker API key, MT5 password) | LOW | CRITICAL | **H** | Argus |
| R13 | Security | Deposit theft via account takeover / order injection | LOW | CRITICAL | **H** | Argus |
| R14 | Business | Exness ToS change disallowing third-party automation | LOW | HIGH | M | Zeus |
| R15 | Business | Payment processor (Stripe/Omise) refund chargebacks / bans | MEDIUM | MEDIUM | M | Zeus |

---

## Detailed Risks + Mitigation

---

### R01 — MT5 Windows VPS connectivity / latency / disconnect
**Category:** Technical
**Probability:** MEDIUM
**Impact:** HIGH
**Trigger signals:** MT5 ping > 200ms, dropped ticks, terminal heartbeat missing > 30s

**Mitigation (preventive):**
- Windows VPS hosted in same data center region as Exness execution server (preferably Equinix LD4 London for Exness)
- Heartbeat ping every 10s from bot → backend; alarm if 3 consecutive miss
- Pre-launch latency benchmark (p95 < 200ms RTT) by Hestia in W2

**Mitigation (corrective):**
- Auto-restart MT5 terminal via Windows scheduled task on health check fail
- Backup VPS in different DC, hot standby, switchover playbook
- Strategy auto-pause on connectivity loss > 60s; alert ops

**Owner:** Hestia
**Review cadence:** weekly (live), daily during W5-W6 paper trading

---

### R02 — Windows VPS instability (MT5 terminal crash, RDP loss)
**Category:** Technical
**Probability:** MEDIUM
**Impact:** HIGH
**Trigger signals:** OS bluescreen, terminal process exit, RDP unreachable

**Mitigation (preventive):**
- Choose VPS provider with known MT5 SLA (Exness VPS / ForexVPS / NYC Servers)
- Resource overhead: 4 vCPU / 8 GB RAM minimum to avoid OOM
- Windows auto-update disabled; manual patching in maintenance window
- Strict process hardening: only MT5 + Python bot + monitoring agent

**Mitigation (corrective):**
- Watchdog service: detect MT5 process crash, relaunch within 30s
- Snapshots daily; restore tested in W4
- Failover VPS in standby with same MT5 config + creds (encrypted)

**Owner:** Hestia
**Review cadence:** weekly

---

### R03 — Exness broker rate limit / IP block on algo traffic
**Category:** Technical
**Probability:** LOW
**Impact:** HIGH
**Trigger signals:** order rejection with "too many requests", account flag email

**Mitigation (preventive):**
- Read Exness ToS + algo policy on Day 1 (Hestia W1)
- Conservative request rate: 5 req/sec ceiling, exponential backoff on rejection
- Stagger strategy ticks (don't fire all 6 simultaneously)
- Use legitimate MT5 terminal (no proxy / VPN) so traffic looks normal retail

**Mitigation (corrective):**
- If flagged: contact Exness support immediately; pause trading; review pattern
- Backup broker tested in design (IC Markets / OANDA) for fast switch if banned
- Disclaimer to user: "compliance with broker ToS is shared responsibility"

**Owner:** Hestia (technical) + Zeus (broker relations)
**Review cadence:** monthly

---

### R04 — Time sync drift causing wrong-bar entries
**Category:** Technical
**Probability:** LOW
**Impact:** MEDIUM

**Mitigation:**
- NTP sync enforced on Windows VPS (pool.ntp.org)
- Bot uses broker server time (from MT5 SymbolInfoTick) as truth, not local clock
- Health check: log time diff between local and broker every minute; alert if > 2s

**Owner:** Hestia
**Review cadence:** weekly

---

### R05 — Strategy overfit: backtest looks great, live underperforms ⚠️ TOP RISK
**Category:** Strategy
**Probability:** HIGH
**Impact:** HIGH
**Trigger signals:** OOS PF significantly lower than IS PF; paper trading divergence > 30% from backtest expectation

**Mitigation (preventive):**
- **Mandatory walk-forward analysis** (5+ folds) — Kairos W3
- **Hard split:** train 2022, validate 2023, test 2024 (untouched until final)
- **Parameter parsimony rule:** ≤ 3 tunable params per strategy
- **No look-ahead:** code review of every strategy by Hephaestus
- **Out-of-sample gate at M2:** strategy must pass PF>1.5, Sharpe>1.0, MaxDD≤20% on 2024 OOS data before promotion to paper trading

**Mitigation (corrective):**
- Paper trading is the ultimate gate — minimum 7 days continuous before any real money discussion (Phase 2)
- Performance monitoring with Bayesian update: alert if live PF deviates > 2 stddev from backtest expectation over 50+ trades

**Owner:** Kairos (with Hephaestus oversight)
**Review cadence:** weekly during W3-W6; daily during paper trading

---

### R06 — Regime change breaks edge
**Category:** Strategy
**Probability:** MEDIUM
**Impact:** HIGH
**Trigger signals:** volatility regime shift (VIX collapse, USD index break), central bank policy pivot, sudden correlation breakdown

**Mitigation (preventive):**
- Multi-regime backtest: test each strategy on 2018 low-vol, 2020 covid, 2022 inflation, 2024 normal
- Strategy diversification: not all 6 strategies same regime (trend + mean-revert + breakout mix)

**Mitigation (corrective):**
- Regime detection layer (Phase 4) — currently manual via Kairos weekly review
- Kill switch per strategy: auto-pause if rolling 20-trade Sharpe < 0

**Owner:** Kairos
**Review cadence:** monthly + on macro events

---

### R07 — Edge decay
**Category:** Strategy
**Probability:** HIGH
**Impact:** MEDIUM

**Mitigation:**
- Continuous strategy performance dashboard (Grafana) — Kairos owns
- Set "alpha half-life" expectation: assume each strategy edge degrades 30% per year
- R&D backlog Phase 4: refresh strategy library every 6 months
- User-facing: clearly disclose that historical ≠ future, with rolling 90-day live PF prominently displayed

**Owner:** Kairos
**Review cadence:** monthly

---

### R08 — Thai SEC tightens rules on retail algo SaaS / requires license ⚠️ CRITICAL impact
**Category:** Regulatory
**Probability:** LOW
**Impact:** CRITICAL
**Trigger signals:** SEC public consultation, news of competitor enforcement

**Mitigation (preventive):**
- Monitor SEC Thailand circulars weekly (Zeus + future legal advisor)
- **Position the product** as a **personal automation tool** (user automates their own account on their own broker) — NOT as "investment management" or "advisory"
- No custody of user funds (broker holds funds, we hold no money)
- No discretionary trading on behalf of user; strategies are mechanical and user-configurable
- Pre-launch legal review in Phase 2 W9-10

**Mitigation (corrective):**
- Ready-to-deploy geo-block at frontend (IP-based) if regulator targets TH retail
- Pivot plan B: open-source the engine, monetize through education
- Reserve fund (10% of Phase 2+ revenue) for legal contingency

**Owner:** Zeus (+ external counsel from Phase 2)
**Review cadence:** monthly; immediate if SEC announces consultation

---

### R09 — SEA cross-border: MY/VN/PH have differing rules
**Category:** Regulatory
**Probability:** MEDIUM
**Impact:** HIGH

**Mitigation:**
- Phase 1: launch only in TH (geo-fence at signup) to limit exposure
- Phase 3: legal review per country before opening
- ToS jurisdiction = Thailand for Phase 1-2
- Avoid SG (MAS is strict on algo / robo-advisory) until specific licensing path researched

**Owner:** Zeus
**Review cadence:** before each country expansion

---

### R10 — Securities Act exposure if labeled "investment advice"
**Category:** Regulatory
**Probability:** LOW
**Impact:** CRITICAL

**Mitigation:**
- **Strict messaging discipline:** never claim returns, never "advice", never "guarantee"
- Marketing copy reviewed by Zeus before publishing; legal review Phase 2
- UI never shows ranking like "best strategy" — only objective backtest metrics user reads themselves
- Risk disclosure prominently displayed pre-purchase + on every dashboard view
- "Past performance does not guarantee future results" mandatory footer

**Owner:** Zeus
**Review cadence:** every marketing copy change

---

### R11 — User real-money loss → lawsuit / public backlash ⚠️ TOP RISK
**Category:** Financial / Reputational
**Probability:** MEDIUM
**Impact:** CRITICAL
**Trigger signals:** any user complaint about loss > 20%, social media post, support ticket with legal threat

**Mitigation (preventive):**
- **Phase 1 paper-only** — no real money at all
- **Phase 2 onwards:** mandatory Risk Acknowledgment with electronic signature before live mode
- Demo / paper trading mandatory minimum 14 days before user can enable live mode
- **Hard DD circuit breaker** at user account level (20% configurable): auto-pause all strategies, email user
- Position size cap: user cannot risk > 2% per trade by default
- Minimum balance enforcement (e.g., $500 USD) to avoid penny-account blowups
- Clear, unfollowable-to-misread disclosure: this is software, not advice, you can lose everything

**Mitigation (corrective):**
- Incident response playbook for "user reports significant loss" — Zeus owns
- Public communications template prepared (Phase 2)
- Liability insurance (E&O / tech) procured before Phase 2 launch
- Refund policy clear (no refund for trading losses; pro-rata refund of subscription only)

**Owner:** Zeus (cross-cutting; product, legal, support)
**Review cadence:** monthly + on every user complaint

---

### R12 — Credential leak (broker API key, MT5 password)
**Category:** Security
**Probability:** LOW
**Impact:** CRITICAL

**Mitigation (preventive):**
- **No plaintext storage** anywhere. Envelope encryption with KMS (AWS KMS / GCP KMS / HashiCorp Vault)
- Per-user data key, rotated on credential update
- Application secrets in vault, not env files in repo
- Credentials never logged (Argus reviews all log statements)
- Mandatory secret scanning in CI (gitleaks)
- Annual credential rotation policy

**Mitigation (corrective):**
- Breach detection: monitor for unusual login patterns (Argus W4)
- Credential rotation playbook: emergency rotation < 1h
- Notification to user within 24h per Thai PDPA

**Owner:** Argus
**Review cadence:** weekly during Phase 1; quarterly after launch

---

### R13 — Deposit theft via account takeover / order injection
**Category:** Security
**Probability:** LOW
**Impact:** CRITICAL

**Mitigation (preventive):**
- **2FA mandatory** for live trading mode (TOTP)
- **Withdraw funds NOT possible from our platform** — only the broker can withdraw to the user's pre-registered bank account (this is the structural defense)
- Order direction validated against strategy rules (no rogue orders)
- IP allowlist option for power users
- Anomaly detection on order patterns (Argus + Themis)

**Mitigation (corrective):**
- Incident response: kill switch per user (instant strategy stop + revoke session)
- Coordinated disclosure with broker if attack pattern detected

**Owner:** Argus
**Review cadence:** weekly during Phase 1-2

---

### R14 — Exness ToS change disallowing third-party automation
**Category:** Business
**Probability:** LOW
**Impact:** HIGH

**Mitigation:**
- Read Exness ToS Day 1; document our compliance posture (Hestia W1)
- Maintain relationship with Exness IB / partnership team (Zeus, post-Phase 1)
- Backup broker integration in architecture (broker adapter pattern — Daedalus W2 ADR-004)
- Multi-broker support from Phase 3

**Owner:** Zeus
**Review cadence:** quarterly

---

### R15 — Payment processor refund chargebacks / bans
**Category:** Business
**Probability:** MEDIUM
**Impact:** MEDIUM

**Mitigation:**
- Clear refund policy at signup (no refund for trading; subscription refund pro-rata within 7 days)
- Stripe + Omise dual integration (failover)
- 7-day free trial to reduce buyer's regret refund pressure
- KYC light (email verification + 3DS) to reduce fraud chargeback
- Subscription, not one-time charges — easier dispute handling
- Reserve 5% of revenue for chargeback float

**Owner:** Zeus (Phase 2+)
**Review cadence:** monthly during Phase 2

---

## Aggregate View

**Critical / High score risks: 10 of 15**
**Top 3 to watch daily:**
1. **R05 Overfit** (Kairos)
2. **R11 User loss → lawsuit** (Zeus)
3. **R01/R02 MT5 VPS reliability** (Hestia)

## Risk Reporting

- Weekly: top 5 risks status in sponsor report
- Every retro: review register, retire closed risks, add new
- Any CRITICAL impact risk that moves to MEDIUM/HIGH probability → escalate to sponsor within 24h
- New risk found during sprint → log immediately, discussed at next standup

---

_— Zeus Ryujin, 2026-06-14_
