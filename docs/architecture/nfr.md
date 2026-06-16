# Non-Functional Requirements (NFR)

> Architect: Daedalus Souta
> Version: 1.0
> Date: 2026-06-14
> Status: Draft (Phase 1 target; will refine per phase)

---

## Purpose

ระบุ **measurable** quality attribute ของระบบ เพื่อให้ทุกทีม design + test ต่อเป้าหมายเดียวกัน NFR ไม่ใช่ wishlist — ทุกตัวต้องมี **how to measure** และ **what we won't promise**

---

## 1. Performance

| ID | Metric | Target (Phase 1–2) | Measurement | Why |
|----|--------|--------------------|---------------:|-----|
| P-1 | API p50 latency | < 100 ms | Prometheus histogram on `/metrics`; bucketize per route | UX feel of "instant" |
| P-2 | API p95 latency | **< 300 ms** | Same | Catches slow path |
| P-3 | API p99 latency | < 800 ms | Same | Tail latency monitor |
| P-4 | Signal → Order acknowledged | **< 2 s** end-to-end | distributed trace: scheduler_tick → MT5 result | Trading edge depends on it |
| P-5 | Backtest UI return | **≤ 30 s** for 3-year M5 window | timer in backtest module | UX promise |
| P-6 | Dashboard initial paint (TTI) | < 2.5 s on 4G | Lighthouse + RUM | Web vital |
| P-7 | WebSocket / SSE message lag | < 500 ms (server → client) | server log timestamp vs client ack | Live ticker UX |

**Scope:** measured from EU egress; TH users may add ~150ms RTT.
**Excludes:** 3rd-party slowness (Stripe webhook delay, broker downtime).

---

## 2. Throughput / Capacity

| ID | Metric | Target | Measurement |
|----|--------|--------|-------------|
| T-1 | Concurrent active users (Phase 1) | 50 | session count |
| T-2 | Concurrent users (Phase 2 MVP) | **100** | session count |
| T-3 | Concurrent users (Phase 3) | 500 | session count |
| T-4 | API RPS (Phase 2) | 50 RPS sustained, 200 RPS burst (10s) | k6 load test |
| T-5 | Backtest jobs / hour | 60 per worker (avg 1/min) | queue depth + completion rate |
| T-6 | Concurrent MT5 terminals / Windows VPS | 50 | Bridge metric |
| T-7 | Live strategy ticks / sec | 100 evaluations/sec across all users | Trading Engine metric |

**Load test gate:** ก่อน Phase 2 launch ต้องผ่าน k6 scenario 100 VU × 10 min ที่ <300ms p95.

---

## 3. Availability

| ID | Metric | Target | Notes |
|----|--------|--------|-------|
| A-1 | App plane uptime | **99.5%** (= ~3.6h downtime/mo) | Single VPS realistic ceiling |
| A-2 | Trading plane uptime | 99.5% | Constrained by Exness MT5 availability |
| A-3 | Stripe webhook processing | 99.9% (eventual, with retry) | Webhook idempotent |
| A-4 | Scheduled maintenance window | Mon 03:00–04:00 UTC (off-market) | Pre-announced |

**Not promised:**
- 24/7 immediate human response (Phase 1–2: best-effort, on-call Mon-Fri biz hours)
- Multi-region failover

**Measured via:** UptimeRobot external prober (1-min interval) + internal `/healthz`.

---

## 4. Reliability / Resilience

| ID | Metric | Target |
|----|--------|--------|
| R-1 | RPO (data loss tolerance) | **1 hour** (WAL archive every 5min, hourly snapshot) |
| R-2 | RTO (restore time) | **4 hours** (provision + restore) |
| R-3 | Quarterly DR drill | mandatory, runbook updated |
| R-4 | Postgres backup retention | 30 daily + 12 weekly + 12 monthly |
| R-5 | Idempotent order placement | 100% (idempotency_key on every order) |
| R-6 | Webhook retry budget | 3 attempts, exp backoff up to 24h |
| R-7 | Strategy daily max-orders cap | configurable, default 50/strategy/day |
| R-8 | Drawdown circuit breaker | auto-disable strategy at user-set DD limit |

---

## 5. Security

(See `docs/security/threat-model.md` — Argus owns. Key NFR below.)

