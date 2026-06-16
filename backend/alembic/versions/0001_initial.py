"""initial schema — full forex-bot schema from docs/database/schema.sql

Revision ID: 0001
Revises:
Create Date: 2026-06-15

Mnemosyne Rin — this migration is intentionally a single op.execute() of
the canonical SQL block. Reasons:

  1. schema.sql IS the source of truth (versioned, code-reviewed, signed by ADRs).
  2. uuidv7(), pgcrypto extension, partitioning, append-only triggers, and
     partial-unique indexes are awkward to express in SQLAlchemy Core +
     fragile under autogenerate.
  3. Reversal is well-defined: DROP TABLE ... CASCADE for every object,
     then DROP FUNCTION, then DROP EXTENSION.

Downgrade is *destructive* (drops all data). Treated as a one-way wall for
prod — only safe in dev/test where you intend to wipe.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# UPGRADE
# ---------------------------------------------------------------------------
UPGRADE_SQL = r"""
-- =========================================================================
-- Extensions
-- =========================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =========================================================================
-- uuidv7() — RFC 9562 time-ordered UUID generator
-- =========================================================================
CREATE OR REPLACE FUNCTION uuidv7()
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    unix_ms bigint := (extract(epoch from clock_timestamp()) * 1000)::bigint;
    rand_bytes bytea := gen_random_bytes(10);
    uuid_bytes bytea;
BEGIN
    uuid_bytes :=
        set_byte(set_byte(set_byte(set_byte(set_byte(set_byte(
            '\x00000000000000000000000000000000'::bytea,
            0, ((unix_ms >> 40) & 255)::int),
            1, ((unix_ms >> 32) & 255)::int),
            2, ((unix_ms >> 24) & 255)::int),
            3, ((unix_ms >> 16) & 255)::int),
            4, ((unix_ms >> 8)  & 255)::int),
            5, (unix_ms         & 255)::int);
    uuid_bytes := uuid_bytes || rand_bytes;
    uuid_bytes := set_byte(uuid_bytes, 6,
        (((get_byte(uuid_bytes, 6) & 15) | 112))::int);
    uuid_bytes := set_byte(uuid_bytes, 8,
        (((get_byte(uuid_bytes, 8) & 63) | 128))::int);
    RETURN encode(uuid_bytes, 'hex')::uuid;
END;
$$;

-- =========================================================================
-- updated_at trigger
-- =========================================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- =========================================================================
-- audit_log append-only enforcer
-- =========================================================================
CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only; % not allowed', TG_OP
        USING ERRCODE = 'check_violation';
END;
$$;

-- =========================================================================
-- CORE TABLES
-- =========================================================================

-- users -------------------------------------------------------------------
CREATE TABLE users (
    id                  uuid          PRIMARY KEY DEFAULT uuidv7(),
    email               citext        NOT NULL,
    password_hash       text          NOT NULL,
    email_verified_at   timestamptz   NULL,
    totp_secret         bytea         NULL,
    full_name           text          NOT NULL,
    country             char(2)       NOT NULL,
    role                varchar(16)   NOT NULL DEFAULT 'user'
                          CHECK (role IN ('user','admin')),
    created_at          timestamptz   NOT NULL DEFAULT now(),
    updated_at          timestamptz   NOT NULL DEFAULT now(),
    deleted_at          timestamptz   NULL
);

CREATE UNIQUE INDEX users_email_uniq
    ON users (email)
    WHERE deleted_at IS NULL;

