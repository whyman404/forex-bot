# Test Plan — Forex Trading Bot SaaS

**Owner:** Themis Saori
**Aligned with:** Zeus roadmap (Phase 1 / 2 / 3)
**Updated:** 2026-06-14

---

## 1. Scope

In scope: backend API, trading-engine (strategies + risk + broker adapter), frontend web app, Stripe billing, MT5 + Binance integration via mock/demo, accessibility, security collaboration with Argus, performance.

Out of scope: mobile native app (Phase 4), broker internal systems, third-party Stripe internals.

---

## 2. Phase 1 — Foundation (6 weeks)

**Goal:** backtest + paper trading of 6 strategies working end-to-end on staging.

### Sprint 1 (week 1–2): scaffolding
- Set up pytest + Vitest + Playwright + CI gates.
- Build test data factory for OHLCV fixtures (Gold + BTC, 1m / 5m / 1h / 1d, known patterns).
- Write smoke E2E: signup → login → empty dashboard.
- **Exit:** CI green, factory documented, smoke E2E in nightly.

### Sprint 2 (week 3–4): strategies + risk
- Unit tests for all 6 strategies on canned fixtures (signal: yes/no, side, SL/TP levels).
- Unit tests for RiskManager (position sizing, DD breaker, daily limit).
- Backtest validation harness (reproducibility + look-ahead + slippage realism).
- **Exit:** ≥ 80% coverage on `trading-engine/strategies/` and `trading-engine/risk/`; backtest validation report on 6 strategies green.

### Sprint 3 (week 5–6): paper trading + broker adapter
- Integration tests for MT5 adapter mock (connect, place_order, partial fill, disconnect→reconnect).
- E2E: start paper strategy → see signal → kill switch.
- Performance baseline on dashboard.
- **Exit:** kill switch verified, paper E2E green, dashboard p95 < 1.5s on 10 users.

---

## 3. Phase 2 — MVP (4 weeks)

**Goal:** live trading on small account, membership/billing live, monitoring.

### Sprint 4 (week 7–8): billing
- Stripe webhook unit + integration tests (signature verify, idempotency, replay).
- Billing E2E: checkout test mode → unlock → cancel → re-subscribe.
- Edge cases: failed payment, dunning, plan downgrade.
- **Exit:** billing flows all green; webhook chaos test (out-of-order events) passes.

### Sprint 5 (week 9–10): live broker
- Live broker adapter against Exness demo first.
- Order accuracy regression (signal direction, size, SL/TP all preserved).
- Reconnect on disconnect verified.
- Security pass with Argus on credential handling (no secrets in logs).
- **Exit:** small-account live trading on Exness demo for 1 week with zero order-mismatch defect.

---

## 4. Phase 3 — Scale (8 weeks)

**Goal:** multi-user load, public launch readiness.

- Performance: 100 → 500 concurrent users on dashboard.
- Soak test: paper trading 1 week continuous, no memory leak.
- Full a11y audit (manual + axe) on all public pages.
- Penetration-style E2E from Argus.
- Disaster recovery drill (restore from backup, kill switch under DB outage).
- **Exit:** see `release-checklist.md`.

---

## 5. Environments per phase

| Phase | Used | Data | Broker | Stripe |
|---|---|---|---|---|
| 1 | dev, ci, staging | Synthetic fixtures | Mock + Exness demo | Test mode |
| 2 | + paper-prod | Synthetic + 1 internal real account | Exness demo, Binance testnet | Test mode |
| 3 | + prod | Real | Exness live (gated) | Live |

---

## 6. Roles

| Person | Responsibility |
|---|---|
| Themis (QA) | Test strategy, automation, exploratory, release signoff |
| Kairos (Quant) | Backtest correctness (paired with QA on validation harness) |
| Atlas (Backend) | Unit + integration tests for backend modules they own |
| Eos (Frontend) | Unit + RTL tests for components |
| Argus (Security) | Security tests, threat-driven test cases |
| Hestia (DevOps) | CI infra, perf test infra, environment parity |
| Hephaestus | Reviewer / final gate |

QA does not write 100% of the tests — QA owns the **strategy, infra, and gating**.

---

## 7. Exit criteria per sprint

Each sprint's exit gate is **explicit** above. No gate slip without PM (Zeus) signoff + risk acknowledgment recorded in the sprint retro.

---

## 8. Risk-based slicing

If sprint is at risk, the slice priority is:
1. Cut breadth (fewer strategies tested) — never cut depth on critical paths (kill switch, billing).
2. Cut E2E breadth — never cut E2E for kill switch + signal accuracy.
3. Cut a11y manual — never cut a11y on kill switch + login.
4. Cut perf breadth — never cut perf baseline measurement.

---

## 9. Defect management

- Tracker: GitHub Issues with labels `sev:P0..P3`, `area:trading|backend|web|billing|security|a11y|perf`.
- SLA: P0 fix < 24h, P1 < 3d, P2 < 1 sprint, P3 backlog.
- All P0 require post-mortem.
- Bug template: `bug-report-template.md`.

---

## 10. Reporting cadence

- Daily standup: blockers + new P0/P1.
- Weekly: defect density, flake rate, coverage trend posted to team channel.
- End-of-sprint: test execution report + exit criteria status.
- End-of-phase: phase QA report to Zeus.