| ID | Requirement |
|----|-------------|
| S-1 | TLS 1.3 on all public endpoints; mTLS internal (bridge) |
| S-2 | Password: Argon2id (m=64MB, t=3, p=4); min 12 chars |
| S-3 | 2FA mandatory for: change broker cred, enable live strategy, withdraw-related |
| S-4 | Broker credential encrypted at rest (ADR-005) |
| S-5 | Audit log immutable, 1-year retention |
| S-6 | OWASP Top 10 — pen-test before Phase 2 launch |
| S-7 | Rate limit: 60 req/min/user general, 5/min for sensitive |
| S-8 | Secret rotation: KEK quarterly, JWT secret yearly |
| S-9 | Dependency scan: weekly (Dependabot + pip-audit) |

---

## 6. Maintainability

| ID | Metric | Target |
|----|--------|--------|
| M-1 | Backend test coverage | > 80% line, > 70% branch |
| M-2 | Frontend type coverage | 100% (strict TS, no `any` without comment) |
| M-3 | CI feedback time (PR check) | < 8 min for unit; < 15 min full |
| M-4 | Mean time to recovery (MTTR) | < 1 hour for known issue |
| M-5 | Deploy frequency | daily-capable; actual rate depends on backlog |
| M-6 | Change failure rate | < 15% (DORA Elite target = 5%) |
| M-7 | Documentation freshness | ADR + architecture doc reviewed quarterly |

**DORA metrics tracked from Phase 2.**

---

## 7. Observability

| ID | Requirement |
|----|-------------|
| O-1 | Every request has correlation ID (frontend → backend → bridge) |
| O-2 | Structured JSON logs (no plaintext password — filter at logger) |
| O-3 | Per-route latency histogram exported to Prometheus |
| O-4 | Business KPI dashboard: active users, daily PnL, signals/day, error rate |
| O-5 | Alert: p95 > 500ms for 5 min → Discord on-call |
| O-6 | Alert: error rate > 2% for 5 min → page on-call |
| O-7 | Trace sampling: 100% for orders, 10% for general API |

---

## 8. Cost

| ID | Metric | Target (Phase 1–2) |
|----|--------|--------------------|
| C-1 | Infra cost | **< $50/mo** |
| C-2 | Cost per active user | < $2/mo (excluding payment fees) |
| C-3 | Backup storage | < $3/mo |

(Detail: ADR-004 cost projection)

---

## 9. Usability (selected, full set in design/)

| ID | Requirement |
|----|-------------|
| U-1 | Dashboard first meaningful paint < 2s |
| U-2 | Backtest result visible (skeleton) immediately, full result < 30s |
| U-3 | Mobile responsive (≥ 375px width) |
| U-4 | WCAG AA accessibility (Iris owns) |
| U-5 | Thai + English UI (i18n from Day 1) |

---

## 10. Compliance / Legal

| ID | Requirement | Note |
|----|-------------|------|
| L-1 | PDPA (Thailand) | DSAR endpoint by Phase 2 |
| L-2 | GDPR (EU users) | data deletion within 30 days |
| L-3 | Stripe ToS | comply with restricted business policy |
| L-4 | No financial advice claim | UI disclaimer everywhere |
| L-5 | Risk disclosure | mandatory on signup |

**Not in scope (Phase 1–2):**
- MAS / SEC / FCA licensing — กฎหมายฉบับเฉพาะของ jurisdiction ไม่ใช่ scope SaaS infra
- AML/KYC (กว้างกว่า identity verify) — Phase 3 evaluation

---

## 11. Portability

| ID | Requirement |
|----|-------------|
| Po-1 | Backend runs on Linux only (Ubuntu 22.04/24.04) |
| Po-2 | Trading Bridge runs on Windows Server 2022 only |
| Po-3 | Docker images: linux/amd64 (no arm needed in infra plan) |
| Po-4 | Dev: macOS / Linux / Windows + WSL2 |

---

## NFR Verification Plan

| NFR group | Verification Method | When |
|-----------|---------------------|------|
| Performance | k6 load test scenarios in `infra/load-tests/` | every release |
| Availability | UptimeRobot rolling 30d report | monthly |
| Reliability | DR drill | quarterly |
| Security | pen-test + Trivy scan | before Phase 2 launch + quarterly |
| Maintainability | DORA dashboard | weekly review |
| Cost | infra invoice + Grafana cost panel | monthly |

---

## Changelog
- **2026-06-14** — initial draft (Daedalus)
