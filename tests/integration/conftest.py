"""Integration test fixtures using Testcontainers."""

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
API_GATEWAY_ROOT = REPO_ROOT / "services" / "api-gateway"
APP_TABLES = (
    "audit_logs",
    "issue_reports",
    "metrics_samples",
    "ssh_keys",
    "pod_sessions",
    "ledger_entries",
    "transfers",
    "accounts",
    "users",
)


def to_async_database_url(database_url: str) -> str:
    """Normalize PostgreSQL URLs to the asyncpg driver used by the API gateway."""
    if database_url.startswith("postgresql+psycopg2://"):
        return database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return database_url


async def reset_database(session: AsyncSession) -> None:
    """Clear all application tables between integration tests."""
    await session.rollback()
    table_list = ", ".join(APP_TABLES)
    await session.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
    await session.commit()


@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL + TimescaleDB container for integration tests."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(
        image="timescale/timescaledb:latest-pg16",
        username="hopper_test",
        password="test",
        dbname="hopper_test",
    ) as postgres:
        yield postgres


@pytest.fixture(scope="session")
def nats_container():
    """Start a NATS container with JetStream enabled."""
    from testcontainers.core.container import DockerContainer

    with DockerContainer("nats:2.10-alpine").with_command(
        "--jetstream"
    ).with_exposed_ports(4222) as nats:
        yield nats


@pytest_asyncio.fixture
async def db_session(postgres_container) -> AsyncSession:
    """Create a database session for testing."""
    url = to_async_database_url(postgres_container.get_connection_url())
    engine = create_async_engine(url)

    # Run migrations
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config(str(API_GATEWAY_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_GATEWAY_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await reset_database(session)
        yield session
        await reset_database(session)

    await engine.dispose()


@pytest.fixture
def nats_url(nats_container) -> str:
    """Get NATS connection URL."""
    host = nats_container.get_container_host_ip()
    port = nats_container.get_exposed_port(4222)
    return f"nats://{host}:{port}"
