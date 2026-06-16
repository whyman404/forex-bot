# Roadmap — Forex/Crypto Trading Bot Platform

**Owner:** Zeus Ryujin
**Date:** 2026-06-14
**Phase 1 Start:** Monday 2026-06-15
**Phase 1 End:** Sunday 2026-07-26 (6 weeks)
**Cadence:** 1-week sprints (Mon → Sun), demo Friday, retro Sunday async

---

## Milestones at a glance

| ID | Milestone | Date | Definition of Done |
|----|-----------|------|---------------------|
| **M1** | **Design Freeze** | End W2 (Sun 2026-06-28) | All ADRs signed, schema v1, API contract v1, UI wireframe v1, strategy specs v1 |
| **M2** | **Backtest Passes** | End W4 (Sun 2026-07-12) | ≥ 4 of 6 strategies hit PF>1.5 / MaxDD≤20% / Sharpe>1.0 on 3yr OOS |
| **M3** | **Paper Trading Running** | End W6 (Sun 2026-07-26) | Paper trading 7 consecutive days, zero P1, dashboard live |

Each milestone is a **GATE** — if not met, escalate to sponsor with options (pivot / extend / descope) within 24h.

---

## Phase 1 — Foundation (6 weeks, 2026-06-15 → 2026-07-26)

### Sprint 1 (W1) — Mon 2026-06-15 → Sun 2026-06-21
**Sprint Goal:** Lock the foundation. Everyone aligned on architecture, schema, UI direction, strategy specs.

| Agent | Deliverable (week) |
|-------|---------------------|
| **Zeus** | Charter signed-off (this doc), risk register live, comms plan running, kick-off async |
| **Daedalus** | ADR-001 (modular monolith vs microservices) decided; ADR-002 (Windows VPS for MT5, Linux for rest); ADR-003 (Python tech stack); high-level architecture diagram v1 |
| **Iris** | Information architecture, user journey map, low-fi wireframe for dashboard + strategy config + backtest report |
| **Mnemosyne** | ERD v1 (users, strategies, accounts, positions, trades, backtests, jobs), naming convention, migration tooling chosen |
| **Atlas** | FastAPI project scaffold, dependency injection pattern, error envelope schema, auth stub |
| **Eos** | Next.js 15 scaffold, design tokens from Iris, route map, auth UI stub |
| **Kairos** | Strategy spec v1 for ALL 6 strategies (entry / exit / SL / TP / position sizing / params), data sourcing plan, backtest framework selected (vectorbt + backtrader hybrid) |
| **Hestia** | dev docker-compose (Postgres + Redis + backend + frontend), Windows VPS spec + provisioning script draft, GitHub Actions CI skeleton |
| **Themis** | Test strategy doc, pyramid plan, acceptance criteria template, coverage targets (unit 80%, integration 60%) |
| **Argus** | Threat model v1 (STRIDE), security baseline checklist, credential handling policy (no plaintext, KMS or vault) |
| **Hephaestus** | Review ADR-001/002/003, mentor on monolith-first decision |

**Demo (Fri 2026-06-19):** Daedalus presents architecture; Iris shows wireframe; Kairos walks through one strategy spec end-to-end.

---

### Sprint 2 (W2) — Mon 2026-06-22 → Sun 2026-06-28 — **MILESTONE M1**
**Sprint Goal:** Design freeze. Everything in spec, ready to build at speed.

| Agent | Deliverable |
|-------|-------------|
| **Zeus** | Sprint 1 retro, M1 readiness review, dependency graph for W3–W6 |
| **Daedalus** | ADR-004 (broker adapter pattern), ADR-005 (event sourcing for trades), final architecture doc, sequence diagrams for order placement |
| **Iris** | Hi-fi mockup for dashboard, equity curve view, design system v1 in Figma + Tailwind tokens exported |
| **Mnemosyne** | Schema v1 final (with indexes), migration set 001-005, seed script |
| **Atlas** | OpenAPI spec v1 (auth, strategy CRUD, backtest job, trade history), pagination + error convention finalized |
| **Eos** | Component library scaffold (shadcn/ui + Tailwind), dashboard shell, layout |
| **Kairos** | Strategy spec v1 ratified by Daedalus + Hephaestus; data ingestion pipeline (Dukascopy / Exness history) running; first vectorbt notebook for London Breakout |
| **Hestia** | Windows VPS provisioned + MT5 installed + Python pkg verified; backend Linux VPS provisioned; secrets management (1Password / Vault) decided |
| **Themis** | Acceptance test template per strategy, pytest fixtures, CI test runner working |
| **Argus** | Secrets handling review, threat model signed by Daedalus, security checklist for backend baseline |
| **Hephaestus** | Code review of FastAPI scaffold + Next.js scaffold; coaching session on async patterns |

**M1 Gate Review (Sun 2026-06-28):** Zeus runs go/no-go on all design artifacts. If any missing → block W3 until resolved.

**Demo (Fri 2026-06-26):** End-to-end design walkthrough: Iris → wireframe; Daedalus → architecture; Mnemosyne → schema; Atlas → API spec; Kairos → strategy.

