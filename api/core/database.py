"""The SQLAlchemy engine, session factory, and the FastAPI session dependency.

ADR-0003: repositories are the only layer that uses the session for queries. Everything
else receives it through the `get_db` dependency and hands it straight on. `Session` is
re-exported here so services can type that parameter without importing SQLAlchemy.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.orm import Session as Session

from core.config import get_settings

# pool_pre_ping checks a pooled connection before handing it out, so a connection dropped
# while Docker restarted the database surfaces as a reconnect rather than an error.
engine = create_engine(get_settings().database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for every ORM model. Alembic autogenerates against its metadata."""


def get_db() -> Generator[Session, None, None]:
    """Yield a session for one request and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
