"""Integration test fixtures using Testcontainers."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


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
    url = postgres_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url)

    # Run migrations
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("services/api-gateway/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url.replace("+asyncpg", ""))
    command.upgrade(alembic_cfg, "head")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def nats_url(nats_container) -> str:
    """Get NATS connection URL."""
    host = nats_container.get_container_host_ip()
    port = nats_container.get_exposed_port(4222)
    return f"nats://{host}:{port}"
