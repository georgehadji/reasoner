"""Alembic environment configuration."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

# Load database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/reasoner",
)


def split_sslmode(url: str) -> tuple[str, dict]:
    """Move a libpq-style ``sslmode`` query param into asyncpg ``connect_args``.

    docker-compose hands the backend ``...?sslmode=require``. SQLAlchemy's
    asyncpg dialect forwards unknown query params as keyword arguments to
    ``asyncpg.connect``, which has no ``sslmode`` parameter and raises
    ``TypeError`` -- under the entrypoint's ``set -e`` that kills the
    container before gunicorn starts. asyncpg spells it ``ssl=`` and accepts
    the same mode strings (``require``, ``verify-full``, ...).
    """
    parsed = make_url(url)
    if "asyncpg" not in parsed.drivername or "sslmode" not in parsed.query:
        return url, {}
    sslmode = parsed.query["sslmode"]
    if isinstance(sslmode, tuple):  # repeated param: last one wins, like libpq
        sslmode = sslmode[-1]
    stripped = parsed.difference_update_query(["sslmode"])
    return stripped.render_as_string(hide_password=False), {"ssl": sslmode}


#: Fixed key for the session-level advisory lock that serialises migrations.
MIGRATION_LOCK_ID = 7_261_000_001

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata — not using SQLAlchemy ORM, so this is None
# Migrations are hand-written raw SQL
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url, _ = split_sslmode(DATABASE_URL)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # docker-entrypoint.sh runs `alembic upgrade head` in every container, so a
    # scale-out or a rolling deploy starts several at once. Two of them applying the
    # same revision race on the DDL, and CREATE INDEX CONCURRENTLY can leave an
    # INVALID index behind. A session-level lock (not xact-level: autocommit_block
    # commits mid-migration) makes the second one wait, then find nothing to do.
    locked = connection.dialect.name == "postgresql"
    if locked:
        connection.execute(text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID})
        connection.commit()  # end the autobegun transaction; the session lock stays
    try:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    finally:
        if locked:
            connection.commit()  # a failed migration leaves the connection mid-transaction
            connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": MIGRATION_LOCK_ID})
            connection.commit()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    url, connect_args = split_sslmode(DATABASE_URL)
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
