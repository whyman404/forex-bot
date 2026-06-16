"""Alembic environment — async-aware, settings-driven.

Mnemosyne Rin — single source of truth for DB URL is `app.core.config.Settings`,
so the same .env runs the app AND the migrations. Eliminates drift.

Notes:
- Uses `create_async_engine` + `connection.run_sync(do_migrations)` pattern.
- Imports `Base` from `app.db.base` AND eagerly imports every model module
  in `app.models` so autogenerate sees the full metadata graph.
- For data-only or pure-SQL migrations (like 0001_initial.py), autogenerate
  is NOT used — those migrations call `op.execute(...)` directly. This file
  still works fine in both modes.
"""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# 1. Load app settings (one source of truth for the DB URL)
# ---------------------------------------------------------------------------
from app.core.config import get_settings  # noqa: E402

# ---------------------------------------------------------------------------
# 2. Import Base + ALL model modules so MetaData is populated
# ---------------------------------------------------------------------------
from app.db import base as _db_base  # noqa: E402
from app import models as _models_pkg  # noqa: E402


def _import_all_models() -> None:
    """Recursively import every submodule under `app.models` so SQLAlchemy
    sees every Table on `Base.metadata`. Required for autogenerate accuracy."""
    for module_info in pkgutil.walk_packages(
        _models_pkg.__path__, prefix=f"{_models_pkg.__name__}."
    ):
        importlib.import_module(module_info.name)


_import_all_models()

target_metadata = _db_base.Base.metadata

# ---------------------------------------------------------------------------
# 3. Alembic config object
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject DB URL from Settings (overrides empty sqlalchemy.url in alembic.ini)
settings = get_settings()
config.set_main_option("sqlalchemy.url", str(settings.database_url))


# ---------------------------------------------------------------------------
# 4. Offline mode (generate SQL without DB connection)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL to stdout."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# 5. Online mode (async)
# ---------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    """Sync callback executed inside `connection.run_sync(...)`."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
        # Render constraint names with our naming convention from app.db.base
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Build an async engine, open a connection, then run migrations sync."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Online entrypoint — wraps async runner."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# 6. Dispatch
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
