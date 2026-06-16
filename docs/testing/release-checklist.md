# Release Checklist — Forex Trading Bot

**Owner:** Themis Saori (final QA sign-off)
**Updated:** 2026-06-14

This checklist gates every deploy to **prod**. Staging deploys use the shorter gate (items marked **[stg]**). All items here are pass/fail. Any "no" blocks release.

---

## 0. Pre-flight (24h before deploy)

- [ ] Release notes drafted (Zeus).
- [ ] Migration plan reviewed (Mnemosyne) — forward + rollback scripts attached.
- [ ] Feature flags toggles documented.
- [ ] On-call rota confirmed for next 24h.
- [ ] Rollback plan documented (1-pager): how to revert image tag, how to roll back DB, who decides.

---

## 1. Code & tests **[stg]**

- [ ] Main branch CI green twice consecutively (last 2 runs).
- [ ] Coverage: trading-engine ≥ 80% line, backend ≥ 80% line, frontend ≥ 75%.
- [ ] No P0 / P1 bugs open.
- [ ] All open P2 bugs triaged with target release.
- [ ] Mutation score on `trading-engine/risk/` ≥ 70% (if quarterly run is current).
- [ ] No `@pytest.mark.skip` / `it.skip` / `.only` outside of explicit allowlist.
- [ ] No `TODO(security)` left in touched files.

---

## 2. E2E **[stg]**

- [ ] All 8 E2E flows green on chromium **and** webkit on main commit.
- [ ] Kill switch E2E green on chromium + webkit + firefox (extra coverage on most critical flow).
- [ ] E2E flake rate ≤ 1% over last 30 days.

---

## 3. Backtest honesty (if any strategy or backtest code changed)

- [ ] Reproducibility test green.
- [ ] Look-ahead test green on all 6 strategies.
- [ ] Slippage realism asserts green.
- [ ] Walk-forward out-of-sample Sharpe ≥ 0.5 × in-sample on each strategy.
- [ ] Backtest report includes PF, Sharpe, Max DD, slippage row, walk-forward folds, data hash, commit SHA.
- [ ] Kairos + Themis + Hephaestus signoff filed in `docs/strategies/<name>/signoff.md`.

---

## 4. Trading safety

- [ ] **Kill switch E2E green** (chromium + webkit).
- [ ] **Kill switch unit test green** (`test_kill_switch.py`).
- [ ] RiskManager mutation score current.
- [ ] Position sizing math regression suite green.
- [ ] DD circuit breaker tested in staging with synthetic drawdown.
- [ ] Daily loss limit tested in staging.
- [ ] Order direction + size accuracy regression green (100 random signals → 100 correct orders in mock broker).
- [ ] MT5 reconnect on disconnect verified.
- [ ] Order idempotency (client_order_id) verified.

---

## 5. Billing

- [ ] All Stripe webhook test cases green (WB-01..09).
- [ ] Idempotency on replay verified.
- [ ] Subscription lifecycle E2E green (subscribe → cancel → re-subscribe).
- [ ] Failed payment / dunning flow tested in staging.
- [ ] No tier change can occur without an inserted `stripe_event` row.

---

## 6. Security **[stg]**

- [ ] `gitleaks` clean on main.
- [ ] `semgrep` clean on changed files.
- [ ] `bandit` (Python) clean.
- [ ] `pip-audit`, `npm audit` no HIGH+ unfixed.
- [ ] `trivy` image scan no HIGH+ unfixable.
- [ ] OWASP ZAP baseline on staging: 0 HIGH findings.
- [ ] IDOR test suite green.
- [ ] JWT integrity test suite green.
- [ ] Secrets-in-logs assertion green over full pytest run.
- [ ] Argus signoff filed.

---

## 7. Performance **[stg]**

- [ ] Latest k6 dashboard_steady scenario all thresholds green.
- [ ] p95 dashboard within 20% of last green release.
- [ ] No memory leak in 7-day soak (or last soak still current).
- [ ] DB slow-query log clean (no > 500ms queries on critical path).

---

## 8. Accessibility **[stg]**

- [ ] axe automated on all listed pages: 0 serious/critical.
- [ ] Kill switch manual a11y check: pass on NVDA + VoiceOver.
- [ ] Login + signup manual a11y: pass.

---

## 9. Observability **[stg]**

- [ ] Sentry receiving events from staging.
- [ ] Prometheus scrape healthy for all targets.
- [ ] Loki ingesting logs for all services.
- [ ] Alerts wired: kill switch invocation, broker disconnect, webhook failure, order placement failure, 5xx rate, p95 latency, DB connection saturation.
- [ ] Dashboards reviewed (Hestia + Themis).

---

## 10. Data & migration

- [ ] Forward migration applied to staging, app boots clean.
- [ ] Rollback migration applied to staging copy, app boots clean.
- [ ] Backup of prod DB taken < 2h before deploy.
- [ ] Backup restore tested in last 30 days.

---

## 11. Smoke tests after deploy

Run these within 5 min of prod deploy:

- [ ] GET `/healthz` 200 on all services.
- [ ] Login as canary user → 200.
- [ ] Strategy list loads.
- [ ] No new Sentry P0 errors in 5 min.
- [ ] Webhook ping test (Stripe send test event) → 200 + handled.

If any fail → rollback per pre-written plan.

---

## 12. Sign-offs

- [ ] Zeus (PM): release approved.
- [ ] Daedalus (Architect): no architecture concerns.
- [ ] Themis (QA): all items above are pass.
- [ ] Argus (Security): security gate cleared.
- [ ] Hestia (DevOps): infra ready, rollback ready.
- [ ] Hephaestus: final review done.

Release tag: `vX.Y.Z` created and signed.

---

## 13. Post-release

- [ ] Monitor dashboards + Sentry for 2 hours.
- [ ] Update `learning-log.md` with any incident or near-miss.
- [ ] Schedule retro within 7 days.
