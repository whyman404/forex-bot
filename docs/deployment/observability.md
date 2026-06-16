# Observability — Forex Bot

> Owner: Hestia Kaoru — DevOps / SRE
> Last updated: 2026-06-14

> "If you can't see it, you can't fix it." — and at 3am you absolutely
> need to see it.

---

## Pillars

| Pillar | Tool (Phase 1) | Phase 3 candidate | Why |
|--------|----------------|-------------------|-----|
| Logs | **Loki + structlog JSON** + Promtail | Same, with S3 backend | Cheap, label-driven, plays well with Grafana |
| Metrics | **Prometheus** + `prometheus-fastapi-instrumentator` | Same, with remote-write to Mimir | Industry default, simple to operate |
| Traces | OpenTelemetry SDK (in code, exporter disabled) | **Tempo or Honeycomb** | Skip in MVP; enable when we need to debug latency across services |
| Errors | **Sentry** (free tier) | Same | Already integrated in FastAPI via `sentry-sdk[fastapi]` |
| Dashboards | **Grafana** | Same | One pane for metrics + logs + traces |
| Alerting | **Prometheus + Grafana managed alerts** | Add PagerDuty | Free tier covers MVP team of 1–3 |

---

## Logs — structured JSON via structlog

Every service writes a single JSON line per log event to stdout. Promtail
tails the docker JSON log files and ships to Loki. Loki's label set is
intentionally small — high-cardinality fields go into the log body, not
labels.

**Labels (low cardinality only):**
* `service` (backend, frontend, trading-engine, mt5-supervisor)
* `env` (development, staging, production)
* `level` (DEBUG, INFO, WARNING, ERROR, CRITICAL)
* `container`

**Log body (parsed from JSON, queryable but not labelled):**
* `request_id` — propagated through the request lifecycle
* `user_id` — when authenticated
* `event` — short stable name (`order.placed`, `signal.generated`)
* `error` — exception class + message
* `latency_ms`, `status`, etc.

Example LogQL queries:

```logql
# All backend errors in the last 1h
{service="backend", level="ERROR"} | json

# Slow requests
{service="backend"} | json | latency_ms > 500

# A specific user's session
{service="backend"} | json | user_id = "usr_abc"
```

---

## Metrics — Prometheus

Backend exposes `/metrics` via `prometheus-fastapi-instrumentator`. The
trading engine exposes its own metrics on `:9100`. MT5 supervisor on
`:9101`. Host metrics from `node-exporter` (Linux) and
`windows_exporter` (Windows VPS).

### Core metrics

**HTTP / API (RED method)**

| Metric | Type | Purpose |
|--------|------|---------|
| `http_requests_total{method,route,status,service}` | counter | Rate + Errors |
| `http_request_duration_seconds_bucket{...}` | histogram | Duration percentiles |
| `http_requests_in_progress{service}` | gauge | Saturation |

**Trading engine**

| Metric | Type | Purpose |
|--------|------|---------|
| `signals_generated_total{strategy,symbol}` | counter | Signal flow |
| `signal_to_order_latency_seconds_bucket{...}` | histogram | E2E latency to broker |
| `open_positions_total{account_id,symbol}` | gauge | Position state |
| `account_daily_pnl_usd{account_id}` | gauge | Risk monitoring |
| `account_daily_loss_limit_usd{account_id}` | gauge | Kill switch threshold |
| `account_max_drawdown_pct{account_id}` | gauge | Risk |
| `backtest_jobs_total{result}` | counter | Backtest reliability |

**MT5 supervisor**

| Metric | Type | Purpose |
|--------|------|---------|
| `mt5_supervisor_last_heartbeat_timestamp_seconds` | gauge | Liveness |
| `mt5_broker_connected` | gauge | 1/0 broker connection |
| `mt5_orders_total{result}` | counter | Orders accepted/rejected/error |
| `mt5_order_latency_seconds_bucket{...}` | histogram | Supervisor→MT5 round trip |
| `mt5_supervisor_wss_reconnects_total` | counter | WSS reliability |
| `mt5_supervisor_mt5_restarts_total` | counter | Terminal stability |

**Infrastructure (USE method)**

| Metric source | What it tells us |
|---------------|------------------|
| `node-exporter` | CPU, memory, disk, network, filesystem fill |
| `cadvisor` | Per-container CPU + memory + I/O |
| `redis_exporter` | Hit ratio, evicted keys, queue depths |
| `pg_exporter` | Connections, slow queries, replication lag |
| `windows_exporter` | Windows VPS health |

