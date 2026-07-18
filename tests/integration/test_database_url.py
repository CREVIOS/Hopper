import pytest

from .conftest import to_async_database_url


def test_to_async_database_url_converts_postgres_scheme():
    assert to_async_database_url("postgres://user:pass@localhost:5432/app") == (
        "postgresql+asyncpg://user:pass@localhost:5432/app"
    )


def test_to_async_database_url_converts_postgresql_scheme():
    assert to_async_database_url("postgresql://user:pass@localhost:5432/app") == (
        "postgresql+asyncpg://user:pass@localhost:5432/app"
    )


def test_to_async_database_url_converts_psycopg2_sqlalchemy_url():
    assert to_async_database_url("postgresql+psycopg2://user:pass@localhost:5432/app") == (
        "postgresql+asyncpg://user:pass@localhost:5432/app"
    )


def test_to_async_database_url_keeps_existing_asyncpg_url():
    url = "postgresql+asyncpg://user:pass@localhost:5432/app"

    assert to_async_database_url(url) == url


def test_to_async_database_url_does_not_rewrite_embedded_postgresql_text():
    url = "sqlite:///tmp/postgresql://not-a-real-db-url"

    assert to_async_database_url(url) == url


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("postgres://u:p@db/app?sslmode=require", "postgresql+asyncpg://u:p@db/app?sslmode=require"),
        ("postgresql://u:p@db:5433/app", "postgresql+asyncpg://u:p@db:5433/app"),
        ("postgresql+psycopg2://u:p@db/app", "postgresql+asyncpg://u:p@db/app"),
        ("postgresql+asyncpg://u:p@db/app", "postgresql+asyncpg://u:p@db/app"),
        ("sqlite+aiosqlite:///tmp/app.db", "sqlite+aiosqlite:///tmp/app.db"),
        ("mysql://u:p@db/app", "mysql://u:p@db/app"),
        ("", ""),
        ("POSTGRESQL://u:p@db/app", "POSTGRESQL://u:p@db/app"),
        (" postgresql://u:p@db/app", " postgresql://u:p@db/app"),
        ("postgresqlx://u:p@db/app", "postgresqlx://u:p@db/app"),
    ],
)
def test_to_async_database_url_edge_cases(source, expected):
    assert to_async_database_url(source) == expected
