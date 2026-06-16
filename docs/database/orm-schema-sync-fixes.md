# ORM ↔ Schema Sync Fixes (Atlas's TODO)

**Author:** Mnemosyne Rin
**Round:** R3 Phase 2
**Date:** 2026-06-15

Cross-team note for **Atlas Goro** (backend). I (Rin) own `schema.sql` and the
migrations; Atlas owns `app/models/*.py`. This document tracks every column
where ORM still drifts from the canonical schema and tells Atlas exactly
what to change in the models.

Rule: **the canonical schema is the SQL in migration 0001 + 0003**. ORM
models must conform. I will NOT fix this via ALTER unless we explicitly
decide to change the canonical schema.

---

## Drift identified at end of R2 and confirmed at R3

### users (model: `app/models/user.py`)

Atlas's model is already aligned to the canonical shape (`role`,
`email_verified_at`, `totp_secret`). No drift remaining at column level.

**Phase-2 additions to add to the model:**

```python
onboarding_step: Mapped[int] = mapped_column(
    Integer, nullable=False, server_default=text("0")
)
stripe_customer_id: Mapped[str | None] = mapped_column(
    String(64), nullable=True
)
consent_marketing_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

Migration 0003 already adds these columns with safe defaults — Atlas just
needs to expose them on the model so the API can read/write.

---

### subscriptions (model: `app/models/subscription.py`)

**Phase-2 addition:** `plan_id` (nullable FK to `plans.id`).

```python
plan_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("plans.id", ondelete="RESTRICT"),
    nullable=True,
)
```

**Important — expand/contract is in progress:**
- Both `plan` (varchar) and `plan_id` (uuid FK) coexist during Phase 2.
- New writes MUST populate **both** columns.
- After backfill, Phase 3 will tighten `plan_id` to `NOT NULL` and drop `plan`.

Add a `Plan` model (`app/models/plan.py`) mapped to the new `plans` table.
See schema in migration 0003 (columns: `code`, `display_name`,
`stripe_product_id`, `stripe_price_id`, `price_cents`, `currency`,
`interval`, `max_strategy_instances`, `max_broker_accounts`,
`max_concurrent_live`, `features` JSONB, `is_visible`, `sort_order`,
`created_at`).

---

### broker_accounts (model: `app/models/broker_account.py`)

**Phase-2 addition:** `mt5_bridge_id` (nullable FK to `mt5_bridges.id`).

```python
mt5_bridge_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("mt5_bridges.id", ondelete="SET NULL"),
    nullable=True,
)
```

Add a `Mt5Bridge` model (`app/models/mt5_bridge.py`). Schema in 0003.

---

### strategy_instances (model: `app/models/strategy_instance.py`)

**Phase-2 additions:**

```python
live_engine_pid: Mapped[str | None] = mapped_column(String(64), nullable=True)
last_heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

---

## New models Atlas must add

For each new table from migration 0003, Atlas should add a model file under
`app/models/`. Suggested filenames:

| Table                 | Suggested model file              |
|-----------------------|------------------------------------|
| `plans`               | `app/models/plan.py`              |
| `stripe_events`       | `app/models/stripe_event.py`      |
| `email_verifications` | `app/models/email_verification.py`|
| `password_resets`     | `app/models/password_reset.py`    |
| `consents`            | `app/models/consent.py`           |
| `live_consents`       | `app/models/live_consent.py`      |
| `live_gate_checks`    | `app/models/live_gate_check.py`   |
| `mt5_bridges`         | `app/models/mt5_bridge.py`        |
| `email_outbox`        | `app/models/email_outbox.py`      |
| `webhook_inbox`       | `app/models/webhook_inbox.py`     |
| `account_exports`     | `app/models/account_export.py`    |
| `account_deletions`   | `app/models/account_deletion.py`  |
| `live_engine_runs`    | `app/models/live_engine_run.py`   |

Don't forget to re-export from `app/models/__init__.py` so `env.py` picks
them up for autogenerate diffs.

---

## Partitioned-table modeling rule (refresh)

For `email_outbox` and `webhook_inbox`, declare the model normally but
remember:
- **PK is composite** `(id, created_at)` / `(id, received_at)`.
- Mark both columns `primary_key=True` in the model.
- Don't try to model the partition children — they're invisible to the ORM.

```python
class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          server_default=text("uuidv7()"))
    created_at: Mapped[datetime] = mapped_column(primary_key=True,
                                                 server_default=text("now()"))
    # ... other columns
```

---

## Why I don't fix this via ALTER

If I ALTER columns to "match" Atlas's ORM, the ER diagram and `schema.sql`
also need to change, and we'd be moving the canonical contract for code
convenience. The contract was reviewed and signed off — convenience moves
to the ORM. Same reasoning that drove R2 decision #2.

If a column genuinely belongs in a different shape (e.g., new product
requirement), open a discussion + ADR, and I'll ship an expand-contract
migration. Don't sneak it in via "fix drift."

---

## Verification checklist (for Atlas's PR)

- [ ] All models updated with Phase-2 columns
- [ ] All new models added + re-exported from `__init__.py`
- [ ] `pytest -k test_alembic_round_trip` still green (no autogen diffs)
- [ ] `pytest -k test_model_schema_alignment` (if it exists) green
- [ ] Spot-check: `python -c "from app.models import *"` raises nothing

If the round-trip test isn't in place yet, that's R3-followup #2 from my
R2 notes — Atlas + I can pair on it.
