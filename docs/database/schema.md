# Database Schema — Forex/Crypto Trading Bot Platform

> Schema design document for the SaaS trading bot platform
> **Author:** Mnemosyne Rin (Database Engineer)
> **Reviewed with:** Daedalus Souta (Architect), Argus Hayato (Security), Atlas Goro (Backend)
> **Created:** 2026-06-14
> **PostgreSQL Version:** 16
> **ORM:** SQLAlchemy 2.0 + Alembic

---

## 0. Design Principles

1. **UUIDv7 primary keys** — time-sortable, index-friendly, no enumeration risk vs. integers. Generated via `uuidv7()` function (we will create it via `pgcrypto` + extension or app-side via `uuid_utils`).
2. **`timestamptz` always** — never naive `timestamp`. All times stored UTC.
3. **`created_at` + `updated_at`** on every table; `deleted_at` only where soft-delete justified (user accounts, broker accounts, strategy instances).
4. **Foreign keys are enforced** — DB is the source of truth for invariants, not the app.
5. **CHECK constraints** for bounded numeric values (`risk_percent`, etc.) — code drift cannot violate.
6. **Enums via CHECK** (not `CREATE TYPE`) — easier to migrate values without rewriting columns; type-stable VARCHAR + CHECK constraint.
7. **Money in `_cents` BIGINT** — never `FLOAT`. Prices in `NUMERIC(18,8)` (8 dp = enough for BTC + Gold).
8. **Encrypted at column-level** — broker credentials use envelope encryption (per ADR-005, Argus). Ciphertext + nonce + key_version stored, plaintext never touches DB.
9. **Range partitioning by month** on the three growth-driven tables: `signals`, `trades`, `audit_log` (millions of rows/year per active user).
10. **Index strategy** — indexes follow real queries (Atlas's access patterns), not "every FK gets an index reflexively." But FKs that join in hot paths do get covering composites.

---

## 1. Identifier & Time Conventions

- **PK:** `id UUID NOT NULL DEFAULT uuidv7()` (we provide `uuidv7()` PL/pgSQL or use `pg_uuidv7` extension).
- **FKs:** `<entity>_id UUID NOT NULL REFERENCES <entity>(id)` — `ON DELETE` policy decided per case (mostly `RESTRICT`, only `CASCADE` for owned children like `signals` -> `strategy_instance`).
- **Timestamps:** `timestamptz NOT NULL DEFAULT now()` for `created_at`. `updated_at` driven by trigger `set_updated_at()`.
- **Soft delete:** `deleted_at timestamptz NULL` + partial unique indexes `WHERE deleted_at IS NULL` so emails / labels can be reused after deletion.

---

## 2. Tables

### 2.1 `users`

**Purpose:** Account holder of the SaaS. Owns subscriptions, broker accounts, strategy instances.

| Column              | Type         | Constraint                                    | Notes |
|---------------------|--------------|-----------------------------------------------|-------|
| id                  | uuid         | PK                                            | uuidv7 |
| email               | citext       | NOT NULL, UNIQUE (partial: deleted_at IS NULL)| case-insensitive |
| password_hash       | text         | NOT NULL                                      | Argon2id (per Argus ADR-004) |
| email_verified_at   | timestamptz  | NULL                                          | NULL = unverified |
| totp_secret         | bytea        | NULL                                          | encrypted at app layer |
| full_name           | text         | NOT NULL                                      | |
| country             | char(2)      | NOT NULL                                      | ISO 3166-1 alpha-2 |
| role                | varchar(16)  | NOT NULL CHECK IN ('user','admin') DEFAULT 'user' | |
| created_at          | timestamptz  | NOT NULL DEFAULT now()                        | |
| updated_at          | timestamptz  | NOT NULL DEFAULT now()                        | trigger |
| deleted_at          | timestamptz  | NULL                                          | soft delete; purge ≥30d (data-retention.md) |

**Indexes**
- `users_pk` on `(id)` — PK btree.
- `users_email_uniq` UNIQUE on `(email)` WHERE `deleted_at IS NULL` — login lookup.
- `users_role_idx` btree on `(role)` WHERE `role='admin'` — small partial; admin list is rare.

**Justification:** Email uniqueness must not block re-registration after soft-delete + purge; partial unique handles that. `citext` avoids case-folding bugs at login.

---

### 2.2 `subscriptions`

**Purpose:** Membership lifecycle, mapped 1:N to user (a user can churn + resubscribe). Source of billing truth = Stripe; this is a local materialization for fast queries.

| Column                  | Type         | Constraint                                                                                                              |
|-------------------------|--------------|--------------------------------------------------------------------------------------------------------------------------|
| id                      | uuid         | PK                                                                                                                       |
| user_id                 | uuid         | NOT NULL REFERENCES users(id) ON DELETE RESTRICT                                                                         |
| plan                    | varchar(24)  | NOT NULL CHECK IN ('trial','pro_monthly','pro_yearly','lifetime')                                                        |
| status                  | varchar(16)  | NOT NULL CHECK IN ('active','past_due','canceled','trialing')                                                            |
| stripe_subscription_id  | text         | NULL UNIQUE                                                                                                              |
| current_period_start    | timestamptz  | NULL                                                                                                                     |
| current_period_end      | timestamptz  | NULL                                                                                                                     |
| canceled_at             | timestamptz  | NULL                                                                                                                     |
| created_at              | timestamptz  | NOT NULL DEFAULT now()                                                                                                   |
| updated_at              | timestamptz  | NOT NULL DEFAULT now()                                                                                                   |

**Indexes**
- `subscriptions_user_status_idx` on `(user_id, status)` — dashboard "show my active subscription".
- `subscriptions_period_end_idx` on `(current_period_end)` WHERE `status='active'` — renewal sweep job.
- `subscriptions_stripe_uniq` UNIQUE on `(stripe_subscription_id)` — webhook idempotency.

**Justification:** Status x user_id is the hot path. The partial index on period_end keeps it small while supporting nightly renewal jobs efficiently.

---

### 2.3 `invoices`

**Purpose:** Immutable record of billing events from Stripe. Append-only.

| Column                | Type         | Constraint                                                              |
|-----------------------|--------------|-------------------------------------------------------------------------|
| id                    | uuid         | PK                                                                      |
| user_id               | uuid         | NOT NULL REFERENCES users(id) ON DELETE RESTRICT                        |
| subscription_id       | uuid         | NULL REFERENCES subscriptions(id) ON DELETE RESTRICT                    |
| stripe_invoice_id     | text         | NOT NULL UNIQUE                                                         |
| amount_cents          | bigint       | NOT NULL CHECK (amount_cents >= 0)                                      |
| currency              | char(3)      | NOT NULL                                                                |
| status                | varchar(16)  | NOT NULL CHECK IN ('draft','open','paid','uncollectible','void')        |
| paid_at               | timestamptz  | NULL                                                                    |
| hosted_invoice_url    | text         | NULL                                                                    |
| created_at            | timestamptz  | NOT NULL DEFAULT now()                                                  |

**Indexes**
- `invoices_user_created_idx` on `(user_id, created_at DESC)` — invoice history page.
- `invoices_stripe_uniq` UNIQUE on `(stripe_invoice_id)` — webhook dedupe.
- `invoices_status_idx` on `(status)` WHERE `status IN ('open','uncollectible')` — collections.

**Justification:** Append-only — no `updated_at`. Money in `bigint` cents. Currency at column level (not derived) because Stripe events carry it explicitly.

---

### 2.4 `broker_accounts`

**Purpose:** External brokerage credentials, **encrypted at column level** per ADR-005 (Argus). One user can connect multiple brokers.

| Column                    | Type         | Constraint                                                                                       |
|---------------------------|--------------|--------------------------------------------------------------------------------------------------|
| id                        | uuid         | PK                                                                                               |
| user_id                   | uuid         | NOT NULL REFERENCES users(id) ON DELETE RESTRICT                                                 |
| broker                    | varchar(24)  | NOT NULL CHECK IN ('exness_mt5','binance','bybit')                                               |
| account_label             | text         | NOT NULL                                                                                         |
| mt5_login                 | bigint       | NULL                                                                                             |
| mt5_server                | text         | NULL                                                                                             |
| credentials_ciphertext    | bytea        | NOT NULL                                                                                         |
| credentials_nonce         | bytea        | NOT NULL                                                                                         |
| credentials_key_version   | int          | NOT NULL DEFAULT 1                                                                               |
| leverage                  | int          | NULL CHECK (leverage > 0 AND leverage <= 2000)                                                   |
| account_currency          | char(3)      | NULL                                                                                             |
| balance_cached_cents      | bigint       | NULL                                                                                             |
| last_sync_at              | timestamptz  | NULL                                                                                             |
| is_active                 | boolean      | NOT NULL DEFAULT true                                                                            |
| created_at                | timestamptz  | NOT NULL DEFAULT now()                                                                           |
| updated_at                | timestamptz  | NOT NULL DEFAULT now()                                                                           |
| deleted_at                | timestamptz  | NULL                                                                                             |

**Indexes**
- `broker_accounts_user_active_idx` on `(user_id, is_active)` WHERE `deleted_at IS NULL` — list user's active brokers.
- `broker_accounts_label_uniq` UNIQUE on `(user_id, account_label)` WHERE `deleted_at IS NULL`.
- `broker_accounts_key_version_idx` on `(credentials_key_version)` — key-rotation sweep.

**Justification:** Plaintext credentials must never touch DB. `key_version` lets Argus rotate KMS keys without re-encrypting all rows in one shot — sweep job re-encrypts version-1 rows to version-2 over time.

---

### 2.5 `strategies`

**Purpose:** Catalog of strategies (the 6 named in product spec) — global, shared by all users. Owned by the team, not the user.

| Column          | Type         | Constraint                                                                                   |
|-----------------|--------------|----------------------------------------------------------------------------------------------|
| id              | uuid         | PK                                                                                           |
| code            | varchar(48)  | NOT NULL UNIQUE CHECK IN ('london_breakout','ny_killzone','ema_adx','ema_rsi','donchian','grid') |
| display_name    | text         | NOT NULL                                                                                     |
| asset_class     | varchar(16)  | NOT NULL CHECK IN ('gold','btc')                                                             |
| default_params  | jsonb        | NOT NULL DEFAULT '{}'::jsonb                                                                 |
| version         | int          | NOT NULL DEFAULT 1                                                                           |
| description     | text         | NULL                                                                                         |
| risk_rating     | varchar(8)   | NOT NULL CHECK IN ('low','medium','high')                                                    |
| is_enabled      | boolean      | NOT NULL DEFAULT true                                                                        |
| created_at      | timestamptz  | NOT NULL DEFAULT now()                                                                       |
| updated_at      | timestamptz  | NOT NULL DEFAULT now()                                                                       |

**Indexes**
- `strategies_code_uniq` UNIQUE on `(code)`.
- `strategies_enabled_idx` on `(is_enabled, asset_class)` WHERE `is_enabled=true` — strategy picker UI.

**Justification:** Closed enum of 6; new strategies require a migration (intentional governance). `default_params` as JSONB supports param schema evolution without column churn.

---

### 2.6 `strategy_instances`

**Purpose:** A user's running configuration of a strategy bound to one broker account. The "bot" in product language.

| Column                    | Type           | Constraint                                                                          |
|---------------------------|----------------|--------------------------------------------------------------------------------------|
| id                        | uuid           | PK                                                                                   |
| user_id                   | uuid           | NOT NULL REFERENCES users(id) ON DELETE RESTRICT                                     |
| broker_account_id         | uuid           | NOT NULL REFERENCES broker_accounts(id) ON DELETE RESTRICT                           |
| strategy_id               | uuid           | NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT                                |
| label                     | text           | NOT NULL                                                                             |
| params                    | jsonb          | NOT NULL DEFAULT '{}'::jsonb                                                         |
| status                    | varchar(16)    | NOT NULL CHECK IN ('paper','live','stopped','killed')                                |
| risk_percent              | numeric(5,2)   | NOT NULL CHECK (risk_percent >= 0 AND risk_percent <= 10)                            |
| max_daily_loss_cents      | bigint         | NOT NULL CHECK (max_daily_loss_cents >= 0)                                           |
| daily_loss_today_cents    | bigint         | NOT NULL DEFAULT 0                                                                   |
| kill_switch_armed         | boolean        | NOT NULL DEFAULT true                                                                |
| last_signal_at            | timestamptz    | NULL                                                                                 |
| started_at                | timestamptz    | NULL                                                                                 |
| stopped_at                | timestamptz    | NULL                                                                                 |
| created_at                | timestamptz    | NOT NULL DEFAULT now()                                                               |
| updated_at                | timestamptz    | NOT NULL DEFAULT now()                                                               |
| deleted_at                | timestamptz    | NULL                                                                                 |

**Indexes**
- `strategy_instances_user_status_idx` on `(user_id, status)` WHERE `deleted_at IS NULL`.
- `strategy_instances_broker_idx` on `(broker_account_id)` WHERE `deleted_at IS NULL`.
- `strategy_instances_label_uniq` UNIQUE on `(user_id, label)` WHERE `deleted_at IS NULL`.
- `strategy_instances_running_idx` on `(status)` WHERE `status IN ('live','paper')` — engine startup pickup.

**Justification:** The `risk_percent` cap is enforced in DB (CHECK 0-10). `daily_loss_today_cents` is a denormalized counter that the trading engine updates per fill — alternative would be aggregating `trades` on each fill which is too expensive. Daily reset job runs at 00:00 UTC.

---

### 2.7 `backtests`

**Purpose:** Historical strategy performance runs. One-shot jobs — append-only result rows.

| Column              | Type           | Constraint                                                                       |
|---------------------|----------------|----------------------------------------------------------------------------------|
| id                  | uuid           | PK                                                                               |
| user_id             | uuid           | NOT NULL REFERENCES users(id) ON DELETE RESTRICT                                 |
| strategy_id         | uuid           | NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT                            |
| asset_symbol        | varchar(16)    | NOT NULL                                                                         |
| timeframe           | varchar(8)     | NOT NULL CHECK IN ('M1','M5','M15','M30','H1','H4','D1')                         |
| params              | jsonb          | NOT NULL DEFAULT '{}'::jsonb                                                     |
| start_date          | date           | NOT NULL                                                                         |
| end_date            | date           | NOT NULL CHECK (end_date >= start_date)                                          |
| status              | varchar(16)    | NOT NULL CHECK IN ('queued','running','completed','failed') DEFAULT 'queued'     |
| total_return_pct    | numeric(10,4)  | NULL                                                                             |
| max_drawdown_pct    | numeric(10,4)  | NULL                                                                             |
| sharpe              | numeric(10,4)  | NULL                                                                             |
| sortino             | numeric(10,4)  | NULL                                                                             |
| profit_factor       | numeric(10,4)  | NULL                                                                             |
| win_rate_pct        | numeric(5,2)   | NULL CHECK (win_rate_pct IS NULL OR (win_rate_pct >= 0 AND win_rate_pct <= 100)) |
| total_trades        | int            | NULL CHECK (total_trades IS NULL OR total_trades >= 0)                           |
| equity_curve_url    | text           | NULL                                                                             |
| trades_count        | int            | NULL                                                                             |
| started_at          | timestamptz    | NULL                                                                             |
| completed_at        | timestamptz    | NULL                                                                             |
| error_message       | text           | NULL                                                                             |
| created_at          | timestamptz    | NOT NULL DEFAULT now()                                                           |

**Indexes**
- `backtests_user_created_idx` on `(user_id, created_at DESC)`.
- `backtests_status_idx` on `(status)` WHERE `status IN ('queued','running')` — worker pickup.
- `backtests_strategy_idx` on `(strategy_id, completed_at DESC)` WHERE `status='completed'`.

**Justification:** `equity_curve_url` points to S3/local blob (10k+ point series should not be inlined). Metric columns are `numeric` for exact math.

---

### 2.8 `signals` (PARTITIONED by month on `ts`)

**Purpose:** Every actionable signal the strategy produces. Hot, write-heavy. Partitioned to keep indexes small and enable cheap pruning.

| Column                 | Type           | Constraint                                                                                |
|------------------------|----------------|-------------------------------------------------------------------------------------------|
| id                     | uuid           | NOT NULL                                                                                  |
| strategy_instance_id   | uuid           | NOT NULL REFERENCES strategy_instances(id) ON DELETE CASCADE                              |
| ts                     | timestamptz    | NOT NULL                                                                                  |
| direction              | varchar(8)     | NOT NULL CHECK IN ('long','short')                                                        |
| price                  | numeric(18,8)  | NOT NULL                                                                                  |
| sl                     | numeric(18,8)  | NULL                                                                                      |
| tp                     | numeric(18,8)  | NULL                                                                                      |
| reason                 | jsonb          | NOT NULL DEFAULT '{}'::jsonb                                                              |
| status                 | varchar(16)    | NOT NULL CHECK IN ('generated','sent_to_broker','filled','rejected','canceled')           |
| broker_order_id        | text           | NULL                                                                                      |
| created_at             | timestamptz    | NOT NULL DEFAULT now()                                                                    |
| PRIMARY KEY            | (id, ts)       | composite (required for partition pruning)                                                |

**Partition strategy:** `PARTITION BY RANGE (ts)` — one partition per month, named `signals_yYYYY_mMM`. See `partitioning.md`.

**Indexes (per partition, inherited from parent)**
- `signals_instance_ts_idx` on `(strategy_instance_id, ts DESC)` — chart / replay.
- `signals_status_idx` on `(status)` WHERE `status IN ('generated','sent_to_broker')` — open-signal sweep.
- `signals_broker_order_idx` on `(broker_order_id)` WHERE `broker_order_id IS NOT NULL` — broker webhook lookup.

**Justification:** Composite PK `(id, ts)` because Postgres requires partition key in PK / unique constraints. The hot read pattern is "last N signals for instance X" — composite `(strategy_instance_id, ts DESC)` answers it via index-only scan.

---

### 2.9 `trades` (PARTITIONED by month on `created_at`)

**Purpose:** Executed positions on the broker. Source of truth for PnL. Append + update-on-close (status, exit fields).

| Column                 | Type           | Constraint                                                                          |
|------------------------|----------------|-------------------------------------------------------------------------------------|
| id                     | uuid           | NOT NULL                                                                            |
| strategy_instance_id   | uuid           | NOT NULL REFERENCES strategy_instances(id) ON DELETE RESTRICT                       |
| signal_id              | uuid           | NULL                                                                                |
| broker_account_id      | uuid           | NOT NULL REFERENCES broker_accounts(id) ON DELETE RESTRICT                          |
| symbol                 | varchar(16)    | NOT NULL                                                                            |
| side                   | varchar(4)     | NOT NULL CHECK IN ('buy','sell')                                                    |
| lot_size               | numeric(10,4)  | NOT NULL CHECK (lot_size > 0)                                                       |
| entry_price            | numeric(18,8)  | NOT NULL                                                                            |
| entry_at               | timestamptz    | NOT NULL                                                                            |
| exit_price             | numeric(18,8)  | NULL                                                                                |
| exit_at                | timestamptz    | NULL                                                                                |
| sl                     | numeric(18,8)  | NULL                                                                                |
| tp                     | numeric(18,8)  | NULL                                                                                |
| commission_cents       | bigint         | NOT NULL DEFAULT 0                                                                  |
| swap_cents             | bigint         | NOT NULL DEFAULT 0                                                                  |
| gross_pnl_cents        | bigint         | NULL                                                                                |
| net_pnl_cents          | bigint         | NULL                                                                                |
| status                 | varchar(16)    | NOT NULL CHECK IN ('open','closed','canceled')                                      |
| broker_ticket          | varchar(64)    | NULL                                                                                |
| created_at             | timestamptz    | NOT NULL DEFAULT now()                                                              |
| updated_at             | timestamptz    | NOT NULL DEFAULT now()                                                              |
| PRIMARY KEY            | (id, created_at) | composite                                                                         |

**Partition strategy:** `PARTITION BY RANGE (created_at)` monthly. See `partitioning.md`.

**Indexes**
- `trades_instance_status_idx` on `(strategy_instance_id, status, entry_at DESC)`.
- `trades_broker_ticket_uniq` UNIQUE on `(broker_account_id, broker_ticket)` WHERE `broker_ticket IS NOT NULL` — broker reconciliation, idempotency.
- `trades_signal_idx` on `(signal_id)` WHERE `signal_id IS NOT NULL`.
- `trades_open_idx` on `(strategy_instance_id)` WHERE `status='open'` — fast "all open positions per bot".

**Justification:** `signal_id` is nullable because some trades come from manual close / manual flat. Partial unique on broker_ticket enforces idempotency from broker webhooks (the most common dedupe failure source).

---

### 2.10 `mt5_terminal_pool`

**Purpose:** Resource pool for Windows VPS MT5 terminal processes. Each user assigned one terminal at trade time.

| Column                | Type         | Constraint                                                                |
|-----------------------|--------------|---------------------------------------------------------------------------|
| id                    | uuid         | PK                                                                        |
| host_id               | text         | NOT NULL                                                                  |
| status                | varchar(16)  | NOT NULL CHECK IN ('free','assigned','unhealthy')                         |
| assigned_user_id      | uuid         | NULL REFERENCES users(id) ON DELETE SET NULL                              |
| mt5_process_id        | int          | NULL                                                                      |
| mt5_port              | int          | NULL CHECK (mt5_port IS NULL OR (mt5_port > 0 AND mt5_port < 65536))      |
| last_heartbeat_at     | timestamptz  | NULL                                                                      |
| created_at            | timestamptz  | NOT NULL DEFAULT now()                                                    |
| updated_at            | timestamptz  | NOT NULL DEFAULT now()                                                    |

**Indexes**
- `mt5_pool_status_idx` on `(status)` WHERE `status='free'` — fast pickup.
- `mt5_pool_assigned_user_uniq` UNIQUE on `(assigned_user_id)` WHERE `assigned_user_id IS NOT NULL` — one user = one terminal.
- `mt5_pool_heartbeat_idx` on `(last_heartbeat_at)` WHERE `status='assigned'` — health sweep.

**Justification:** Partial unique on `assigned_user_id` enforces 1:1 active assignment. Heartbeat sweep marks stale terminals `unhealthy`.

---

### 2.11 `audit_log` (PARTITIONED by month on `created_at`)

**Purpose:** Append-only security/compliance log. **Never updated, never deleted within retention.** Triggered by API actions (auth, billing, broker_account, strategy_instance lifecycle, admin actions).

| Column              | Type         | Constraint                                                          |
|---------------------|--------------|---------------------------------------------------------------------|
| id                  | uuid         | NOT NULL                                                            |
| actor_user_id       | uuid         | NULL REFERENCES users(id) ON DELETE SET NULL                        |
| action              | varchar(64)  | NOT NULL                                                            |
| target_type         | varchar(32)  | NULL                                                                |
| target_id           | uuid         | NULL                                                                |
| payload_redacted    | jsonb        | NOT NULL DEFAULT '{}'::jsonb                                        |
| ip_addr             | inet         | NULL                                                                |
| user_agent          | text         | NULL                                                                |
| created_at          | timestamptz  | NOT NULL DEFAULT now()                                              |
| PRIMARY KEY         | (id, created_at) | composite                                                       |

**Partition strategy:** `PARTITION BY RANGE (created_at)` monthly.

**Indexes**
- `audit_actor_created_idx` on `(actor_user_id, created_at DESC)`.
- `audit_action_created_idx` on `(action, created_at DESC)`.
- `audit_target_idx` on `(target_type, target_id)` WHERE `target_id IS NOT NULL` — "history for this record".

**Justification:** `payload_redacted` must be pre-scrubbed by app (no secrets / tokens / PII beyond what's allowed). FK on `actor_user_id` uses `ON DELETE SET NULL` — we keep audit history even after user purge for compliance, but de-identify.

---

### 2.12 `api_keys`

**Purpose:** Programmatic access tokens for power users / automation.

| Column           | Type         | Constraint                                                              |
|------------------|--------------|-------------------------------------------------------------------------|
| id               | uuid         | PK                                                                      |
| user_id          | uuid         | NOT NULL REFERENCES users(id) ON DELETE CASCADE                         |
| label            | text         | NOT NULL                                                                |
| key_hash         | bytea        | NOT NULL UNIQUE                                                         |
| last_used_at     | timestamptz  | NULL                                                                    |
| expires_at       | timestamptz  | NULL                                                                    |
| revoked_at       | timestamptz  | NULL                                                                    |
| created_at       | timestamptz  | NOT NULL DEFAULT now()                                                  |

**Indexes**
- `api_keys_hash_uniq` UNIQUE on `(key_hash)` — auth lookup.
- `api_keys_user_active_idx` on `(user_id)` WHERE `revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())` — *not built; expires_at uses now() which is non-immutable*. Use `(user_id, revoked_at)` instead.

**Justification:** Only the hash stored (sha256/blake3 — Argus picks). Cascade delete is acceptable because keys derive lifecycle from user.

---

### 2.13 `notifications`

**Purpose:** Per-user notifications across channels.

| Column        | Type         | Constraint                                                            |
|---------------|--------------|-----------------------------------------------------------------------|
| id            | uuid         | PK                                                                    |
| user_id       | uuid         | NOT NULL REFERENCES users(id) ON DELETE CASCADE                       |
| channel       | varchar(16)  | NOT NULL CHECK IN ('email','push','inapp')                            |
| kind          | varchar(48)  | NOT NULL                                                              |
| payload       | jsonb        | NOT NULL DEFAULT '{}'::jsonb                                          |
| sent_at       | timestamptz  | NULL                                                                  |
| read_at       | timestamptz  | NULL                                                                  |
| created_at    | timestamptz  | NOT NULL DEFAULT now()                                                |

**Indexes**
- `notifications_user_unread_idx` on `(user_id, created_at DESC)` WHERE `read_at IS NULL` — badge count.
- `notifications_user_created_idx` on `(user_id, created_at DESC)` — history view.

**Justification:** 90-day retention (see data-retention.md). Partial index on unread keeps the badge query cheap as history grows.

---

## 3. Triggers

### 3.1 `set_updated_at()`

A generic BEFORE-UPDATE trigger that bumps `updated_at = now()` on row update. Attached to every table with an `updated_at` column.

### 3.2 `prevent_audit_mutation()`

BEFORE UPDATE / DELETE trigger on `audit_log_*` partitions raising an exception. Audit is append-only at the DB level (defense-in-depth alongside app-level discipline).

---

## 4. Relationships (Summary)

```
users 1───* subscriptions
users 1───* invoices
users 1───* broker_accounts
users 1───* strategy_instances
users 1───* backtests
users 1───* api_keys
users 1───* notifications
users 1───* audit_log (actor)
users 1───* mt5_terminal_pool (assigned, 1:1 partial)

subscriptions 1───* invoices

broker_accounts 1───* strategy_instances
broker_accounts 1───* trades

strategies 1───* strategy_instances
strategies 1───* backtests

strategy_instances 1───* signals
strategy_instances 1───* trades

signals 1───* trades (0..1, signal may not fill)
```

See `er-diagram.md` for the Mermaid diagram.

---

## 5. Capacity Projection (Phase 3 — 1,000 active users)

| Table              | Rows/user/day | Total rows / month  | Note |
|--------------------|---------------|---------------------|------|
| signals            | ~200          | ~6M                 | partition rotated |
| trades             | ~50           | ~1.5M               | partition rotated |
| audit_log          | ~30           | ~900K               | partition rotated |
| notifications      | ~10           | ~300K, 90d purge    | |
| subscriptions      | very low      | ~few K total        | |
| backtests          | a few         | ~tens of K          | |

Estimated DB size at end of Phase 3: ~50 GB primary including indexes. PG16 on a 4 vCPU / 16 GB / 200 GB NVMe instance fits with headroom. See `partitioning.md` for retention rotation.

---

## 6. Open Questions / Decisions Pending

- **OLAP separation:** for Phase 4, we plan to push closed `trades` + `signals` to ClickHouse / DuckDB for analytics. Schema here optimized for OLTP.
- **Read replicas:** Phase 2 single primary; Phase 3 add read replica for backtest read-only queries.
- **pgvector:** if we add ML strategy similarity (Kairos's idea), we add a `strategy_embeddings` table later — not in initial schema.

---

## 7. References

- ADR-003 (Daedalus) — Tech stack: PostgreSQL 16 + SQLAlchemy 2.
- ADR-005 (Argus) — Envelope encryption for broker credentials.
- ADR-004 (Argus) — Argon2id for password hashing.
- `partitioning.md` — monthly partition strategy + maintenance.
- `data-retention.md` — GDPR/PDPA retention windows.
