"""F1 sign-in: valid credentials issue a JWT with role claims; invalid ones get a
generic 401 that never says whether the account exists."""

from collections.abc import Generator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

import main
from core import security
from core.database import SessionLocal, get_db
from models.user import User
from services.auth import InvalidCredentialsError, sign_in


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """Real Postgres session. Users use Postgres-only ARRAY/UUID columns (ADR-0002)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.query(User).delete()
        session.commit()
        session.close()


def _add_user(db: Session, email: str, password: str, roles: list[str]) -> User:
    user = User(email=email, password_hash=security.hash_password(password), roles=roles)
    db.add(user)
    db.commit()
    return user


async def _post(app: FastAPI, path: str, body: dict[str, str]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=body)


@pytest.mark.story("SCRUM-27")
def test_sign_in_returns_token_with_role_claims(db: Session) -> None:
    _add_user(db, "multi@example.com", "secret123", ["organiser", "coordinator"])

    result = sign_in(db, "multi@example.com", "secret123")

    assert result.token_type == "bearer"
    assert result.roles == ["organiser", "coordinator"]
    claims = security.decode_access_token(result.access_token)
    assert claims["roles"] == ["organiser", "coordinator"]


@pytest.mark.story("SCRUM-27")
def test_sign_in_rejects_wrong_password_with_generic_error(db: Session) -> None:
    _add_user(db, "user@example.com", "secret123", ["attendee"])

    with pytest.raises(InvalidCredentialsError):
        sign_in(db, "user@example.com", "wrong-password")


@pytest.mark.story("SCRUM-27")
def test_sign_in_rejects_unknown_email_with_same_error(db: Session) -> None:
    with pytest.raises(InvalidCredentialsError):
        sign_in(db, "nobody@example.com", "whatever")


@pytest.mark.story("SCRUM-27")
async def test_login_endpoint_returns_token_for_valid_credentials(db: Session) -> None:
    _add_user(db, "user@example.com", "secret123", ["attendee"])
    app = main.create_app()
    app.dependency_overrides[get_db] = lambda: db

    response = await _post(
        app, "/api/auth/login", {"email": "user@example.com", "password": "secret123"}
    )

    assert response.status_code == 200
    assert response.json()["roles"] == ["attendee"]


@pytest.mark.story("SCRUM-27")
async def test_login_endpoint_returns_generic_401_for_invalid_credentials(
    db: Session,
) -> None:
    app = main.create_app()
    app.dependency_overrides[get_db] = lambda: db

    response = await _post(
        app, "/api/auth/login", {"email": "nobody@example.com", "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
