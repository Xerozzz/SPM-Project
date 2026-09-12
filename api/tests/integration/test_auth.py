"""F1 sign-in: valid credentials issue a JWT with role claims; invalid ones get a
generic 401 that never says whether the account exists."""

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.orm import Session

from core import security
from domain.roles import Role
from models.user import User
from services.auth import InvalidCredentialsError, sign_in

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]

PASSWORD = "password123"  # what make_user hashes; see tests/integration/conftest.py


@pytest.mark.story("SCRUM-27")
def test_sign_in_returns_token_with_role_claims(db: Session, make_user: MakeUser) -> None:
    user = make_user(Role.ORGANISER, Role.COORDINATOR)

    result = sign_in(db, user.email, PASSWORD)

    assert result.token_type == "bearer"
    assert result.roles == ["organiser", "coordinator"]
    claims = security.decode_access_token(result.access_token)
    assert claims["sub"] == str(user.id)
    assert claims["roles"] == ["organiser", "coordinator"]


@pytest.mark.story("SCRUM-27")
def test_sign_in_rejects_wrong_password_with_generic_error(
    db: Session, make_user: MakeUser
) -> None:
    user = make_user(Role.ATTENDEE)

    with pytest.raises(InvalidCredentialsError):
        sign_in(db, user.email, "wrong-password")


@pytest.mark.story("SCRUM-27")
def test_sign_in_rejects_unknown_email_with_same_error(db: Session) -> None:
    with pytest.raises(InvalidCredentialsError):
        sign_in(db, "nobody@example.com", "whatever")


@pytest.mark.story("SCRUM-27")
def test_sign_in_treats_an_over_long_password_as_wrong_not_as_a_crash(
    db: Session, make_user: MakeUser
) -> None:
    # Over bcrypt's 72-byte limit. core.security refuses it before bcrypt sees it, so this
    # is a normal failed login on every supported bcrypt version.
    user = make_user(Role.ATTENDEE)

    with pytest.raises(InvalidCredentialsError):
        sign_in(db, user.email, "a" * 80)


@pytest.mark.story("SCRUM-27")
async def test_login_endpoint_returns_token_for_valid_credentials(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    user = make_user(Role.ATTENDEE)

    async with make_client(None) as client:
        response = await client.post(
            "/api/auth/login", json={"email": user.email, "password": PASSWORD}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["attendee"]
    # The UI relies on this field; a plain @property would silently leave it out.
    assert body["token_type"] == "bearer"


@pytest.mark.story("SCRUM-27")
async def test_login_endpoint_returns_generic_401_for_invalid_credentials(
    make_client: MakeClient,
) -> None:
    async with make_client(None) as client:
        response = await client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


@pytest.mark.story("SCRUM-27")
async def test_login_endpoint_returns_401_not_500_for_an_over_long_password(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    user = make_user(Role.ATTENDEE)

    async with make_client(None) as client:
        response = await client.post(
            "/api/auth/login", json={"email": user.email, "password": "a" * 80}
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
