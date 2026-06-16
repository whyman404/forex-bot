"""Seed an admin user. Idempotent (UPSERT).

Usage:
    python -m scripts.seed_admin
    python -m scripts.seed_admin --email admin@local --password changeme123

Notes:
- Targets the schema produced by alembic migration 0001 — uses raw SQL against
  the `users` table (not the ORM) so this script is forward-compatible if the
  ORM model evolves separately from schema.sql.
- Password is hashed with Argon2id via app.core.security.hash_password.
- Country is set to 'US' by default — change via env if needed.

Mnemosyne Rin — running this in production:
    Only one admin should be seeded automatically. Rotate the password
    IMMEDIATELY after first login. The default `changeme123` is dev-only.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Final

from sqlalchemy import text

from app.core.security import hash_password
from app.db.session import SessionLocal


DEFAULT_EMAIL: Final[str] = "admin@local"
DEFAULT_PASSWORD: Final[str] = "changeme123"
DEFAULT_FULL_NAME: Final[str] = "Admin"
DEFAULT_COUNTRY: Final[str] = "US"

# Environment variables override defaults but NOT explicit CLI args.
# Production seed:    set ADMIN_EMAIL/ADMIN_PASSWORD in Railway env + run --from-env
# Local dev:          ./scripts/dev.sh exports vars from .env.admin (gitignored)
ENV_EMAIL = "ADMIN_EMAIL"
ENV_PASSWORD = "ADMIN_PASSWORD"
ENV_FULL_NAME = "ADMIN_FULL_NAME"
ENV_COUNTRY = "ADMIN_COUNTRY"


UPSERT_SQL = text(
    """
    INSERT INTO users
        (email, password_hash, email_verified_at, full_name, country, role)
    VALUES
        (:email, :password_hash, now(), :full_name, :country, 'admin')
    ON CONFLICT (email) WHERE deleted_at IS NULL
    DO UPDATE SET
        password_hash     = EXCLUDED.password_hash,
        email_verified_at = COALESCE(users.email_verified_at, EXCLUDED.email_verified_at),
        role              = 'admin',
        updated_at        = now()
    RETURNING id, email, role;
    """
)


async def seed_admin(
    email: str,
    password: str,
    full_name: str = DEFAULT_FULL_NAME,
    country: str = DEFAULT_COUNTRY,
) -> None:
    password_hash = hash_password(password)

    async with SessionLocal() as session:
        result = await session.execute(
            UPSERT_SQL,
            {
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name,
                "country": country,
            },
        )
        row = result.first()
        await session.commit()

    if row is None:
        sys.stderr.write("seed_admin: UPSERT returned no row — investigate.\n")
        sys.exit(2)

    sys.stdout.write("=" * 60 + "\n")
    sys.stdout.write("Admin user seeded.\n")
    sys.stdout.write(f"  id:    {row.id}\n")
    sys.stdout.write(f"  email: {row.email}\n")
    sys.stdout.write(f"  role:  {row.role}\n")
    sys.stdout.write(f"  pass:  {password}\n")
    sys.stdout.write("=" * 60 + "\n")
    sys.stdout.write("WARNING: rotate this password immediately after first login.\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed an admin user (idempotent).")
    parser.add_argument(
        "--from-env",
        action="store_true",
        help=f"Require all credentials from env: {ENV_EMAIL}, {ENV_PASSWORD}, {ENV_FULL_NAME}, {ENV_COUNTRY}",
    )
    parser.add_argument("--email", default=None, help=f"Admin email (env: {ENV_EMAIL}; default: {DEFAULT_EMAIL})")
    parser.add_argument(
        "--password",
        default=None,
        help=f"Admin password (env: {ENV_PASSWORD}; default: {DEFAULT_PASSWORD}). Change immediately in prod.",
    )
    parser.add_argument("--full-name", default=None, help=f"Full name (env: {ENV_FULL_NAME})")
    parser.add_argument("--country", default=None, help=f"ISO 3166-1 alpha-2 (env: {ENV_COUNTRY})")
    return parser.parse_args()


def _resolve(args: argparse.Namespace) -> tuple[str, str, str, str]:
    """Resolution order: explicit CLI arg → env var → default. --from-env requires env."""
    email = args.email or os.environ.get(ENV_EMAIL) or DEFAULT_EMAIL
    password = args.password or os.environ.get(ENV_PASSWORD) or DEFAULT_PASSWORD
    full_name = args.full_name or os.environ.get(ENV_FULL_NAME) or DEFAULT_FULL_NAME
    country = args.country or os.environ.get(ENV_COUNTRY) or DEFAULT_COUNTRY

    if args.from_env:
        missing = [
            name for name, value, default in [
                (ENV_EMAIL, email, DEFAULT_EMAIL),
                (ENV_PASSWORD, password, DEFAULT_PASSWORD),
            ] if value == default
        ]
        if missing:
            sys.stderr.write(f"seed_admin: --from-env requires {missing} to be set.\n")
            sys.exit(3)

    if password == DEFAULT_PASSWORD:
        sys.stderr.write(
            "seed_admin: WARNING using DEFAULT password. Set ADMIN_PASSWORD env or "
            "--password arg for production.\n"
        )

    return email, password, full_name, country


def main() -> None:
    args = _parse_args()
    email, password, full_name, country = _resolve(args)
    asyncio.run(seed_admin(email, password, full_name, country))


if __name__ == "__main__":
    main()
