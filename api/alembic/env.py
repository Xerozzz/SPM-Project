"""Alembic environment.

Deliberately online-only: we always migrate a real PostgreSQL database (ADR-0002 rules
out SQLite), so the usual offline branch would only ever be dead code.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from core.config import get_settings
from core.database import Base

config = context.config

# One source of truth for the URL: the same settings object the API uses.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importing api models here is what lets `alembic revision --autogenerate` see them.
target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
