# Test Strategy — Forex Trading Bot SaaS

**Owner:** Themis Saori (QA)
**Updated:** 2026-06-14
**Status:** Approved baseline for Phase 1–3

---

## 1. Why this strategy exists

This is a SaaS that **moves real money on behalf of paying users**. A defect in production can:
- Wipe user accounts (margin call / runaway loss)
- Leak broker credentials → legal + regulatory blast
- Mis-charge users → chargeback / fraud claim
- Silently corrupt backtest → users trust false edge

There is no "small bug" once we go live. The strategy below is **risk-prioritized, not coverage-prioritized**.

---

## 2. Quality goals

| Goal | Metric | Target |
|---|---|---|
| Critical paths bug-free | Defect escape rate (P0/P1) | 0 per release |
| Unit coverage — trading-engine | Line + branch | ≥ 80% line / 70% branch |
| Unit coverage — backend | Line | ≥ 80% |
| Mutation score — trading-engine | mutmut | ≥ 70% on core (risk, strategies) |
| E2E happy paths | Pass rate | 100% green required to deploy |
| Flake rate | Per CI run | ≤ 1% over 30-day rolling |
| Mean time to detect P0 in prod | Sentry alert | < 5 min |
| WCAG 2.1 AA | axe + manual | 100% on public + auth pages |

Coverage % is **not the goal** — confidence in change is. Coverage is a floor, mutation is the ceiling check.

---

## 3. Risk-based priority register

Tested with descending priority. Block release on P0/P1 regression.

| # | Risk | Severity | Likelihood | Priority | Owner of mitigation |
|---|---|---|---|---|---|
| 1 | **Kill switch fails** → strategy keeps trading on disaster | Catastrophic | Medium | **P0** | Trading-engine + UI |
| 2 | **Broker credentials leaked** in logs / API response / git | Catastrophic | Medium | **P0** | Backend + Argus + CI |
| 3 | **Backtest dishonest** (look-ahead, survivorship, no slippage) | Catastrophic | High | **P0** | Quant (Kairos) + QA |
| 4 | **Billing incorrect** — double charge, no charge, wrong tier | High | Medium | **P0** | Stripe webhook tests |
| 5 | **Signal → order mismatch** — strategy says BUY 0.1, broker gets SELL 1.0 | Catastrophic | Low | **P0** | Trading-engine |
| 6 | **Position sizing / leverage wrong** — over-leveraged | Catastrophic | Medium | **P0** | RiskManager |
| 7 | **DD circuit breaker silent** | High | Medium | **P1** | RiskManager |
| 8 | **Auth bypass / IDOR** — user A reads user B's data | High | Medium | **P1** | Security + QA |
| 9 | **MT5 disconnect → orphaned order** | High | High | **P1** | Broker adapter |
| 10 | **Stripe webhook replay** | Medium | Medium | **P1** | Billing |
| 11 | **Rate limit bypass** | Medium | Medium | **P2** | Backend |
| 12 | **Dashboard slow** > 3s | Medium | Medium | **P2** | Frontend perf |
| 13 | **A11y blocker on kill switch** | High | Low | **P1** | UI |
| 14 | **Timezone drift in candle data** | High | Medium | **P1** | Trading-engine |
| 15 | **Dependency CVE in prod** | Medium | High | **P2** | CI dep scan |

---

## 4. Test pyramid (target ratio)

```
                 /\
                /e2\       ~5%   — 8 critical user journeys (Playwright)
               /----\
              / int  \     ~25%  — API contract, broker mock, DB
             /--------\
            /  unit    \   ~70%  — strategies, risk math, helpers, parsers
           /------------\
```

- **Unit-heavy on `trading-engine`** — strategies & risk math are pure functions → trivial to unit test → catastrophic if wrong → invert pyramid would be malpractice.
- **Integration on backend** — auth flow, broker_account CRUD, Stripe webhook signature, DB row level.
- **E2E on 8 happy paths only** — too brittle/expensive for breadth, but irreplaceable for "does the whole stack work."
- **Contract tests** between trading-engine ↔ backend via Pact (JSON event schema).
- **Mutation testing** quarterly on `trading-engine/strategies/` and `trading-engine/risk/` to catch silent assertion gaps.

