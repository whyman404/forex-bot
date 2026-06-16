"""seed plans catalog — 4 default plans (trial, pro_monthly, pro_yearly, lifetime)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-15

Mnemosyne Rin — data migration.

Idempotent via INSERT ... ON CONFLICT (code) DO UPDATE.
We DO update display_name, features, limits, price_cents, sort_order on
conflict — this lets us re-run as the marketing copy / limits evolve.
We DO NOT touch stripe_product_id / stripe_price_id on conflict — those
are filled by backend/scripts/stripe_setup.py against the live Stripe
account (idempotency boundary is Stripe's).
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Pinned plan catalog as of 2026-06-15. To change pricing/limits, ship a NEW
# migration — do not edit this dict.
PLANS: list[dict] = [
    {
        "code": "trial",
        "display_name": "14-day Trial",
        "price_cents": 0,
        "currency": "USD",
        "interval": "month",  # interval not meaningful for free trial, but enum forces a value
        "max_strategy_instances": 1,
        "max_broker_accounts": 1,
        "max_concurrent_live": 0,
        "features": {
            "trial_days": 14,
            "backtests_per_day": 5,
            "paper_only": True,
            "support": "community",
        },
        "is_visible": True,
        "sort_order": 10,
    },
    {
        "code": "pro_monthly",
        "display_name": "Pro Monthly",
        "price_cents": 2900,  # $29.00
        "currency": "USD",
        "interval": "month",
        "max_strategy_instances": 6,
        "max_broker_accounts": 2,
        "max_concurrent_live": 2,
        "features": {
            "backtests_per_day": 100,
            "paper_only": False,
            "support": "email",
            "killswitch_drill": True,
        },
        "is_visible": True,
        "sort_order": 20,
    },
    {
        "code": "pro_yearly",
        "display_name": "Pro Yearly (17% off)",
        "price_cents": 29000,  # $290.00 vs $348 monthly = ~17% saving
        "currency": "USD",
        "interval": "year",
        "max_strategy_instances": 6,
        "max_broker_accounts": 2,
        "max_concurrent_live": 2,
        "features": {
            "backtests_per_day": 100,
            "paper_only": False,
            "support": "email",
            "killswitch_drill": True,
            "yearly_savings_pct": 17,
        },
        "is_visible": True,
        "sort_order": 30,
    },
    {
        "code": "lifetime",
        "display_name": "Lifetime",
        "price_cents": 99000,  # $990.00 one-time
        "currency": "USD",
        "interval": "one_time",
        "max_strategy_instances": 6,
        "max_broker_accounts": 3,
        "max_concurrent_live": 4,
        "features": {
            "backtests_per_day": 200,
            "paper_only": False,
            "support": "priority_email",
            "killswitch_drill": True,
            "early_access_features": True,
        },
        "is_visible": True,
        "sort_order": 40,
    },
]


UPSERT_SQL = sa.text(
    """
    INSERT INTO plans (
        code, display_name, stripe_product_id, stripe_price_id,
        price_cents, currency, interval,
        max_strategy_instances, max_broker_accounts, max_concurrent_live,
        features, is_visible, sort_order
    ) VALUES (
        :code, :display_name, NULL, NULL,
        :price_cents, :currency, :interval,
        :max_strategy_instances, :max_broker_accounts, :max_concurrent_live,
        CAST(:features AS jsonb), :is_visible, :sort_order
    )
    ON CONFLICT (code) DO UPDATE
        SET display_name           = EXCLUDED.display_name,
            price_cents            = EXCLUDED.price_cents,
            currency               = EXCLUDED.currency,
            interval               = EXCLUDED.interval,
            max_strategy_instances = EXCLUDED.max_strategy_instances,
            max_broker_accounts    = EXCLUDED.max_broker_accounts,
            max_concurrent_live    = EXCLUDED.max_concurrent_live,
            features               = EXCLUDED.features,
            is_visible             = EXCLUDED.is_visible,
            sort_order             = EXCLUDED.sort_order
        -- intentionally NOT touching stripe_product_id / stripe_price_id
        ;
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    for plan in PLANS:
        bind.execute(
            UPSERT_SQL,
            {
                "code": plan["code"],
                "display_name": plan["display_name"],
                "price_cents": plan["price_cents"],
                "currency": plan["currency"],
                "interval": plan["interval"],
                "max_strategy_instances": plan["max_strategy_instances"],
                "max_broker_accounts": plan["max_broker_accounts"],
                "max_concurrent_live": plan["max_concurrent_live"],
                "features": json.dumps(plan["features"]),
                "is_visible": plan["is_visible"],
                "sort_order": plan["sort_order"],
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    codes = tuple(p["code"] for p in PLANS)
    # Best-effort: only delete if no subscription points at the plan.
    # If anything is referencing the row, leave it (RESTRICT will raise).
    bind.execute(
        sa.text(
            "DELETE FROM plans WHERE code = ANY(:codes) "
            "AND id NOT IN (SELECT plan_id FROM subscriptions WHERE plan_id IS NOT NULL);"
        ),
        {"codes": list(codes)},
    )