---

## Traces — OpenTelemetry (MVP-disabled)

The backend ships `opentelemetry-instrumentation-fastapi` and friends
(see `backend/pyproject.toml`). Exporter is configured but Tempo is not
deployed for Phase 1 — `OTEL_TRACES_SAMPLER_ARG=0.0` keeps it dormant.

Enable for Phase 2:

1. Deploy Tempo as another docker service.
2. Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317` in `.env`.
3. Bump `OTEL_TRACES_SAMPLER_ARG=0.1` (10% sample).
4. Add Tempo datasource to Grafana provisioning.

We keep the instrumentation in code today so it's a config flip, not a
refactor, when we need it.

---

## Dashboards

All dashboards live in `infra/grafana/dashboards/` and are provisioned
on container start.

### Forex Bot — API Overview (RED)

Already shipped: `api-overview.json`. Panels:

* Stat row: req/s, 5xx ratio, p95 latency, signal→order p95
* Time series: requests by status, latency p50/p95/p99
* Trading: open positions, signals/min by strategy, MT5 heartbeat age
* Queue depth, recent backend errors (logs)

### Planned (Phase 1 close-out)

* **Forex Bot — Trading** — per-strategy PnL, win rate, drawdown,
  position breakdown by symbol.
* **Forex Bot — Infra (USE)** — CPU/memory/disk/network on both VPSes,
  Postgres connection saturation, Redis evicted_keys, backup last
  success age.
* **Forex Bot — Business** — DAU/MAU, signup funnel, paid conversion,
  churn. (Eos owns frontend events; Hestia provides storage + dashboard.)

---

## Alerts

Defined in `infra/prometheus/rules/slo-alerts.yml`. Every alert has a
`runbook_url` annotation pointing at a runbook in
`docs/deployment/runbooks/`. **Rule: no runbook → no alert.**

### Severity levels

| Severity | Reaction | Channel |
|----------|----------|---------|
| `page` | Wake the on-call | PagerDuty (Phase 2) / Discord + SMS in Phase 1 |
| `ticket` | Address within 1 business day | GitHub issue auto-created |
| `info` | Logged for trend analysis | Slack/Discord only |

### Current alerts (paging)

| Alert | Trigger | Why it pages |
|-------|---------|--------------|
| `APIAvailabilityFastBurn` | 14.4x SLO burn in 1h | Error budget being eaten |
| `APILatencyP95High` | p95 > 500ms for 10 min | User-visible slowness |
| `SignalToOrderLatencyHigh` | p95 > 2s for 5 min | Trading edge degraded |
| `MT5SupervisorDown` | No heartbeat 60s | Live trading halted |
| `MT5BrokerConnectionLost` | broker disconnect | Open positions stale |
| `DailyLossLimitHit` | account loss > limit | Kill switch engaged |
| `MaxDrawdownExceeded` | drawdown > 20% | Strategy needs review |
| `DiskUsageCritical` | disk > 90% | Service degradation imminent |
| `PostgresDown` | pg_up == 0 | Total outage |
| `RedisDown` | redis_up == 0 | Sessions broken |

### Alert hygiene — Hestia's rules

* If an alert fires and we don't act → mute or delete it within the next
  postmortem; do not let alert fatigue start.
* Every page must include: summary, current value, runbook URL,
  dashboard URL.
* `for:` clauses use multi-window: never page on a 1-minute spike.
* Test alerts in staging by faking the underlying metric every quarter.

---

## SLOs

See `slo.md`. Brief:

* **API availability**: 99.5% over 30 days (budget = 3h 39min/30d).
* **Signal-to-order p95**: ≤ 2s.
* **Backtest job success**: ≥ 99%.

Burn-rate alerts come from `slo-alerts.yml`.

---

## On-call workflow (Phase 1, team of 1–3)

1. Alert fires → Discord + SMS (Twilio).
2. On-call engineer acknowledges in Discord within 5 min.
3. Open the relevant runbook from the alert's `runbook_url`.
4. Mitigate first (rollback / kill switch / failover), root-cause later.
5. Within 48h: write a blameless postmortem in
   `dev-team/05-devops-hestia-kaoru/work/postmortems/`.

---

## What I won't do (yet)

* Build our own anomaly detection — false positives ruin trust.
* Pay for Datadog before we hit $1k/mo budget — Prometheus + Loki are
  fine until traffic is real.
* Use tracing as the primary debug tool while we don't have the scale to
  feed it — wasted vendor spend.
