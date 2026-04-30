import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # NullPool disables connection pooling for migrations. Alembic manages the
    # connection lifecycle directly (open → migrate → close), so a pool would
    # create connections that are never reused and never returned cleanly.
    connectable = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        # Alembic's migration runner is synchronous. run_sync bridges the async
        # connection into a synchronous context so do_run_migrations can call
        # standard Alembic APIs (context.configure, context.run_migrations)
        # without any async/await plumbing inside the migration files themselves.
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # asyncio.run starts a fresh event loop for the migration process.
    # Alembic invokes this module as a script, so there is no running loop yet —
    # unlike application code where the FastAPI event loop is already active.
    asyncio.run(run_migrations_online())
