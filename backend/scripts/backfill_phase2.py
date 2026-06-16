"""Phase-2 backfill for users created before Phase 2 schema rolled out.

What it does (idempotent, all in one transaction per user):

  1. users.onboarding_step
       step ladder:
         0 = nothing
         1 = email verified
         2 = consent (tos + privacy) signed
         3 = broker_account attached
         4 = strategy_instance created
         5 = first live_consent signed
       We take the MAX step the user has reached based on existing rows.
       Never reduces an already-higher step.

  2. subscriptions.plan_id
       Backfill from subscriptions.plan (the old string column) → plans.id.

  3. live_consents
       Left empty intentionally — Phase-2 rules require explicit re-sign,
       even for legacy users. Documented in the runbook.

  4. consents
       For users with email_verified_at NOT NULL, insert a synthetic
       'tos' v0 consent row dated email_verified_at — preserves the legal
       record that the user agreed at signup. Skips if a 'tos' consent
       already exists for the user.

Usage:
    python -m scripts.backfill_phase2
    python -m scripts.backfill_phase2 --dry-run
    python -m scripts.backfill_phase2 --user-id <uuid>
    python -m scripts.backfill_phase2 --batch-size 500

Run after `alembic upgrade head` reaches revision 0004.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Final

from sqlalchemy import text

from app.db.session import SessionLocal


DEFAULT_BATCH: Final[int] = 500


# ---------------------------------------------------------------------------
# SQL primitives — all written against schema directly (no ORM imports) so
# this script stays decoupled from model evolution.
# ---------------------------------------------------------------------------

SELECT_USERS_BATCH = text(
    """
    SELECT id, email_verified_at, onboarding_step
      FROM users
     WHERE deleted_at IS NULL
       AND (:user_id::uuid IS NULL OR id = :user_id::uuid)
       AND id > :cursor
     ORDER BY id
     LIMIT :batch
    """
)


# Returns the max-reached step for a single user, computed from observable
# evidence in other tables.
COMPUTE_STEP_SQL = text(
    """
    WITH
      ev AS (SELECT email_verified_at IS NOT NULL AS verified FROM users WHERE id = :uid),
      co AS (SELECT count(*) > 0 AS has_consent FROM consents
              WHERE user_id = :uid AND kind IN ('tos','privacy')),
      ba AS (SELECT count(*) > 0 AS has_broker FROM broker_accounts
              WHERE user_id = :uid AND deleted_at IS NULL),
      si AS (SELECT count(*) > 0 AS has_instance FROM strategy_instances
              WHERE user_id = :uid AND deleted_at IS NULL),
      lc AS (SELECT count(*) > 0 AS has_live_consent FROM live_consents
              WHERE user_id = :uid)
    SELECT
      CASE
        WHEN (SELECT has_live_consent FROM lc) THEN 5
        WHEN (SELECT has_instance     FROM si) THEN 4
        WHEN (SELECT has_broker       FROM ba) THEN 3
        WHEN (SELECT has_consent      FROM co) THEN 2
        WHEN (SELECT verified         FROM ev) THEN 1
        ELSE 0
      END AS step
    """
)


UPDATE_ONBOARDING_SQL = text(
    """
    UPDATE users
       SET onboarding_step = GREATEST(onboarding_step, :step)
     WHERE id = :uid
       AND onboarding_step < :step
    """
)


INSERT_LEGACY_TOS_CONSENT_SQL = text(
    """
    INSERT INTO consents (user_id, kind, version, agreed_at)
    SELECT :uid, 'tos', 'v0-legacy', u.email_verified_at
      FROM users u
     WHERE u.id = :uid
       AND u.email_verified_at IS NOT NULL
       AND NOT EXISTS (
            SELECT 1 FROM consents c
             WHERE c.user_id = :uid AND c.kind = 'tos'
       )
    """
)


# Backfill subscriptions.plan_id from the existing string column `plan`.
BACKFILL_PLAN_ID_SQL = text(
    """
    UPDATE subscriptions s
       SET plan_id = p.id
      FROM plans p
     WHERE s.plan_id IS NULL
       AND s.plan = p.code
    """
)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
async def backfill(user_id: str | None, batch_size: int, dry: bool) -> None:
    processed = 0
    errors = 0
    cursor = "00000000-0000-0000-0000-000000000000"

    async with SessionLocal() as session:
        # 1) Subscriptions plan_id — one-shot UPDATE (fast).
        sys.stdout.write("[1/2] backfill subscriptions.plan_id from plans.code\n")
        if not dry:
            result = await session.execute(BACKFILL_PLAN_ID_SQL)
            sys.stdout.write(f"  updated {result.rowcount} subscription rows\n")
        else:
            sys.stdout.write("  (dry-run) skipping update\n")

        # 2) Per-user onboarding step + legacy tos consent.
        sys.stdout.write("[2/2] per-user onboarding_step + legacy ToS consent\n")
        while True:
            batch = (
                await session.execute(
                    SELECT_USERS_BATCH,
                    {
                        "user_id": user_id,
                        "cursor": cursor,
                        "batch": batch_size,
                    },
                )
            ).fetchall()

            if not batch:
                break

            for row in batch:
                uid = row.id
                try:
                    # 2a) Insert legacy ToS consent if appropriate (idempotent).
                    if not dry:
                        await session.execute(
                            INSERT_LEGACY_TOS_CONSENT_SQL, {"uid": uid}
                        )

                    # 2b) Compute and apply onboarding_step.
                    step_row = (
                        await session.execute(COMPUTE_STEP_SQL, {"uid": uid})
                    ).fetchone()
                    step = int(step_row.step) if step_row else 0

                    if not dry:
                        await session.execute(
                            UPDATE_ONBOARDING_SQL, {"uid": uid, "step": step}
                        )

                    processed += 1
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    sys.stderr.write(f"  ERROR uid={uid}: {exc}\n")

                cursor = str(uid)

            if not dry:
                await session.commit()
            sys.stdout.write(f"  cursor={cursor}  processed={processed}  errors={errors}\n")

            # Single-user mode: stop after one row.
            if user_id is not None:
                break

        sys.stdout.write(f"done. processed={processed} errors={errors} dry_run={dry}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase-2 backfill (idempotent).")
    p.add_argument("--user-id", type=str, default=None,
                   help="Limit to a single user uuid (debugging).")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                   help=f"Batch size (default {DEFAULT_BATCH}).")
    p.add_argument("--dry-run", action="store_true",
                   help="Plan only; do not write.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(backfill(user_id=args.user_id, batch_size=args.batch_size, dry=args.dry_run))


if __name__ == "__main__":
    main()
