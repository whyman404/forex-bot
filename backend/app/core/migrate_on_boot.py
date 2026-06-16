"""Opt-in Alembic migration at app boot.

Atlas Goro — running migrations from inside the running app is generally
a bad idea (every replica races on the same `alembic upgrade head`).
But on PaaS without a deploy hook (Fly, sometimes Railway), it is the
pragmatic option.

Safety:
1. **Disabled by default** — only runs if `RUN_MIGRATIONS_ON_BOOT=true`.
2. **Postgres advisory lock** — only one replica wins; others wait or skip.
3. **Idempotent** — `alembic upgrade head` is a no-op if already current.
4. **Bounded wait** — caller can time-out; we won't deadlock startup forever.

Recommended workflow on Railway:
- Use the one-shot post-deploy script (`scripts/railway_post_deploy.sh`)
  for migrations.
- Leave `RUN_MIGRATIONS_ON_BOOT=false`.

Reference:
- Alembic env.py running migrations programmatically — Alembic Cookbook
- pg_advisory_lock — Postgres docs §13.3.5
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.session import SessionLocal

logger = get_logger(__name__)

# Arbitrary fixed integer — must match across replicas. Pick something
# unlikely to collide with other apps sharing the DB.
_ADVISORY_LOCK_KEY = 4242_4242_42


@asynccontextmanager
async def _advisory_lock(lock_key: int = _ADVISORY_LOCK_KEY) -> AsyncIterator[bool]:
    """Try to acquire a Postgres session-level advisory lock.

    Yields True if acquired (caller may proceed), False if someone else
    holds it. We use `pg_try_advisory_lock` (non-blocking) so racing
    replicas exit fast.
    """
    async with SessionLocal() as session:
        try:
            result = await session.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_key}
            )
            acquired = bool(result.scalar())
            try:
                yield acquired
            finally:
                if acquired:
                    await session.execute(
                        text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key}
                    )
                    await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("advisory_lock_error", err=str(exc))
            yield False


def _run_alembic_upgrade_head() -> None:
    """Run `alembic upgrade head` programmatically.

    Synchronous — Alembic itself is sync. We call this from a thread so
    we don't block the event loop.
    """
    from alembic import command
    from alembic.config import Config

    # alembic.ini sits at backend project root, which equals CWD in our Docker
    # image and on Railway. Build an absolute path defensively.
    ini_path = Path("alembic.ini")
    if not ini_path.exists():
        # Try parent (in case CWD is `/app/app/`).
        ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    cfg = Config(str(ini_path))
    command.upgrade(cfg, "head")


async def run_migrations_if_enabled() -> None:
    """Lifespan hook — call from startup. No-op unless explicitly enabled."""
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.run_migrations_on_boot:
        logger.info("migrations_on_boot_disabled")
        return

    async with _advisory_lock() as acquired:
        if not acquired:
            logger.info("migrations_skipped_lock_held_by_peer")
            return
        logger.info("migrations_running")
        try:
            await asyncio.to_thread(_run_alembic_upgrade_head)
            logger.info("migrations_complete")
        except Exception as exc:  # noqa: BLE001
            # We log but DO NOT crash the app — a failed migration on one
            # replica shouldn't take down all of them. Operator must inspect.
            logger.error("migrations_failed", err=str(exc))
            raise
