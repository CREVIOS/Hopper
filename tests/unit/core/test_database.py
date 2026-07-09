from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core import database as database_module


def test_base_is_declarative_base_subclass():
    assert issubclass(database_module.Base, DeclarativeBase)


def test_async_session_factory_uses_async_session_class():
    session = database_module.async_session()

    assert isinstance(session, AsyncSession)
    assert session.sync_session.expire_on_commit is False
