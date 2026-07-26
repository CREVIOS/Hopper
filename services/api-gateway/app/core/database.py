from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# echo is its own opt-in flag, NOT tied to `debug`: prod runs with debug=true
# for verbose error context, and echoing every SQL statement at INFO floods the
# logs and burns CPU. Enable per-run with HOPPER_SQL_ECHO=true when needed.
engine = create_async_engine(settings.database_url, echo=settings.sql_echo)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
