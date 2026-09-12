"""Fixtures for integration tests — the ones that need a real PostgreSQL.

They live here rather than in tests/ so that pure unit tests (domain/, dependencies) never
touch a database. Read this once and every integration test in the repo makes sense.

    migrated_database  session-scoped, autouse for this directory: make sure the database
                       in DATABASE_URL exists and is at the latest migration. `make test`
                       points DATABASE_URL at a separate *_test database so tests never
                       touch development data.
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
import psycopg
import pytest
from alembic.config import Config
from fastapi import FastAPI
from psycopg import sql
from sqlalchemy import make_url
from sqlalchemy.orm import Session

import main
from alembic import command
from core.config import get_settings
from core.database import engine, get_db
from core.security import create_access_token, hash_password
from domain.roles import Role
from models.user import User


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Create the test database if it does not exist, then bring it to head.

    autouse for this directory, because anything that touches `core.database.engine`
    needs the database to exist — including tests that bring their own session rather
    than the `db` fixture.
    """
    url = make_url(get_settings().database_url)
    name = str(url.database)
    # CREATE DATABASE cannot take a bound parameter, so the name is composed as a quoted
    # identifier with psycopg's sql module rather than concatenated into a string
    # (AGENTS.md §3). The connection goes to the maintenance database, not the test one.
    maintenance_dsn = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(maintenance_dsn, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone()
        if exists is None:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
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

    def _make(*roles: Role | str, email: str | None = None) -> User:
        user = User(
            email=email or f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            # Role(...) validates: a misspelt role in a test fails here, not as a 403.
            roles=[Role(role).value for role in roles],
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
