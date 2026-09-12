"""Shared fixtures. Read this once and every integration test in the repo makes sense.

    migrated_database  session-scoped: make sure the database in DATABASE_URL exists and is
                       at the latest migration. `make test` points DATABASE_URL at a
                       separate *_test database so tests never touch development data.
    db                 one transaction per test, rolled back at the end — tests are
                       isolated from each other and leave nothing behind, and a test that
                       calls `db.commit()` through the service layer still rolls back.
    app                the FastAPI app with `get_db` overridden to hand out that session.
    make_user          create a user with the given roles inside the test's transaction.
    make_client        an httpx client for the app, optionally signed in as a user.

Tests use real PostgreSQL, never SQLite (ADR-0002).
"""

import uuid
from collections.abc import Callable, Generator

import httpx
import pytest
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import Session

import main
from alembic import command
from core.config import get_settings
from core.database import engine, get_db
from core.security import create_access_token, hash_password
from models.user import User


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Create the test database if it does not exist, then bring it to head.

    autouse, because anything that touches `core.database.engine` needs the database to
    exist — including tests that bring their own session rather than the `db` fixture.
    """
    url = make_url(get_settings().database_url)
    maintenance = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        ).scalar()
        if not exists:
            # CREATE DATABASE cannot take a bound parameter; the name comes from our own
            # settings, and quoting it as an identifier keeps it from being parsed as SQL.
            quoted = maintenance.dialect.identifier_preparer.quote(str(url.database))
            connection.execute(text(f"CREATE DATABASE {quoted}"))
    maintenance.dispose()
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """A session inside one transaction that is always rolled back.

    join_transaction_mode="create_savepoint" turns `session.commit()` inside the code
    under test into a savepoint release, so the outer transaction survives and the
    rollback at the end still discards everything.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def app(db: Session) -> FastAPI:
    """A fresh app whose request handlers see the test's transaction."""
    application = main.create_app()
    application.dependency_overrides[get_db] = lambda: db
    return application


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    """Create a signed-up user with the given roles, e.g. make_user("organiser")."""

    def _make(*roles: str, email: str | None = None) -> User:
        user = User(
            email=email or f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            roles=list(roles),
        )
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture
def make_client(app: FastAPI) -> Callable[[User | None], httpx.AsyncClient]:
    """An in-process client; pass a user to send a valid bearer token for them."""

    def _make(user: User | None = None) -> httpx.AsyncClient:
        headers: dict[str, str] = {}
        if user is not None:
            token = create_access_token(str(user.id), list(user.roles))
            headers["Authorization"] = f"Bearer {token}"
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
        )

    return _make
