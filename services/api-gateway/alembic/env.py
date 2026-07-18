import asyncio
from logging.config import fileConfig

# Make sure `app` is importable regardless of how alembic is invoked.
# This adds services/api-gateway/ to sys.path so `from app.x import y` works.
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.core.database import Base
from app.models import *  # noqa: F401, F403

config = context.config
# Always migrate the same database the app talks to (HOPPER_DATABASE_URL /
# .env), overriding the static fallback URL in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the migration target URL (HOP-22 25.4).

    Precedence:
      1. An explicitly-set ``sqlalchemy.url`` (programmatic ``set_main_option``
         — how the integration tests point at their Testcontainer, and how
         one-off scripts can override).
      2. The app settings' ``database_url`` — which itself honours the
         ``HOPPER_DATABASE_URL`` env var and the service ``.env`` file, and
         defaults to the local compose Postgres. This is what makes
         ``alembic upgrade head`` work inside the deployed pod with NO extra
         flags (historically env.py read only alembic.ini's hardcoded
         localhost URL, so prod migrations needed a set_main_option dance).
    """
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from app.config import settings

    # Escape % so ConfigParser interpolation can't mangle passwords.
    return settings.database_url.replace("%", "%%")


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