CREATE INDEX users_admin_idx
    ON users (role)
    WHERE role = 'admin';

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- subscriptions -----------------------------------------------------------
CREATE TABLE subscriptions (
    id                      uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id                 uuid          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    plan                    varchar(24)   NOT NULL
                              CHECK (plan IN ('trial','pro_monthly','pro_yearly','lifetime')),
    status                  varchar(16)   NOT NULL
                              CHECK (status IN ('active','past_due','canceled','trialing')),
    stripe_subscription_id  text          NULL,
    current_period_start    timestamptz   NULL,
    current_period_end      timestamptz   NULL,
    canceled_at             timestamptz   NULL,
    created_at              timestamptz   NOT NULL DEFAULT now(),
    updated_at              timestamptz   NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX subscriptions_stripe_uniq
    ON subscriptions (stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;

CREATE INDEX subscriptions_user_status_idx
    ON subscriptions (user_id, status);

CREATE INDEX subscriptions_period_end_active_idx
    ON subscriptions (current_period_end)
    WHERE status = 'active';

CREATE TRIGGER trg_subscriptions_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- invoices ----------------------------------------------------------------
CREATE TABLE invoices (
    id                  uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id             uuid          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subscription_id     uuid          NULL REFERENCES subscriptions(id) ON DELETE RESTRICT,
    stripe_invoice_id   text          NOT NULL UNIQUE,
    amount_cents        bigint        NOT NULL CHECK (amount_cents >= 0),
    currency            char(3)       NOT NULL,
    status              varchar(16)   NOT NULL
                          CHECK (status IN ('draft','open','paid','uncollectible','void')),
    paid_at             timestamptz   NULL,
    hosted_invoice_url  text          NULL,
    created_at          timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX invoices_user_created_idx
    ON invoices (user_id, created_at DESC);

CREATE INDEX invoices_open_idx
    ON invoices (status)
    WHERE status IN ('open','uncollectible');

-- broker_accounts ---------------------------------------------------------
CREATE TABLE broker_accounts (
    id                       uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id                  uuid          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    broker                   varchar(24)   NOT NULL
                              CHECK (broker IN ('exness_mt5','binance','bybit')),
    account_label            text          NOT NULL,
    mt5_login                bigint        NULL,
    mt5_server               text          NULL,
    credentials_ciphertext   bytea         NOT NULL,
    credentials_nonce        bytea         NOT NULL,
    credentials_key_version  int           NOT NULL DEFAULT 1,
    leverage                 int           NULL CHECK (leverage IS NULL OR (leverage > 0 AND leverage <= 2000)),
    account_currency         char(3)       NULL,
    balance_cached_cents     bigint        NULL,
    last_sync_at             timestamptz   NULL,
    is_active                boolean       NOT NULL DEFAULT true,
    created_at               timestamptz   NOT NULL DEFAULT now(),
    updated_at               timestamptz   NOT NULL DEFAULT now(),
    deleted_at               timestamptz   NULL
);

CREATE UNIQUE INDEX broker_accounts_label_uniq
    ON broker_accounts (user_id, account_label)
    WHERE deleted_at IS NULL;

CREATE INDEX broker_accounts_user_active_idx
    ON broker_accounts (user_id, is_active)
    WHERE deleted_at IS NULL;

CREATE INDEX broker_accounts_key_version_idx
    ON broker_accounts (credentials_key_version);

CREATE TRIGGER trg_broker_accounts_updated_at
    BEFORE UPDATE ON broker_accounts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- strategies --------------------------------------------------------------
CREATE TABLE strategies (
    id              uuid          PRIMARY KEY DEFAULT uuidv7(),
    code            varchar(48)   NOT NULL UNIQUE
                      CHECK (code IN ('london_breakout','ny_killzone','ema_adx','ema_rsi','donchian','grid')),
    display_name    text          NOT NULL,
    asset_class     varchar(16)   NOT NULL CHECK (asset_class IN ('gold','btc')),
    default_params  jsonb         NOT NULL DEFAULT '{}'::jsonb,
    version         int           NOT NULL DEFAULT 1,
    description     text          NULL,
    risk_rating     varchar(8)    NOT NULL CHECK (risk_rating IN ('low','medium','high')),
    is_enabled      boolean       NOT NULL DEFAULT true,
    created_at      timestamptz   NOT NULL DEFAULT now(),
    updated_at      timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX strategies_enabled_idx
    ON strategies (is_enabled, asset_class)
    WHERE is_enabled = true;

CREATE TRIGGER trg_strategies_updated_at
    BEFORE UPDATE ON strategies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- strategy_instances ------------------------------------------------------
CREATE TABLE strategy_instances (
    id                       uuid           PRIMARY KEY DEFAULT uuidv7(),
    user_id                  uuid           NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    broker_account_id        uuid           NOT NULL REFERENCES broker_accounts(id) ON DELETE RESTRICT,
    strategy_id              uuid           NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    label                    text           NOT NULL,
    params                   jsonb          NOT NULL DEFAULT '{}'::jsonb,
    status                   varchar(16)    NOT NULL
                              CHECK (status IN ('paper','live','stopped','killed')),
    risk_percent             numeric(5,2)   NOT NULL
                              CHECK (risk_percent >= 0 AND risk_percent <= 10),
    max_daily_loss_cents     bigint         NOT NULL CHECK (max_daily_loss_cents >= 0),
    daily_loss_today_cents   bigint         NOT NULL DEFAULT 0,
    kill_switch_armed        boolean        NOT NULL DEFAULT true,
    last_signal_at           timestamptz    NULL,
    started_at               timestamptz    NULL,
    stopped_at               timestamptz    NULL,
    created_at               timestamptz    NOT NULL DEFAULT now(),
    updated_at               timestamptz    NOT NULL DEFAULT now(),
    deleted_at               timestamptz    NULL
);

CREATE UNIQUE INDEX strategy_instances_label_uniq
    ON strategy_instances (user_id, label)
    WHERE deleted_at IS NULL;

CREATE INDEX strategy_instances_user_status_idx
    ON strategy_instances (user_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX strategy_instances_broker_idx
    ON strategy_instances (broker_account_id)
    WHERE deleted_at IS NULL;

CREATE INDEX strategy_instances_running_idx
    ON strategy_instances (status)
    WHERE status IN ('live','paper');

CREATE TRIGGER trg_strategy_instances_updated_at
    BEFORE UPDATE ON strategy_instances
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- backtests ---------------------------------------------------------------
CREATE TABLE backtests (
    id                  uuid           PRIMARY KEY DEFAULT uuidv7(),
    user_id             uuid           NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    strategy_id         uuid           NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    asset_symbol        varchar(16)    NOT NULL,
    timeframe           varchar(8)     NOT NULL
                          CHECK (timeframe IN ('M1','M5','M15','M30','H1','H4','D1')),
    params              jsonb          NOT NULL DEFAULT '{}'::jsonb,
    start_date          date           NOT NULL,
    end_date            date           NOT NULL CHECK (end_date >= start_date),
    status              varchar(16)    NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued','running','completed','failed')),
    total_return_pct    numeric(10,4)  NULL,
    max_drawdown_pct    numeric(10,4)  NULL,
    sharpe              numeric(10,4)  NULL,
    sortino             numeric(10,4)  NULL,
    profit_factor       numeric(10,4)  NULL,
    win_rate_pct        numeric(5,2)   NULL
                          CHECK (win_rate_pct IS NULL OR (win_rate_pct >= 0 AND win_rate_pct <= 100)),
    total_trades        int            NULL CHECK (total_trades IS NULL OR total_trades >= 0),
    equity_curve_url    text           NULL,
    trades_count        int            NULL,
    started_at          timestamptz    NULL,
    completed_at        timestamptz    NULL,
    error_message       text           NULL,
    created_at          timestamptz    NOT NULL DEFAULT now()
);

CREATE INDEX backtests_user_created_idx
    ON backtests (user_id, created_at DESC);

CREATE INDEX backtests_queue_idx
    ON backtests (status, created_at)
    WHERE status IN ('queued','running');

CREATE INDEX backtests_strategy_completed_idx
    ON backtests (strategy_id, completed_at DESC)
    WHERE status = 'completed';

-- =========================================================================
-- PARTITIONED TABLES — signals
-- =========================================================================
CREATE TABLE signals (
    id                     uuid           NOT NULL DEFAULT uuidv7(),
    strategy_instance_id   uuid           NOT NULL REFERENCES strategy_instances(id) ON DELETE CASCADE,
    ts                     timestamptz    NOT NULL,
    direction              varchar(8)     NOT NULL CHECK (direction IN ('long','short')),
    price                  numeric(18,8)  NOT NULL,
    sl                     numeric(18,8)  NULL,
    tp                     numeric(18,8)  NULL,
    reason                 jsonb          NOT NULL DEFAULT '{}'::jsonb,
    status                 varchar(16)    NOT NULL
                              CHECK (status IN ('generated','sent_to_broker','filled','rejected','canceled')),
    broker_order_id        text           NULL,
    created_at             timestamptz    NOT NULL DEFAULT now(),
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);

CREATE TABLE signals_default PARTITION OF signals DEFAULT;
CREATE TABLE signals_y2026_m06 PARTITION OF signals
    FOR VALUES FROM ('2026-06-01 00:00+00') TO ('2026-07-01 00:00+00');
CREATE TABLE signals_y2026_m07 PARTITION OF signals
    FOR VALUES FROM ('2026-07-01 00:00+00') TO ('2026-08-01 00:00+00');
CREATE TABLE signals_y2026_m08 PARTITION OF signals
    FOR VALUES FROM ('2026-08-01 00:00+00') TO ('2026-09-01 00:00+00');
CREATE TABLE signals_y2026_m09 PARTITION OF signals
    FOR VALUES FROM ('2026-09-01 00:00+00') TO ('2026-10-01 00:00+00');
CREATE TABLE signals_y2026_m10 PARTITION OF signals
    FOR VALUES FROM ('2026-10-01 00:00+00') TO ('2026-11-01 00:00+00');
CREATE TABLE signals_y2026_m11 PARTITION OF signals
    FOR VALUES FROM ('2026-11-01 00:00+00') TO ('2026-12-01 00:00+00');

CREATE INDEX signals_instance_ts_idx
    ON signals (strategy_instance_id, ts DESC);

CREATE INDEX signals_status_open_idx
    ON signals (status)
    WHERE status IN ('generated','sent_to_broker');

CREATE INDEX signals_broker_order_idx
    ON signals (broker_order_id)
    WHERE broker_order_id IS NOT NULL;

-- =========================================================================
-- PARTITIONED TABLES — trades
-- =========================================================================
CREATE TABLE trades (
    id                      uuid           NOT NULL DEFAULT uuidv7(),
    strategy_instance_id    uuid           NOT NULL REFERENCES strategy_instances(id) ON DELETE RESTRICT,
    signal_id               uuid           NULL,
    broker_account_id       uuid           NOT NULL REFERENCES broker_accounts(id) ON DELETE RESTRICT,
    symbol                  varchar(16)    NOT NULL,
    side                    varchar(4)     NOT NULL CHECK (side IN ('buy','sell')),
    lot_size                numeric(10,4)  NOT NULL CHECK (lot_size > 0),
    entry_price             numeric(18,8)  NOT NULL,
    entry_at                timestamptz    NOT NULL,
    exit_price              numeric(18,8)  NULL,
    exit_at                 timestamptz    NULL,
    sl                      numeric(18,8)  NULL,
    tp                      numeric(18,8)  NULL,
    commission_cents        bigint         NOT NULL DEFAULT 0,
    swap_cents              bigint         NOT NULL DEFAULT 0,
    gross_pnl_cents         bigint         NULL,
    net_pnl_cents           bigint         NULL,
    status                  varchar(16)    NOT NULL
                              CHECK (status IN ('open','closed','canceled')),
    broker_ticket           varchar(64)    NULL,
    created_at              timestamptz    NOT NULL DEFAULT now(),
    updated_at              timestamptz    NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE trades_default PARTITION OF trades DEFAULT;
CREATE TABLE trades_y2026_m06 PARTITION OF trades
    FOR VALUES FROM ('2026-06-01 00:00+00') TO ('2026-07-01 00:00+00');
CREATE TABLE trades_y2026_m07 PARTITION OF trades
    FOR VALUES FROM ('2026-07-01 00:00+00') TO ('2026-08-01 00:00+00');
CREATE TABLE trades_y2026_m08 PARTITION OF trades
    FOR VALUES FROM ('2026-08-01 00:00+00') TO ('2026-09-01 00:00+00');
CREATE TABLE trades_y2026_m09 PARTITION OF trades
    FOR VALUES FROM ('2026-09-01 00:00+00') TO ('2026-10-01 00:00+00');
CREATE TABLE trades_y2026_m10 PARTITION OF trades
    FOR VALUES FROM ('2026-10-01 00:00+00') TO ('2026-11-01 00:00+00');
CREATE TABLE trades_y2026_m11 PARTITION OF trades
    FOR VALUES FROM ('2026-11-01 00:00+00') TO ('2026-12-01 00:00+00');

CREATE INDEX trades_instance_status_entry_idx
    ON trades (strategy_instance_id, status, entry_at DESC);

CREATE UNIQUE INDEX trades_broker_ticket_uniq
    ON trades (broker_account_id, broker_ticket)
    WHERE broker_ticket IS NOT NULL;

CREATE INDEX trades_signal_idx
    ON trades (signal_id)
    WHERE signal_id IS NOT NULL;

CREATE INDEX trades_open_idx
    ON trades (strategy_instance_id)
    WHERE status = 'open';

CREATE TRIGGER trg_trades_updated_at
    BEFORE UPDATE ON trades
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================================
-- OPERATIONAL — mt5_terminal_pool
-- =========================================================================
CREATE TABLE mt5_terminal_pool (
    id                 uuid           PRIMARY KEY DEFAULT uuidv7(),
    host_id            text           NOT NULL,
    status             varchar(16)    NOT NULL
                        CHECK (status IN ('free','assigned','unhealthy')),
    assigned_user_id   uuid           NULL REFERENCES users(id) ON DELETE SET NULL,
    mt5_process_id     int            NULL,
    mt5_port           int            NULL
                        CHECK (mt5_port IS NULL OR (mt5_port > 0 AND mt5_port < 65536)),
    last_heartbeat_at  timestamptz    NULL,
    created_at         timestamptz    NOT NULL DEFAULT now(),
    updated_at         timestamptz    NOT NULL DEFAULT now()
);

CREATE INDEX mt5_pool_free_idx
    ON mt5_terminal_pool (status)
    WHERE status = 'free';

CREATE UNIQUE INDEX mt5_pool_assigned_user_uniq
    ON mt5_terminal_pool (assigned_user_id)
    WHERE assigned_user_id IS NOT NULL;

CREATE INDEX mt5_pool_heartbeat_idx
    ON mt5_terminal_pool (last_heartbeat_at)
    WHERE status = 'assigned';

CREATE TRIGGER trg_mt5_terminal_pool_updated_at
    BEFORE UPDATE ON mt5_terminal_pool
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================================
-- audit_log (partitioned, append-only)
-- =========================================================================
CREATE TABLE audit_log (
    id                 uuid           NOT NULL DEFAULT uuidv7(),
    actor_user_id      uuid           NULL REFERENCES users(id) ON DELETE SET NULL,
    action             varchar(64)    NOT NULL,
    target_type        varchar(32)    NULL,
    target_id          uuid           NULL,
    payload_redacted   jsonb          NOT NULL DEFAULT '{}'::jsonb,
    ip_addr            inet           NULL,
    user_agent         text           NULL,
    created_at         timestamptz    NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT;
CREATE TABLE audit_log_y2026_m06 PARTITION OF audit_log
    FOR VALUES FROM ('2026-06-01 00:00+00') TO ('2026-07-01 00:00+00');
CREATE TABLE audit_log_y2026_m07 PARTITION OF audit_log
    FOR VALUES FROM ('2026-07-01 00:00+00') TO ('2026-08-01 00:00+00');
CREATE TABLE audit_log_y2026_m08 PARTITION OF audit_log
    FOR VALUES FROM ('2026-08-01 00:00+00') TO ('2026-09-01 00:00+00');
CREATE TABLE audit_log_y2026_m09 PARTITION OF audit_log
    FOR VALUES FROM ('2026-09-01 00:00+00') TO ('2026-10-01 00:00+00');
CREATE TABLE audit_log_y2026_m10 PARTITION OF audit_log
    FOR VALUES FROM ('2026-10-01 00:00+00') TO ('2026-11-01 00:00+00');
CREATE TABLE audit_log_y2026_m11 PARTITION OF audit_log
    FOR VALUES FROM ('2026-11-01 00:00+00') TO ('2026-12-01 00:00+00');

CREATE INDEX audit_actor_created_idx
    ON audit_log (actor_user_id, created_at DESC);

CREATE INDEX audit_action_created_idx
    ON audit_log (action, created_at DESC);

CREATE INDEX audit_target_idx
    ON audit_log (target_type, target_id)
    WHERE target_id IS NOT NULL;

-- Append-only enforcement at parent: attaches to each partition.
CREATE TRIGGER trg_audit_no_update
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();

-- =========================================================================
-- api_keys
-- =========================================================================
CREATE TABLE api_keys (
    id            uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id       uuid          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label         text          NOT NULL,
    key_hash      bytea         NOT NULL UNIQUE,
    last_used_at  timestamptz   NULL,
    expires_at    timestamptz   NULL,
    revoked_at    timestamptz   NULL,
    created_at    timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX api_keys_user_active_idx
    ON api_keys (user_id, revoked_at, expires_at);

-- =========================================================================
-- notifications
-- =========================================================================
CREATE TABLE notifications (
    id         uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id    uuid          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel    varchar(16)   NOT NULL CHECK (channel IN ('email','push','inapp')),
    kind       varchar(48)   NOT NULL,
    payload    jsonb         NOT NULL DEFAULT '{}'::jsonb,
    sent_at    timestamptz   NULL,
    read_at    timestamptz   NULL,
    created_at timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX notifications_user_unread_idx
    ON notifications (user_id, created_at DESC)
    WHERE read_at IS NULL;

CREATE INDEX notifications_user_created_idx
    ON notifications (user_id, created_at DESC);
"""


# ---------------------------------------------------------------------------
# DOWNGRADE — explicit, ordered, destructive.
# Reverses upgrade in dependency-safe order.
# ---------------------------------------------------------------------------
DOWNGRADE_SQL = r"""
-- Drop child tables first (FK fan-in), then parents, then partitioned, then funcs/extensions.
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS api_keys CASCADE;

-- audit_log partitions
DROP TABLE IF EXISTS audit_log CASCADE;

-- mt5
DROP TABLE IF EXISTS mt5_terminal_pool CASCADE;

-- trades partitions
DROP TABLE IF EXISTS trades CASCADE;

-- signals partitions
DROP TABLE IF EXISTS signals CASCADE;

-- backtests / strategies graph
DROP TABLE IF EXISTS backtests CASCADE;
DROP TABLE IF EXISTS strategy_instances CASCADE;
DROP TABLE IF EXISTS strategies CASCADE;

-- billing
DROP TABLE IF EXISTS invoices CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;

-- brokers
DROP TABLE IF EXISTS broker_accounts CASCADE;

-- users last
DROP TABLE IF EXISTS users CASCADE;

-- Functions
DROP FUNCTION IF EXISTS prevent_audit_mutation();
DROP FUNCTION IF EXISTS set_updated_at();
DROP FUNCTION IF EXISTS uuidv7();

-- Extensions — keep citext + pgcrypto if other migrations or apps depend on them.
-- We intentionally do NOT drop them here. Uncomment in a true wipe scenario.
-- DROP EXTENSION IF EXISTS "uuid-ossp";
-- DROP EXTENSION IF EXISTS citext;
-- DROP EXTENSION IF EXISTS pgcrypto;
"""


def upgrade() -> None:
    op.execute(sa.text(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(sa.text(DOWNGRADE_SQL))