---

## 5. Test types & owners

| Type | Tool | Where it runs | Owner |
|---|---|---|---|
| Unit (Python) | pytest + pytest-cov | CI on every PR | Author + QA review |
| Unit (TS/React) | Vitest + RTL | CI on every PR | Eos + QA review |
| Integration API | pytest + httpx + testcontainers (PG, Redis) | CI on every PR | Atlas + QA |
| Contract | Pact | Nightly | QA |
| E2E web | Playwright (chromium, webkit, firefox) | CI on PR + nightly full | QA |
| Performance | k6 | Manual + weekly | QA + Hestia |
| Security | OWASP ZAP, semgrep, trivy, gitleaks, bandit | CI on every PR + nightly | Argus + QA |
| Accessibility | axe-core + manual NVDA/VoiceOver | CI + per-sprint manual | QA |
| Mutation | mutmut | Quarterly on core | QA |
| Exploratory | Charter-based session | Per feature | QA + dev pair |
| Backtest validation | Custom harness (see backtest-validation.md) | Per strategy change | QA + Kairos |

---

## 6. Environments

| Env | Purpose | Data | Broker | Stripe | Refresh |
|---|---|---|---|---|---|
| **dev** | Local | Seeded synthetic | Mock | Test mode | On demand |
| **ci** | Pipeline | Ephemeral testcontainers | Mock | Test mode | Per job |
| **staging** | Pre-prod, full stack | Anonymized snapshot | Exness demo | Test mode | Nightly |
| **paper-prod** | Real broker, paper money | Real (limited users) | Exness demo / Binance testnet | Test mode | N/A |
| **prod** | Real money | Real | Exness live / Binance live | Live | N/A |

> Production smoke tests are **read-only** — never trigger real orders.

---

## 7. Definition of Done (per story)

A story is **Done** only when:
1. Acceptance criteria as Given/When/Then exist and are automated.
2. Unit tests added/updated, ≥ 80% coverage on touched modules.
3. If touches API: integration test added.
4. If touches UI critical path: E2E added.
5. If touches money / orders / risk: at least one mutation-survives test added.
6. No P0/P1 bug open against the story.
7. axe pass on touched pages.
8. PR security check green (semgrep, gitleaks, bandit).
9. Reviewed by Hephaestus + QA sign-off.

---

## 8. Definition of Ready for Release

See `release-checklist.md`. Summary: all P0/P1 bugs closed, full E2E green twice consecutively, performance baseline unchanged, security scan clean, backtest validation re-run on changed strategies, rollback plan documented.

---

## 9. Shift-left commitments

- QA joins **refinement** — convert AC to Given/When/Then before sprint start.
- QA pairs on **PR review** for critical modules (risk, broker, billing).
- QA owns **test data factory** so devs can write tests fast.
- QA writes the **first failing test** for new spec when possible.

---

## 10. Out of scope

- Penetration test of broker infrastructure (their problem).
- Chaos engineering on prod MT5 terminal in Phase 1 (deferred to Phase 3).
- Cross-tenant load testing > 1000 users (deferred to Phase 3 scale-out).

---

## 11. Tooling baseline

| Layer | Library | Version |
|---|---|---|
| Python test | pytest | 8.x |
| Coverage | pytest-cov | 5.x |
| Mocking | unittest.mock, freezegun, respx | latest |
| DB test | testcontainers-python | 4.x |
| TS test | Vitest | 2.x |
| React test | @testing-library/react | 16.x |
| E2E | Playwright | 1.45+ |
| Perf | k6 | 0.50+ |
| A11y | @axe-core/playwright | latest |
| Mutation | mutmut | 2.x |
| Contract | pact-python | 2.x |

---

## 12. Reporting

- **Per PR:** coverage delta, test count, E2E status, security scan.
- **Per sprint:** defect density, escape rate, flake rate, test runtime trend.
- **Per release:** release-checklist signoff, backtest validation report, performance baseline diff.
