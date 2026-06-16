# Performance Test Plan — k6

**Owner:** Themis Saori + Hestia Kaoru
**Tool:** k6 (with k6-reporter HTML, Grafana k6 cloud optional)
**Updated:** 2026-06-14

---

## 1. Why we perf-test

Trading is real-time. Slow dashboard = users panic-click. Slow webhook = Stripe retries. Slow strategy start = race conditions. We baseline now, watch trends.

---

## 2. SLO targets (Phase 1 → 3)

| Endpoint / page | Phase 1 (10 users) | Phase 2 (50 users) | Phase 3 (500 users) | p95 budget |
|---|---|---|---|---|
| GET /dashboard | < 1.5 s | < 1.5 s | < 2.0 s | hard cap 3 s |
| GET /api/strategy-instances | < 250 ms | < 300 ms | < 400 ms | hard 800 ms |
| POST /api/auth/login | < 400 ms | < 500 ms | < 700 ms | hard 1.5 s |
| POST /api/backtests | < 500 ms (job enqueue only) | same | same | hard 1 s |
| POST /webhooks/stripe | < 200 ms | < 250 ms | < 300 ms | hard 500 ms |
| WS /api/stream (trade events) | < 100 ms event→client | < 150 ms | < 250 ms | hard 500 ms |

Error rate budget: < 0.1% over the test.

---

## 3. Scenarios

### 3.1 `k6/scenarios/dashboard_steady.js`
100 VUs, ramp up 2 min, hold 10 min, ramp down 2 min.
Each VU: login once, then loop GET /dashboard + GET /api/strategy-instances every 5s.

### 3.2 `k6/scenarios/backtest_burst.js`
Burst of 50 backtest job enqueues in 30s. Rate-limited at 10/min/user — test that 429 returns properly and that legit users beneath limit are unaffected.

### 3.3 `k6/scenarios/auth_spike.js`
Auth-only: 200 VUs login concurrently. Check JWT issue latency + Redis session writes.

### 3.4 `k6/scenarios/webhook_chaos.js`
500 Stripe-shaped webhook posts/sec for 1 min, with deliberate duplicates (10%) and out-of-order (5%). Verify all converge to correct user.tier state.

### 3.5 `k6/scenarios/ws_fanout.js`
100 WS clients subscribed to their own trade stream. Engine emits 50 trades/sec total. Measure event-to-client latency.

### 3.6 `k6/scenarios/soak_paper.js` (manual, weekly)
10 paper strategies running for 7 days. Track memory + connection pool + Redis keys over time. Watchdog kills on >2GB RSS or > 5000 open connections.

---

## 4. Thresholds in code

```js
export const options = {
  scenarios: { /* … */ },
  thresholds: {
    'http_req_duration{name:dashboard}': ['p(95)<1500'],
    'http_req_duration{name:login}':     ['p(95)<400'],
    'http_req_failed':                   ['rate<0.001'],
    'checks':                            ['rate>0.999'],
  },
};
```

k6 exits non-zero if any threshold breached → CI marks build failed.

---

## 5. Data setup

- Seeded DB with 1000 users, 500 broker accounts, 200 strategy instances, 50k trades.
- Stripe in test mode, mocked at gateway for webhook scenarios.
- MT5 broker mock at `broker-mock:8080`.

---

## 6. What we measure & report

- p50 / p95 / p99 per endpoint.
- Error rate per endpoint.
- Throughput.
- CPU + mem per service (Grafana panel).
- DB: connection pool saturation, slow query log.
- Redis: ops/sec, mem.

Report stored under `docs/testing/perf-reports/YYYY-MM-DD-<scenario>.md` with baseline diff.

---

## 7. Cadence

| Cadence | What |
|---|---|
| On PR touching backend critical path | dashboard_steady + auth_spike (smaller, 5 min) |
| Nightly | full suite except soak |
| Weekly | soak_paper |
| Pre-release | full suite + soak + baseline comparison |

---

## 8. Acceptance for release

- All thresholds green.
- p95 dashboard within 20% of last release baseline (else investigate before deploy).
- No memory leak over 7-day soak.