---

### Sprint 3 (W3) — Mon 2026-06-29 → Sun 2026-07-05
**Sprint Goal:** Build the engine. First strategy runs end-to-end in backtest.

| Agent | Deliverable |
|-------|-------------|
| **Zeus** | Daily risk check, M2 dependency tracking, escalation if Kairos blocked |
| **Daedalus** | Code review on engine modules; refactor guidance |
| **Iris** | Backtest report visualization design, equity curve component spec |
| **Mnemosyne** | Migrations applied to staging; query optimization for trade history |
| **Atlas** | Auth (register/login/JWT), strategy CRUD endpoints, backtest job submission endpoint, job status endpoint |
| **Eos** | Login + register pages, dashboard skeleton with mock data, strategy list page |
| **Kairos** | **Backtest framework working** + **London Breakout** + **NY Killzone Reversal** running with 3yr Gold tick data; report includes PF, Sharpe, MaxDD, winrate, RR, expectancy |
| **Hestia** | Redis queue (RQ or Celery) for backtest jobs; basic Sentry + Grafana wired |
| **Themis** | Unit tests for OMS position sizing, SL/TP logic; integration test for backtest job pipeline |
| **Argus** | Pen-test on auth endpoints; rate limit baseline |
| **Hephaestus** | Pair session with Kairos on backtest pitfalls (lookahead bias, survivorship) |

**Demo (Fri 2026-07-03):** Submit backtest job from UI → see report with PF/Sharpe/DD numbers.

---

### Sprint 4 (W4) — Mon 2026-07-06 → Sun 2026-07-12 — **MILESTONE M2**
**Sprint Goal:** All 6 strategies pass backtest gate, OOS validated.

| Agent | Deliverable |
|-------|-------------|
| **Zeus** | M2 gate review prep, contingency plan if 2+ strategies fail |
| **Daedalus** | Broker adapter interface finalized (MT5 + Binance); review concurrency model for live |
| **Iris** | Strategy config UI design, parameter form patterns |
| **Mnemosyne** | Performance tuning for backtest result storage; partitioning for trade table |
| **Atlas** | Strategy config persistence, backtest job orchestration, results endpoint with filters |
| **Eos** | Backtest report viewer page (equity curve, drawdown chart, trade list, metrics card), strategy config form |
| **Kairos** | **Remaining 4 strategies live:** EMA50+ADX, EMA Cross+RSI, Donchian Breakout, Grid Bot (with SL); walk-forward analysis tool; OOS validation report for all 6 |
| **Hestia** | MT5 connection from Windows VPS verified with demo account; heartbeat monitoring |
| **Themis** | Acceptance tests for backtest metrics correctness (compare against known fixture); regression suite |
| **Argus** | Encryption at rest for broker creds (envelope encryption with KMS); audit log baseline |
| **Hephaestus** | Architecture review on broker adapter, code review on OMS |

**M2 Gate Review (Sun 2026-07-12):** Zeus + Kairos + Themis review. Pass criteria: ≥ 4 of 6 strategies meet PF>1.5, MaxDD≤20%, Sharpe>1.0 on 3yr OOS.
- If 4-6 pass → proceed to W5
- If 2-3 pass → +1 week buffer, descope weakest strategy
- If 0-1 pass → trigger **K1 kill criterion** → sponsor decision

**Demo (Fri 2026-07-10):** Run backtest of all 6 strategies live in demo, show OOS dashboard.

---

### Sprint 5 (W5) — Mon 2026-07-13 → Sun 2026-07-19
**Sprint Goal:** Wire paper trading. Strategy → MT5 demo account loop closes.

| Agent | Deliverable |
|-------|-------------|
| **Zeus** | M3 risk tracking, paper trading SLO definition |
| **Daedalus** | Event flow review for live mode; idempotency design for order placement |
| **Iris** | Live dashboard polish — open positions, real-time P&L card, alert toast pattern |
| **Mnemosyne** | Event store for live trades, position state machine schema |
| **Atlas** | Paper trading orchestration service (start / stop / pause strategy), webhook receiver from MT5 events, position state API |
| **Eos** | Live dashboard (open positions table, equity curve realtime via SSE, alert center), strategy start/stop controls |
| **Kairos** | **Paper trading loop**: strategy → signal → OMS → MT5 demo order; logging every decision with reason code |
| **Hestia** | Windows VPS production setup with auto-restart for MT5 terminal; Prometheus exporter for MT5 health; backup VPS standby plan |
| **Themis** | End-to-end test: signal → order placed → fill received → position recorded → dashboard updated; chaos test (kill MT5, kill backend) |
| **Argus** | Threat model update for live trading flow; broker credential rotation procedure |
| **Hephaestus** | Live code review session on OMS + broker adapter |

**Demo (Fri 2026-07-17):** Open paper trading session, place a real order through London Breakout signal on demo Exness, see it on dashboard.

---

### Sprint 6 (W6) — Mon 2026-07-20 → Sun 2026-07-26 — **MILESTONE M3**
**Sprint Goal:** 7 consecutive days of paper trading, zero P1, polish.

