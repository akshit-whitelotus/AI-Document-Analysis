from pathlib import Path
import sys

# auth-service directory
SERVICE_ROOT = Path(__file__).resolve().parents[1]

# project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from shared.config.settings import settings
from shared.database.base import Base

# Import all models
from app.models import *

config = context.config

config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("+asyncpg", "")
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        version_table="auth_alembic_version",
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="auth_alembic_version",
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()