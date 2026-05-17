"""Alembic environment — NutriOS.

Supports both offline (--sql) and online (live DB connection) migration modes.
DATABASE_URL is read from app.config.settings so it stays in sync with the
FastAPI app and never needs to be duplicated in alembic.ini.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Pull in app config & models ───────────────────────────────

# These imports rely on prepend_sys_path = . in alembic.ini, which adds
# backend/ to sys.path so "from app.xxx" resolves correctly.
from app.config import settings
from app.models import Base  # noqa: F401 — all models are registered on Base

# ── Alembic config object ─────────────────────────────────────

config = context.config

# Override the sqlalchemy.url from alembic.ini with the real value from
# the environment, so we only ever configure DATABASE_URL in one place.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up Python logging from the [loggers] section of alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Tell Alembic which metadata to diff against when auto-generating migrations
target_metadata = Base.metadata


# ── Offline mode (generates SQL without a live connection) ────

def run_migrations_offline() -> None:
    """Run migrations without a real DB connection.

    Useful for generating SQL scripts to review before applying.
    Usage: alembic upgrade head --sql > migration.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (connects to a live DB) ──────────────────────

def run_migrations_online() -> None:
    """Run migrations against a live database connection.

    Uses NullPool so Alembic doesn't hold an open connection between
    migration steps (important for Railway / serverless environments).
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ── Entry point ───────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