| Agent | Deliverable |
|-------|-------------|
| **Zeus** | M3 gate review, Phase 1 retro, Phase 2 kickoff prep |
| **Daedalus** | Phase 2 architecture proposal (live trading, billing), tech debt log |
| **Iris** | UX polish from feedback, accessibility audit (WCAG AA) |
| **Mnemosyne** | Backup procedure tested, restore drill, data retention policy |
| **Atlas** | Disclaimer + Risk Acknowledgment flow, audit log endpoint, observability endpoints |
| **Eos** | Risk Ack modal, ToS / Privacy pages, settings page polish |
| **Kairos** | **7-day paper trading run** monitored, daily report, parameter tuning log, edge decay watch |
| **Hestia** | Runbook for ops (restart MT5, rotate creds, deploy hotfix), alerts wired to email |
| **Themis** | Phase 1 acceptance test pack signed off, test coverage report, perf baseline |
| **Argus** | Phase 1 security sign-off, pen-test summary, no critical findings |
| **Hephaestus** | Final code review pass, tech debt prioritization |

**M3 Gate Review (Sun 2026-07-26):** Phase 1 DoD checklist (see charter §11). If green → Phase 1 closed. If red → 1-week buffer + sponsor brief.

**Demo (Fri 2026-07-24):** Full demo to sponsor — live paper trading 5+ days running, dashboard, backtest, risk flow.

---

## Phase 1 Dependency Graph (critical path)

```
Charter → Strategy Specs → Backtest framework → Backtest data → All 6 strategies ──┐
   │            │                                                                    │
   │            └──→ Schema → Backend endpoints ──→ Frontend wires ──┐               │
   │                                                                  │               │
   └─→ Architecture → Infra (Win VPS + Linux VPS) → MT5 connection ──┴───→ Paper Trading → M3
```

**Critical path = Charter → Strategy Specs → Backtest framework → 6 strategies passing → MT5 integration → Paper trading**

Zeus monitors this path daily. Any slip > 1 day on critical path triggers escalation.

---

## Phase 2 — MVP (4 weeks, tentative 2026-07-27 → 2026-08-23)

**High-level goals:**
- W7-8: **Live trading** with small real account, hard DD circuit breaker, kill switch
- W7-8: **Stripe + Omise billing** (subscription tiers: Free trial, Starter, Pro), customer portal
- W8-9: **Monitoring + alerting** mature (Grafana dashboards, PagerDuty / Discord webhooks)
- W9-10: **Closed beta** with 5-10 invited users, NPS survey, churn instrumentation
- W10: **Legal review** completed (ToS, AML/KYC posture, Thai SEC consultation if needed)

**Phase 2 Exit Criteria:**
- 5+ beta users live trading with real money, no funds lost beyond DD budget
- MRR generation possible (paywall live)
- < 1% P1 incident rate, MTTR < 1h

---

## Phase 3 — Scale (8 weeks, tentative 2026-08-24 → 2026-10-18)

**High-level goals:**
- Multi-tenant hardening (rate limit per user, resource quota)
- Performance: support 100 concurrent strategies running
- Marketing site, content (blog, YouTube), referral program
- Thai + English UI, payment localization
- Mobile-responsive deep polish
- Tier pricing optimization
- Public launch (controlled — landing page → waitlist → batched invites)

**Phase 3 Exit Criteria:**
- 500 paid subscribers
- MRR $25K
- Churn < 8%
- Operational maturity: SLO 99.5%, P1 < 4h MTTR

---

## Phase 4 — Optimize (continuous, 2026-10+)

- Strategy R&D pipeline (Kairos owns), edge decay monitoring
- ML / regime detection layer
- Additional brokers (OANDA, IC Markets, IBKR)
- API for power users
- Copy trading / social layer
- Strategy marketplace (vetted creators)
- Tax export, regulatory reports per jurisdiction

---

## Summary Gantt (Phase 1)

```
Week        : W1   W2   W3   W4   W5   W6
Dates       : 6/15 6/22 6/29 7/06 7/13 7/20
              ----.----.----.----.----.----
Charter     : ████
Architecture: ████ ███
UX Design   : ████ ███
DB Schema   : ████ ███
Backend API : ███  ██████████
Frontend    :      █████ ██████ ████
Strategy    : ████ ████ ██████████
Backtest    :      ███  ██████████
Infra (VPS) : ███  ███  ███  ████ ███
MT5 wire    :                ███  ████
Paper trade :                     ███  █████
QA / Test   :      ████ █████ █████ ████ ████
Security    :      ████ ███   ████      ████
              ----.----.----.----.----.----
Milestone   :      M1        M2        M3
```

**Critical path agents per week:**
- W1: Daedalus, Kairos
- W2: Daedalus, Kairos, Mnemosyne
- W3: Kairos, Atlas
- W4: Kairos (M2 blocker)
- W5: Kairos, Hestia, Atlas
- W6: Hestia, Themis (M3 gate)

---

_— Zeus Ryujin, 2026-06-14_
_Roadmap is a living document. Updated end of every sprint._
