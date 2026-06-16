"""Partition maintenance — monthly cron job.

For each of `signals`, `trades`, `audit_log`:
  1. Ensure the next N (default 3) monthly partitions exist.
  2. Detach + drop partitions older than retention (per-table).

Usage:
    python -m scripts.maintain_partitions
    python -m scripts.maintain_partitions --ahead 6 --dry-run
    python -m scripts.maintain_partitions --skip-drop

Recommended schedule: run on the 25th of each month at 02:00 UTC, then again
on the 1st as a safety net.

Mnemosyne Rin — retention defaults align with legal + business needs:
  - signals: 18 months (operational + ML training set)
  - trades: 84 months / 7 years (regulatory)
  - audit_log: 84 months / 7 years (regulatory)

Override via env or CLI flag if your jurisdiction differs.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from app.db.session import SessionLocal


# ---------------------------------------------------------------------------
# Partition table configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PartitionedTable:
    name: str
    retention_months: int  # how long to keep historical partitions


PARTITIONED_TABLES: list[PartitionedTable] = [
    PartitionedTable(name="signals", retention_months=18),
    PartitionedTable(name="trades", retention_months=84),
    PartitionedTable(name="audit_log", retention_months=84),
    # Phase-2 additions (migration 0003)
    # email_outbox: 6mo is enough for operational debug + bounce trace;
    #   after that, the receipt is the legal record (not our outbox).
    # webhook_inbox: 12mo — webhook replay window for Stripe disputes.
    PartitionedTable(name="email_outbox", retention_months=6),
    PartitionedTable(name="webhook_inbox", retention_months=12),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    """Return the first of (d.month + months)."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def _partition_name(table: str, d: date) -> str:
    return f"{table}_y{d.year:04d}_m{d.month:02d}"


# ---------------------------------------------------------------------------
# DDL builders
# ---------------------------------------------------------------------------
CREATE_PARTITION_SQL = text(
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_class WHERE relname = :part_name
        ) THEN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                :part_name, :parent_name, :start_ts, :end_ts
            );
        END IF;
    END$$;
    """
)


# We DETACH first then DROP so a long-running query on the partition doesn't
# block the cron, and so the table can be archived to cold storage if needed.
DETACH_PARTITION_SQL = text(
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE c.relname = :part_name AND p.relname = :parent_name
        ) THEN
            EXECUTE format('ALTER TABLE %I DETACH PARTITION %I', :parent_name, :part_name);
        END IF;
    END$$;
    """
)

DROP_PARTITION_SQL = text("DROP TABLE IF EXISTS :part_name_literal")  # see _drop()


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------
async def _create_ahead(session, table: PartitionedTable, months_ahead: int, dry: bool) -> list[str]:
    today = datetime.now(timezone.utc).date()
    base = _first_of_month(today)
    created: list[str] = []

    # months 0..N-1 from current month — covers current + next (N-1)
    for offset in range(0, months_ahead + 1):
        start = _add_months(base, offset)
        end = _add_months(base, offset + 1)
        part_name = _partition_name(table.name, start)
        msg = f"  ensure {part_name}  [{start} .. {end})"
        sys.stdout.write(msg + "\n")
        if dry:
            continue
        await session.execute(
            CREATE_PARTITION_SQL,
            {
                "part_name": part_name,
                "parent_name": table.name,
                "start_ts": f"{start} 00:00+00",
                "end_ts": f"{end} 00:00+00",
            },
        )
        created.append(part_name)
    return created


async def _drop_old(session, table: PartitionedTable, dry: bool) -> list[str]:
    today = datetime.now(timezone.utc).date()
    cutoff = _add_months(_first_of_month(today), -table.retention_months)

    # Find partitions older than cutoff by scanning pg_inherits.
    rows = (
        await session.execute(
            text(
                """
                SELECT c.relname AS part_name
                FROM pg_inherits i
                JOIN pg_class c ON c.oid = i.inhrelid
                JOIN pg_class p ON p.oid = i.inhparent
                WHERE p.relname = :parent_name
                  AND c.relname ~ '^([a-z_]+)_y[0-9]{4}_m[0-9]{2}$'
                """
            ),
            {"parent_name": table.name},
        )
    ).fetchall()

    dropped: list[str] = []
    for r in rows:
        part_name = r.part_name
        # parse YYYY_MM from suffix
        try:
            tag = part_name.rsplit("_y", 1)[1]  # "2026_m06"
            year_s, month_s = tag.split("_m")
            part_start = date(int(year_s), int(month_s), 1)
        except (IndexError, ValueError):
            continue
        if part_start >= cutoff:
            continue
        msg = f"  drop {part_name} (start={part_start}, cutoff={cutoff})"
        sys.stdout.write(msg + "\n")
        if dry:
            continue
        await session.execute(
            DETACH_PARTITION_SQL,
            {"part_name": part_name, "parent_name": table.name},
        )
        # Identifier interpolation — safe because part_name was validated by regex above
        # and is from pg_class (we created it).
        await session.execute(text(f'DROP TABLE IF EXISTS "{part_name}"'))
        dropped.append(part_name)
    return dropped


async def maintain(months_ahead: int, dry: bool, skip_drop: bool) -> None:
    async with SessionLocal() as session:
        for tbl in PARTITIONED_TABLES:
            sys.stdout.write(f"[{tbl.name}] retention={tbl.retention_months}mo\n")
            await _create_ahead(session, tbl, months_ahead, dry)
            if skip_drop:
                sys.stdout.write("  (skip drop)\n")
            else:
                await _drop_old(session, tbl, dry)
        if not dry:
            await session.commit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create + drop monthly partitions.")
    p.add_argument("--ahead", type=int, default=3, help="How many future months to ensure (default 3)")
    p.add_argument("--dry-run", action="store_true", help="Plan only; do not execute DDL")
    p.add_argument("--skip-drop", action="store_true", help="Only create, never drop")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(maintain(months_ahead=args.ahead, dry=args.dry_run, skip_drop=args.skip_drop))


if __name__ == "__main__":
    main()
