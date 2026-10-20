from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401

config = context.config

# Programmatic callers (the test harness) pass configure_logger=False so fileConfig does
# not replace the host process's redacting log handlers.
if config.config_file_name is not None and config.attributes.get('configure_logger', True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

database_url = config.get_main_option('sqlalchemy.url') or settings.DATABASE_URL
config.set_main_option('sqlalchemy.url', database_url.replace('%', '%%'))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # One transaction per revision, so an autocommit block inside one (e.g.
            # replace_enum_check's VALIDATE) commits only that revision's earlier steps.
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
