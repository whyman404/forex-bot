# ER Diagram — Forex/Crypto Trading Bot Platform

> Mermaid ER diagram of the OLTP schema
> **Author:** Mnemosyne Rin
> **Created:** 2026-06-14

---

## Full Diagram

```mermaid
erDiagram
    USERS ||--o{ SUBSCRIPTIONS : "has"
    USERS ||--o{ INVOICES : "billed"
    USERS ||--o{ BROKER_ACCOUNTS : "owns"
    USERS ||--o{ STRATEGY_INSTANCES : "runs"
    USERS ||--o{ BACKTESTS : "requests"
    USERS ||--o{ API_KEYS : "issues"
    USERS ||--o{ NOTIFICATIONS : "receives"
    USERS ||--o{ AUDIT_LOG : "acts in"
    USERS ||--o| MT5_TERMINAL_POOL : "assigned to"

    SUBSCRIPTIONS ||--o{ INVOICES : "generates"

    BROKER_ACCOUNTS ||--o{ STRATEGY_INSTANCES : "connected via"
    BROKER_ACCOUNTS ||--o{ TRADES : "executes"

    STRATEGIES ||--o{ STRATEGY_INSTANCES : "templated by"
    STRATEGIES ||--o{ BACKTESTS : "tested by"

    STRATEGY_INSTANCES ||--o{ SIGNALS : "emits"
    STRATEGY_INSTANCES ||--o{ TRADES : "produces"

    SIGNALS ||--o| TRADES : "may fill into"

    USERS {
        uuid id PK
        citext email UK
        text password_hash
        timestamptz email_verified_at
        bytea totp_secret
        text full_name
        char country
        varchar role
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    SUBSCRIPTIONS {
        uuid id PK
        uuid user_id FK
        varchar plan
        varchar status
        text stripe_subscription_id UK
        timestamptz current_period_start
        timestamptz current_period_end
        timestamptz canceled_at
        timestamptz created_at
        timestamptz updated_at
    }

    INVOICES {
        uuid id PK
        uuid user_id FK
        uuid subscription_id FK
        text stripe_invoice_id UK
        bigint amount_cents
        char currency
        varchar status
        timestamptz paid_at
        text hosted_invoice_url
        timestamptz created_at
    }

    BROKER_ACCOUNTS {
        uuid id PK
        uuid user_id FK
        varchar broker
        text account_label
        bigint mt5_login
        text mt5_server
        bytea credentials_ciphertext
        bytea credentials_nonce
        int credentials_key_version
        int leverage
        char account_currency
        bigint balance_cached_cents
        timestamptz last_sync_at
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    STRATEGIES {
        uuid id PK
        varchar code UK
        text display_name
        varchar asset_class
        jsonb default_params
        int version
        text description
        varchar risk_rating
        boolean is_enabled
        timestamptz created_at
        timestamptz updated_at
    }

    STRATEGY_INSTANCES {
        uuid id PK
        uuid user_id FK
        uuid broker_account_id FK
        uuid strategy_id FK
        text label
        jsonb params
        varchar status
        numeric risk_percent
        bigint max_daily_loss_cents
        bigint daily_loss_today_cents
        boolean kill_switch_armed
        timestamptz last_signal_at
        timestamptz started_at
        timestamptz stopped_at
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    BACKTESTS {
        uuid id PK
        uuid user_id FK
        uuid strategy_id FK
        varchar asset_symbol
        varchar timeframe
        jsonb params
        date start_date
        date end_date
        varchar status
        numeric total_return_pct
        numeric max_drawdown_pct
        numeric sharpe
        numeric sortino
        numeric profit_factor
        numeric win_rate_pct
        int total_trades
        text equity_curve_url
        int trades_count
        timestamptz started_at
        timestamptz completed_at
        text error_message
        timestamptz created_at
    }

    SIGNALS {
        uuid id PK
        uuid strategy_instance_id FK
        timestamptz ts
        varchar direction
        numeric price
        numeric sl
        numeric tp
        jsonb reason
        varchar status
        text broker_order_id
        timestamptz created_at
    }

    TRADES {
        uuid id PK
        uuid strategy_instance_id FK
        uuid signal_id FK
        uuid broker_account_id FK
        varchar symbol
        varchar side
        numeric lot_size
        numeric entry_price
        timestamptz entry_at
        numeric exit_price
        timestamptz exit_at
        numeric sl
        numeric tp
        bigint commission_cents
        bigint swap_cents
        bigint gross_pnl_cents
        bigint net_pnl_cents
        varchar status
        varchar broker_ticket
        timestamptz created_at
        timestamptz updated_at
    }

    MT5_TERMINAL_POOL {
        uuid id PK
        text host_id
        varchar status
        uuid assigned_user_id FK
        int mt5_process_id
        int mt5_port
        timestamptz last_heartbeat_at
        timestamptz created_at
        timestamptz updated_at
    }

    AUDIT_LOG {
        uuid id PK
        uuid actor_user_id FK
        varchar action
        varchar target_type
        uuid target_id
        jsonb payload_redacted
        inet ip_addr
        text user_agent
        timestamptz created_at
    }

    API_KEYS {
        uuid id PK
        uuid user_id FK
        text label
        bytea key_hash UK
        timestamptz last_used_at
        timestamptz expires_at
        timestamptz revoked_at
        timestamptz created_at
    }

    NOTIFICATIONS {
        uuid id PK
        uuid user_id FK
        varchar channel
        varchar kind
        jsonb payload
        timestamptz sent_at
        timestamptz read_at
        timestamptz created_at
    }
```

---

## Relationship Notes

- `USERS` is the strong root entity; almost everything traces back to it.
- `STRATEGY_INSTANCES` is the central operational entity: it binds a user × broker × strategy and is the parent of `SIGNALS` and `TRADES`.
- `SIGNALS` -> `TRADES` is 1..0..1 — a signal may not fill; a trade always has a signal except for manual flats (signal_id NULL).
- `MT5_TERMINAL_POOL` -> `USERS` is 1:1 partial (only while assigned), enforced by partial unique index on `assigned_user_id`.
- `AUDIT_LOG.actor_user_id` is `ON DELETE SET NULL` for compliance (we keep history but de-identify on purge).
- `SUBSCRIPTIONS` -> `INVOICES` is 1:N — one subscription can produce many invoices over time.
- `BROKER_ACCOUNTS` -> `TRADES` directly (not transit through strategy instance) because closed positions still belong to the broker account even if the instance is deleted.

---

## Lifecycle Diagram (state)

```mermaid
stateDiagram-v2
    [*] --> trial: signup
    trial --> active: payment_succeeded
    trial --> canceled: trial_expired_no_pay
    active --> past_due: payment_failed
    past_due --> active: dunning_recovered
    past_due --> canceled: dunning_exhausted
    active --> canceled: user_cancel
    canceled --> [*]
```

```mermaid
stateDiagram-v2
    [*] --> paper: instance_created
    paper --> live: user_promote
    live --> stopped: user_pause
    stopped --> live: user_resume
    live --> killed: kill_switch_trigger
    paper --> killed: kill_switch_trigger
    killed --> [*]: archive
```
