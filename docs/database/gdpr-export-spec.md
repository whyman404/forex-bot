# GDPR / PDPA Data Export Specification

**Author:** Mnemosyne Rin
**Date:** 2026-06-15
**Endpoint:** `POST /users/me/export` → enqueue ; `GET /users/me/export/{id}` → poll
**Backed by:** `account_exports` table (migration 0003)

---

## Goal

When a user invokes their right to data portability (GDPR Art. 20 /
PDPA s. 31), they receive a single downloadable archive containing every
piece of personal data we hold about them — in a machine-readable form.

Output is a **zip** containing:
- `manifest.json` — index of the contents + record counts
- one `.ndjson` file per table (newline-delimited JSON)
- `README.txt` — human-readable explanation of contents

NDJSON is preferred over JSON-array because it streams better and lets the
user `jq` line-by-line without loading the whole file.

---

## Tables exported

Order: identity → billing → trading → notifications → audit.

### 1. `users.ndjson` (1 row)

Sanitized: **NO `password_hash`, NO `totp_secret`**.

Fields:
```
id, email, email_verified_at, full_name, country, role,
onboarding_step, stripe_customer_id, consent_marketing_at,
created_at, updated_at, deleted_at
```

### 2. `subscriptions.ndjson`

All subscription rows (any status).

Fields:
```
id, plan, plan_id, status, stripe_subscription_id,
current_period_start, current_period_end, canceled_at,
created_at, updated_at
```

### 3. `invoices.ndjson`

All invoice rows.

Fields:
```
id, subscription_id, stripe_invoice_id, amount_cents, currency,
status, paid_at, hosted_invoice_url, created_at
```

### 4. `broker_accounts.ndjson`

**Metadata only — NO `credentials_ciphertext`, NO `credentials_nonce`,
NO `credentials_key_version`.** The encrypted secret is by definition
NOT data that belongs to the user's right to export (it's our encryption
artifact). The label + broker name + masked login is what they need.

Fields:
```
id, broker, account_label, mt5_login_masked (last 4 of mt5_login),
mt5_server, leverage, account_currency, balance_cached_cents,
last_sync_at, is_active, mt5_bridge_id, created_at, updated_at, deleted_at
```

### 5. `strategy_instances.ndjson`

All instances (including soft-deleted).

Fields:
```
id, broker_account_id, strategy_id, label, params, status,
risk_percent, max_daily_loss_cents, daily_loss_today_cents,
kill_switch_armed, last_signal_at, started_at, stopped_at,
live_engine_pid, last_heartbeat_at,
created_at, updated_at, deleted_at
```

### 6. `backtests.ndjson`

All backtest rows + their summary metrics.

Fields:
```
id, strategy_id, asset_symbol, timeframe, params, start_date, end_date,
status, total_return_pct, max_drawdown_pct, sharpe, sortino,
profit_factor, win_rate_pct, total_trades, equity_curve_url,
trades_count, started_at, completed_at, error_message, created_at
```

### 7. `signals_last90d.ndjson`

Trading signals for this user's instances, **last 90 days** only.

Rationale: signals are operational ephemera; full history can be large
and is not what most users actually want. If the user explicitly requests
full history, we provide via support ticket (rare). 90d is documented in
the export README.

Filter: `created_at >= now() - interval '90 days'`.

Fields:
```
id, strategy_instance_id, ts, direction, price, sl, tp, reason,
status, broker_order_id, created_at
```

### 8. `trades.ndjson`

**All trades** (no time filter — regulatory + user's actual money).

Fields:
```
id, strategy_instance_id, signal_id, broker_account_id, symbol, side,
lot_size, entry_price, entry_at, exit_price, exit_at, sl, tp,
commission_cents, swap_cents, gross_pnl_cents, net_pnl_cents,
status, broker_ticket, created_at, updated_at
```

### 9. `consents.ndjson`

All consent records (ToS, privacy, marketing, data processing).

Fields: `id, kind, version, agreed_at`.

### 10. `live_consents.ndjson`

All live-go acknowledgements.

Fields: `id, strategy_code, version, risk_acknowledged, ip_addr,
user_agent, signed_at`.

### 11. `notifications_last90d.ndjson`

Notifications sent to the user, last 90 days.

Fields: TBD by Atlas (notifications model).

### 12. `audit_log_self_last90d.ndjson`

Audit log entries where `actor_user_id = $user`, last 90 days only.

Rationale: PDPA s.31 + GDPR Art. 15 grants insight into how their data
was processed. We expose **their own actions**, not system actions about
them (the latter often contains internal ops metadata that is privileged).

Fields: `id, action, target_type, target_id, payload_redacted, ip_addr,
user_agent, created_at`.

---

## `manifest.json` shape

```json
{
  "format_version": "1.0",
  "user_id": "0193abcd-...",
  "exported_at": "2026-06-15T14:00:00Z",
  "files": [
    {"name": "users.ndjson",                 "rows": 1},
    {"name": "subscriptions.ndjson",         "rows": 2},
    {"name": "invoices.ndjson",              "rows": 12},
    {"name": "broker_accounts.ndjson",       "rows": 2},
    {"name": "strategy_instances.ndjson",    "rows": 3},
    {"name": "backtests.ndjson",             "rows": 47},
    {"name": "signals_last90d.ndjson",       "rows": 1284},
    {"name": "trades.ndjson",                "rows": 320},
    {"name": "consents.ndjson",              "rows": 4},
    {"name": "live_consents.ndjson",         "rows": 3},
    {"name": "notifications_last90d.ndjson", "rows": 41},
    {"name": "audit_log_self_last90d.ndjson","rows": 220}
  ],
  "sha256_per_file": { "...": "..." },
  "redactions_applied": [
    "users.password_hash",
    "users.totp_secret",
    "broker_accounts.credentials_*",
    "audit_log entries by other actors"
  ]
}
```

---

## Operational notes

- The exporter is a background worker; row is created in `account_exports`
  with `status='queued'`, transitions through `running` → `ready`.
- Output uploaded to S3 with a pre-signed URL written into
  `account_exports.download_url`.
- `expires_at` = 7 days from `ready`. After expiry the row moves to
  `expired` and a partition-purge cron deletes the S3 object.
- Hard upper bound: one export per user per 24h (rate-limited at API).
- Audit-log a row on enqueue AND on download — exports are themselves
  subject to audit.
- Backend (Atlas) owns the worker. I (Rin) own the SQL.
