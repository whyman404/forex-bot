# SLOs — Forex Bot

> Owner: Hestia Kaoru — DevOps / SRE
> Last updated: 2026-06-14
> Review cadence: monthly during Phase 1, weekly during Phase 2

> SLO = the line above which the service is "fine enough" for users.
> Below = we stop ship new features and fix reliability instead.

---

## Why these SLOs

A trading bot has two faces:

1. **A SaaS web app** — login, manage strategies, view dashboards.
   Standard SaaS bar.
2. **A real-time order router** — latency from "signal" to "order at
   broker" decides whether a strategy makes or loses money.

I deliberately picked numbers we can hit on a $50/mo footprint while
still being honest with paying users. Tighter SLOs in Phase 3 once we
have the headroom.

---

## SLO catalogue

| # | SLO | Target | Window | Why |
|---|-----|--------|--------|-----|
| 1 | API availability | **99.5%** | 30 days | Acceptable for $50/mo single-VPS setup |
| 2 | API latency (p95) | **≤ 500 ms** | 30 days | Pages still feel snappy |
| 3 | Signal-to-order latency (p95) | **≤ 2.0 s** | 30 days | Strategies tolerate 2s slippage; >2s degrades edge |
| 4 | Backtest job success ratio | **≥ 99%** | 30 days | Most backtest failures = code bugs, not infra |
| 5 | MT5 supervisor uptime | **≥ 99%** | 30 days | Cannot trade if it's down; daily losses if SLO breached |
| 6 | Daily backup success | **100%** | 7 days | If backup fails 1 day we accept; 2 days = page |

Error budgets are derived from the SLO. SLO 1 (99.5%) gives **219 minutes
of error budget per 30 days**.

---

## SLI definitions

Numbers in this section feed both Grafana SLO panels and the alert
rules in `infra/prometheus/rules/slo-alerts.yml`.

### SLO 1 — API availability

```promql
# Good events: non-5xx responses to user-facing /api/* routes
good = sum(rate(http_requests_total{service="backend",route=~"/api/.*",status!~"5.."}[window]))

# Valid events: total /api/* requests
valid = sum(rate(http_requests_total{service="backend",route=~"/api/.*"}[window]))

availability = good / valid
```

Excludes:
* `/healthz`, `/readyz`, `/metrics` (operator routes)
* requests originating from monitoring exporters (label `synthetic=true`)

### SLO 2 — API latency p95

```promql
sli:api_latency:p95_5m =
  histogram_quantile(0.95,
    sum by (le) (rate(http_request_duration_seconds_bucket{service="backend",route=~"/api/.*"}[5m]))
  )
```

Budget: 5% of requests above 500 ms over 30 days.

### SLO 3 — Signal-to-order latency p95

We record a Prometheus histogram in the backend's order_router when an
order intent is published, and again when the corresponding fill comes
back from the MT5 supervisor. The difference is sampled at p95.

```promql
sli:signal_to_order:p95_5m =
  histogram_quantile(0.95,
    sum by (le) (rate(signal_to_order_latency_seconds_bucket[5m]))
  )
```

Budget: 5% of orders above 2.0 s over 30 days.

### SLO 4 — Backtest job success

```promql
1 - (
  sum(rate(backtest_jobs_total{result="error"}[30d]))
  /
  sum(rate(backtest_jobs_total[30d]))
)
```

### SLO 5 — MT5 supervisor uptime

```promql
avg_over_time(up{service="mt5-supervisor"}[30d])
```

### SLO 6 — Daily backup

A cron emits `pg_backup_last_success_timestamp_seconds`. If it is older
than 26 h we count the previous day as failed.

---

## Burn-rate alerting (multi-window, multi-burn-rate)

From the SRE Workbook (chapter 5). Two-tier policy:

| Tier | Burn rate | Long window | Short window | Severity | Reaction |
|------|-----------|-------------|--------------|----------|----------|
| Fast | 14.4× | 1 h | 5 min | page | Wake on-call |
| Slow | 6× | 6 h | 30 min | ticket | Look during business hours |

Rationale: at 14.4× burn we consume 2% of monthly budget in 1 hour; at
6× we consume 10% in 6 hours. Anything slower we look at during weekly
review.

Implemented in `slo-alerts.yml`:
* `APIAvailabilityFastBurn`
* `APIAvailabilitySlowBurn`

Per-SLO burn alerts will be added the same way as we ship dashboards
for SLOs 3–6.

---

## Error budget policy

When the **rolling 30-day error budget for any page-tier SLO is < 0%**
(i.e. exhausted):

1. We stop merging non-trivial product PRs to `main`.
2. The next deploy must be a reliability fix.
3. We document the cause in `dev-team/05-devops-hestia-kaoru/work/postmortems/`.
4. Budget resets after rolling window naturally; we don't grant
   "discretionary" budget.

When the budget is < 30%:

1. Code freeze isn't triggered, but new risky deploys must be reviewed
   by the on-call.
2. We bias toward smaller PRs and feature flags.

When the budget is > 100% (always green for 30d):

1. Either the SLO is too loose → tighten it next review.
2. Or we have headroom for a planned chaos exercise.

---

## Reporting

* Grafana dashboard "Forex Bot — SLOs" (planned for Phase 1 close).
  Shows: current SLI, 30-day SLO, remaining budget, burn rate.
* Monthly SLO review: 30-minute meeting; 3 things only — current state,
  incidents that ate budget, action items.
* Quarterly SLO review: are the targets still right? Bump or relax.

---

## What is explicitly *not* an SLO

* **Order win rate / PnL** — that's a strategy/quant concern, not
  infrastructure. Kairos owns it.
* **Time to first byte from frontend** — covered by Web Vitals on the
  client; will become an SLO in Phase 3.
* **Slippage vs market price** — needs richer broker data; we will
  start measuring in Phase 2 before turning into SLO.

Keeping the SLO list short is the point. If everything is critical,
nothing is.
