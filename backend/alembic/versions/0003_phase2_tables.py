"""phase 2 — billing, consents, ops tables + additive columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15

Mnemosyne Rin — Phase 2 deliverable.

Design rules (expand-contract):
  * additive ONLY. No DROP, no RENAME, no type narrowing.
  * every new column on existing tables is nullable OR has a server default.
  * every new table created with IF NOT EXISTS so the migration is idempotent.
  * partition setup mirrors signals/trades pattern (RANGE on month, default
    partition as safety net, 6 init partitions m06..m11/2026).
  * indexes use partial/GIN where appropriate to keep write penalty bounded.

Downgrade: only drops the objects this migration creates. Existing data on
augmented tables (users, subscriptions, broker_accounts, strategy_instances)
remains untouched on downgrade because we only drop the *added* columns.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# UPGRADE
# ---------------------------------------------------------------------------
UPGRADE_SQL = r"""
-- =========================================================================
-- Phase 2 :: NEW TABLES (idempotent — IF NOT EXISTS)
-- =========================================================================

-- plans -------------------------------------------------------------------
-- Replaces the implicit enum on subscriptions.plan with a real lookup table.
-- We DO NOT remove subscriptions.plan in this migration (expand phase).
-- A future contract migration can drop it once all writers populate plan_id.
CREATE TABLE IF NOT EXISTS plans (
    id                          uuid          PRIMARY KEY DEFAULT uuidv7(),
    code                        varchar(24)   NOT NULL UNIQUE
                                  CHECK (code IN ('trial','pro_monthly','pro_yearly','lifetime')),
    display_name                text          NOT NULL,
    stripe_product_id           text          NULL,
    stripe_price_id             text          NULL,
    price_cents                 bigint        NOT NULL CHECK (price_cents >= 0),
    currency                    char(3)       NOT NULL DEFAULT 'USD',
    interval                    varchar(16)   NOT NULL
                                  CHECK (interval IN ('month','year','one_time')),
    max_strategy_instances      int           NOT NULL CHECK (max_strategy_instances >= 0),
    max_broker_accounts         int           NOT NULL CHECK (max_broker_accounts >= 0),
    max_concurrent_live         int           NOT NULL CHECK (max_concurrent_live >= 0),
    features                    jsonb         NOT NULL DEFAULT '{}'::jsonb,
    is_visible                  boolean       NOT NULL DEFAULT true,
    sort_order                  int           NOT NULL DEFAULT 0,
    created_at                  timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS plans_visible_sort_idx
    ON plans (is_visible, sort_order)
    WHERE is_visible = true;

CREATE UNIQUE INDEX IF NOT EXISTS plans_stripe_price_uniq
    ON plans (stripe_price_id)
    WHERE stripe_price_id IS NOT NULL;


-- stripe_events -----------------------------------------------------------
-- Idempotency table for Stripe webhook deduplication.
-- Insert on receive; UNIQUE on stripe_event_id is the dedup contract.
CREATE TABLE IF NOT EXISTS stripe_events (
    id                  uuid          PRIMARY KEY DEFAULT uuidv7(),
    stripe_event_id     text          NOT NULL UNIQUE,
    event_type          varchar(64)   NOT NULL,
    processed_at        timestamptz   NULL,
    payload             jsonb         NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS stripe_events_unprocessed_idx
    ON stripe_events (event_type, created_at)
    WHERE processed_at IS NULL;

-- GIN on payload — supports admin queries / debugging webhook bodies.
CREATE INDEX IF NOT EXISTS stripe_events_payload_gin
    ON stripe_events
    USING GIN (payload jsonb_path_ops);


-- email_verifications -----------------------------------------------------
CREATE TABLE IF NOT EXISTS email_verifications (
    id             uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id        uuid          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash     text          NOT NULL,
    expires_at     timestamptz   NOT NULL,
    used_at        timestamptz   NULL,
    created_at     timestamptz   NOT NULL DEFAULT now()
);

-- token_hash MUST be globally unique (the secret index). Lookup by hash is
-- the hot path. Unique btree is fine; this stays small (TTL-pruned).
CREATE UNIQUE INDEX IF NOT EXISTS email_verifications_token_hash_uniq
    ON email_verifications (token_hash);

CREATE INDEX IF NOT EXISTS email_verifications_user_active_idx
    ON email_verifications (user_id, created_at DESC)
    WHERE used_at IS NULL;

CREATE INDEX IF NOT EXISTS email_verifications_expiry_idx
    ON email_verifications (expires_at)
    WHERE used_at IS NULL;


-- password_resets ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS password_resets (
    id             uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id        uuid          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash     text          NOT NULL,
    expires_at     timestamptz   NOT NULL,
    used_at        timestamptz   NULL,
    created_at     timestamptz   NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS password_resets_token_hash_uniq
    ON password_resets (token_hash);

CREATE INDEX IF NOT EXISTS password_resets_user_active_idx
    ON password_resets (user_id, created_at DESC)
    WHERE used_at IS NULL;

CREATE INDEX IF NOT EXISTS password_resets_expiry_idx
    ON password_resets (expires_at)
    WHERE used_at IS NULL;


-- consents ----------------------------------------------------------------
-- Generic consent register (ToS, privacy, marketing, data processing).
-- One row per (user, kind, version) event — never UPDATE; only INSERT.
CREATE TABLE IF NOT EXISTS consents (
    id              uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id         uuid          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    kind            varchar(24)   NOT NULL
                      CHECK (kind IN ('tos','privacy','marketing','data_processing')),
    version         varchar(16)   NOT NULL,
    agreed_at       timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS consents_user_kind_idx
    ON consents (user_id, kind, agreed_at DESC);


-- live_consents -----------------------------------------------------------
-- Specific "go live" acknowledgement per strategy code, captured at sign-time
-- with IP + UA for legal traceability. Never updated.
CREATE TABLE IF NOT EXISTS live_consents (
    id                   uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id              uuid          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    strategy_code        varchar(48)   NOT NULL,
    version              varchar(16)   NOT NULL,
    risk_acknowledged    boolean       NOT NULL,
    ip_addr              inet          NULL,
    user_agent           text          NULL,
    signed_at            timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS live_consents_user_strategy_idx
    ON live_consents (user_id, strategy_code, signed_at DESC);


-- live_gate_checks --------------------------------------------------------
-- Audit trail of the live-gate evaluations (paper -> live transition).
CREATE TABLE IF NOT EXISTS live_gate_checks (
    id                       uuid          PRIMARY KEY DEFAULT uuidv7(),
    strategy_instance_id     uuid          NOT NULL REFERENCES strategy_instances(id) ON DELETE CASCADE,
    checked_at               timestamptz   NOT NULL DEFAULT now(),
    result                   varchar(16)   NOT NULL CHECK (result IN ('passed','failed')),
    checks_json              jsonb         NOT NULL DEFAULT '{}'::jsonb,
    evaluator                text          NULL
);

CREATE INDEX IF NOT EXISTS live_gate_checks_instance_idx
    ON live_gate_checks (strategy_instance_id, checked_at DESC);

CREATE INDEX IF NOT EXISTS live_gate_checks_failed_idx
    ON live_gate_checks (strategy_instance_id, checked_at DESC)
    WHERE result = 'failed';


-- mt5_bridges -------------------------------------------------------------
-- User-managed MT5 bridge endpoints (self-hosted) — separate from the
-- hosted mt5_terminal_pool. Encryption: same envelope pattern (ADR-005).
CREATE TABLE IF NOT EXISTS mt5_bridges (
    id                          uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id                     uuid          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    label                       text          NOT NULL,
    bridge_url                  text          NOT NULL,
    bridge_token_ciphertext     bytea         NOT NULL,
    bridge_token_nonce          bytea         NOT NULL,
    bridge_token_key_version    int           NOT NULL DEFAULT 1,
    last_heartbeat_at           timestamptz   NULL,
    status                      varchar(16)   NOT NULL DEFAULT 'unknown'
                                  CHECK (status IN ('unknown','healthy','degraded','down')),
    host_info                   jsonb         NOT NULL DEFAULT '{}'::jsonb,
    created_at                  timestamptz   NOT NULL DEFAULT now(),
    updated_at                  timestamptz   NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS mt5_bridges_user_label_uniq
    ON mt5_bridges (user_id, label);

CREATE INDEX IF NOT EXISTS mt5_bridges_user_status_idx
    ON mt5_bridges (user_id, status);

CREATE INDEX IF NOT EXISTS mt5_bridges_heartbeat_idx
    ON mt5_bridges (last_heartbeat_at)
    WHERE status IN ('healthy','degraded');

DROP TRIGGER IF EXISTS trg_mt5_bridges_updated_at ON mt5_bridges;
CREATE TRIGGER trg_mt5_bridges_updated_at
    BEFORE UPDATE ON mt5_bridges
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- email_outbox (partitioned by month) -------------------------------------
-- Outgoing transactional email queue. Written by app, drained by worker.
CREATE TABLE IF NOT EXISTS email_outbox (
    id              uuid          NOT NULL DEFAULT uuidv7(),
    to_email        citext        NOT NULL,
    kind            varchar(48)   NOT NULL,
    payload         jsonb         NOT NULL DEFAULT '{}'::jsonb,
    status          varchar(16)   NOT NULL DEFAULT 'queued'
                      CHECK (status IN ('queued','sent','failed','bounced')),
    sent_at         timestamptz   NULL,
    error_message   text          NULL,
    created_at      timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE IF NOT EXISTS email_outbox_default PARTITION OF email_outbox DEFAULT;
CREATE TABLE IF NOT EXISTS email_outbox_y2026_m06 PARTITION OF email_outbox
    FOR VALUES FROM ('2026-06-01 00:00+00') TO ('2026-07-01 00:00+00');
CREATE TABLE IF NOT EXISTS email_outbox_y2026_m07 PARTITION OF email_outbox
    FOR VALUES FROM ('2026-07-01 00:00+00') TO ('2026-08-01 00:00+00');
CREATE TABLE IF NOT EXISTS email_outbox_y2026_m08 PARTITION OF email_outbox
    FOR VALUES FROM ('2026-08-01 00:00+00') TO ('2026-09-01 00:00+00');
CREATE TABLE IF NOT EXISTS email_outbox_y2026_m09 PARTITION OF email_outbox
    FOR VALUES FROM ('2026-09-01 00:00+00') TO ('2026-10-01 00:00+00');
CREATE TABLE IF NOT EXISTS email_outbox_y2026_m10 PARTITION OF email_outbox
    FOR VALUES FROM ('2026-10-01 00:00+00') TO ('2026-11-01 00:00+00');
CREATE TABLE IF NOT EXISTS email_outbox_y2026_m11 PARTITION OF email_outbox
    FOR VALUES FROM ('2026-11-01 00:00+00') TO ('2026-12-01 00:00+00');

-- Partial index on queue — the only hot read path; size stays tiny
-- because rows graduate to 'sent' quickly.
CREATE INDEX IF NOT EXISTS email_outbox_queue_idx
    ON email_outbox (created_at)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS email_outbox_to_email_idx
    ON email_outbox (to_email, created_at DESC);

CREATE INDEX IF NOT EXISTS email_outbox_failed_idx
    ON email_outbox (created_at DESC)
    WHERE status IN ('failed','bounced');


-- webhook_inbox (partitioned by month) ------------------------------------
-- All inbound webhooks, raw — for audit + replay. Source-agnostic.
CREATE TABLE IF NOT EXISTS webhook_inbox (
    id              uuid          NOT NULL DEFAULT uuidv7(),
    source          varchar(24)   NOT NULL
                      CHECK (source IN ('stripe','resend','internal')),
    event_id        text          NULL,
    raw_payload     jsonb         NOT NULL DEFAULT '{}'::jsonb,
    processed       boolean       NOT NULL DEFAULT false,
    processed_at    timestamptz   NULL,
    error_message   text          NULL,
    received_at     timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (id, received_at)
) PARTITION BY RANGE (received_at);

CREATE TABLE IF NOT EXISTS webhook_inbox_default PARTITION OF webhook_inbox DEFAULT;
CREATE TABLE IF NOT EXISTS webhook_inbox_y2026_m06 PARTITION OF webhook_inbox
    FOR VALUES FROM ('2026-06-01 00:00+00') TO ('2026-07-01 00:00+00');
CREATE TABLE IF NOT EXISTS webhook_inbox_y2026_m07 PARTITION OF webhook_inbox
    FOR VALUES FROM ('2026-07-01 00:00+00') TO ('2026-08-01 00:00+00');
CREATE TABLE IF NOT EXISTS webhook_inbox_y2026_m08 PARTITION OF webhook_inbox
    FOR VALUES FROM ('2026-08-01 00:00+00') TO ('2026-09-01 00:00+00');
CREATE TABLE IF NOT EXISTS webhook_inbox_y2026_m09 PARTITION OF webhook_inbox
    FOR VALUES FROM ('2026-09-01 00:00+00') TO ('2026-10-01 00:00+00');
CREATE TABLE IF NOT EXISTS webhook_inbox_y2026_m10 PARTITION OF webhook_inbox
    FOR VALUES FROM ('2026-10-01 00:00+00') TO ('2026-11-01 00:00+00');
CREATE TABLE IF NOT EXISTS webhook_inbox_y2026_m11 PARTITION OF webhook_inbox
    FOR VALUES FROM ('2026-11-01 00:00+00') TO ('2026-12-01 00:00+00');

CREATE INDEX IF NOT EXISTS webhook_inbox_unprocessed_idx
    ON webhook_inbox (source, received_at)
    WHERE processed = false;

-- Source + event_id is the natural dedup key. Indexed (not unique — partitions
-- can't enforce unique without including the partition key).
CREATE INDEX IF NOT EXISTS webhook_inbox_source_event_idx
    ON webhook_inbox (source, event_id)
    WHERE event_id IS NOT NULL;


-- account_exports ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_exports (
    id              uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id         uuid          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status          varchar(16)   NOT NULL DEFAULT 'queued'
                      CHECK (status IN ('queued','running','ready','expired','failed')),
    download_url    text          NULL,
    expires_at      timestamptz   NULL,
    created_at      timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS account_exports_user_idx
    ON account_exports (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS account_exports_active_idx
    ON account_exports (status, created_at)
    WHERE status IN ('queued','running','ready');


-- account_deletions -------------------------------------------------------
-- One open request per user (enforced by partial unique below).
CREATE TABLE IF NOT EXISTS account_deletions (
    id                      uuid          PRIMARY KEY DEFAULT uuidv7(),
    user_id                 uuid          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    requested_at            timestamptz   NOT NULL DEFAULT now(),
    scheduled_purge_at      timestamptz   NOT NULL,
    canceled_at             timestamptz   NULL,
    purged_at               timestamptz   NULL
);

-- A user can only have ONE open (not canceled, not purged) deletion request.
CREATE UNIQUE INDEX IF NOT EXISTS account_deletions_user_open_uniq
    ON account_deletions (user_id)
    WHERE canceled_at IS NULL AND purged_at IS NULL;

CREATE INDEX IF NOT EXISTS account_deletions_due_idx
    ON account_deletions (scheduled_purge_at)
    WHERE canceled_at IS NULL AND purged_at IS NULL;


-- live_engine_runs --------------------------------------------------------
-- Operational history of live-engine sessions per strategy instance.
CREATE TABLE IF NOT EXISTS live_engine_runs (
    id                          uuid          PRIMARY KEY DEFAULT uuidv7(),
    strategy_instance_id        uuid          NOT NULL REFERENCES strategy_instances(id) ON DELETE CASCADE,
    started_at                  timestamptz   NOT NULL DEFAULT now(),
    stopped_at                  timestamptz   NULL,
    stop_reason                 varchar(48)   NULL,
    total_signals               int           NOT NULL DEFAULT 0,
    total_trades                int           NOT NULL DEFAULT 0,
    realized_pnl_cents          bigint        NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS live_engine_runs_instance_started_idx
    ON live_engine_runs (strategy_instance_id, started_at DESC);

CREATE INDEX IF NOT EXISTS live_engine_runs_open_idx
    ON live_engine_runs (strategy_instance_id)
    WHERE stopped_at IS NULL;


-- =========================================================================
-- Phase 2 :: ADDITIVE COLUMNS on existing tables
-- =========================================================================

-- users -------------------------------------------------------------------
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS onboarding_step       int           NOT NULL DEFAULT 0;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS stripe_customer_id    varchar(64)   NULL;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS consent_marketing_at  timestamptz   NULL;

CREATE UNIQUE INDEX IF NOT EXISTS users_stripe_customer_uniq
    ON users (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;


-- subscriptions -----------------------------------------------------------
-- plan_id is nullable for backward compat. The Phase-2 backfill populates
-- it for every existing row. A future migration (Phase 3) can set NOT NULL
-- once writers go through plan_id.
ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS plan_id  uuid  NULL REFERENCES plans(id) ON DELETE RESTRICT;

-- composite (user_id, status) already exists from 0001 (subscriptions_user_status_idx).
-- Re-create as IF NOT EXISTS to be explicit and idempotent.
CREATE INDEX IF NOT EXISTS subscriptions_user_status_idx
    ON subscriptions (user_id, status);

CREATE INDEX IF NOT EXISTS subscriptions_plan_id_idx
    ON subscriptions (plan_id)
    WHERE plan_id IS NOT NULL;


-- strategy_instances ------------------------------------------------------
ALTER TABLE strategy_instances
    ADD COLUMN IF NOT EXISTS live_engine_pid     varchar(64)  NULL;
ALTER TABLE strategy_instances
    ADD COLUMN IF NOT EXISTS last_heartbeat_at   timestamptz  NULL;

CREATE INDEX IF NOT EXISTS strategy_instances_heartbeat_idx
    ON strategy_instances (last_heartbeat_at)
    WHERE status IN ('live','paper');


-- broker_accounts ---------------------------------------------------------
ALTER TABLE broker_accounts
    ADD COLUMN IF NOT EXISTS mt5_bridge_id  uuid  NULL
        REFERENCES mt5_bridges(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS broker_accounts_mt5_bridge_idx
    ON broker_accounts (mt5_bridge_id)
    WHERE mt5_bridge_id IS NOT NULL;
"""


# ---------------------------------------------------------------------------
# DOWNGRADE — drops only what this migration created (safe, additive reversal)
# ---------------------------------------------------------------------------
DOWNGRADE_SQL = r"""
-- Drop indexes added to existing tables first (avoid orphan refs).
DROP INDEX IF EXISTS broker_accounts_mt5_bridge_idx;
DROP INDEX IF EXISTS strategy_instances_heartbeat_idx;
DROP INDEX IF EXISTS subscriptions_plan_id_idx;
DROP INDEX IF EXISTS users_stripe_customer_uniq;

-- Drop columns added to existing tables.
ALTER TABLE broker_accounts     DROP COLUMN IF EXISTS mt5_bridge_id;
ALTER TABLE strategy_instances  DROP COLUMN IF EXISTS last_heartbeat_at;
ALTER TABLE strategy_instances  DROP COLUMN IF EXISTS live_engine_pid;
ALTER TABLE subscriptions       DROP COLUMN IF EXISTS plan_id;
ALTER TABLE users               DROP COLUMN IF EXISTS consent_marketing_at;
ALTER TABLE users               DROP COLUMN IF EXISTS stripe_customer_id;
ALTER TABLE users               DROP COLUMN IF EXISTS onboarding_step;

-- Drop new tables. Order: dependents first.
DROP TABLE IF EXISTS live_engine_runs       CASCADE;
DROP TABLE IF EXISTS account_deletions      CASCADE;
DROP TABLE IF EXISTS account_exports        CASCADE;
DROP TABLE IF EXISTS webhook_inbox          CASCADE;
DROP TABLE IF EXISTS email_outbox           CASCADE;
DROP TRIGGER IF EXISTS trg_mt5_bridges_updated_at ON mt5_bridges;
DROP TABLE IF EXISTS mt5_bridges            CASCADE;
DROP TABLE IF EXISTS live_gate_checks       CASCADE;
DROP TABLE IF EXISTS live_consents          CASCADE;
DROP TABLE IF EXISTS consents               CASCADE;
DROP TABLE IF EXISTS password_resets        CASCADE;
DROP TABLE IF EXISTS email_verifications    CASCADE;
DROP TABLE IF EXISTS stripe_events          CASCADE;
DROP TABLE IF EXISTS plans                  CASCADE;
"""


def upgrade() -> None:
    op.execute(sa.text(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(sa.text(DOWNGRADE_SQL))
