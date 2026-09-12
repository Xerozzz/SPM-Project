"""Shared auth dependencies: missing/invalid/expired tokens get 401, wrong roles get 403."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core import security
from core.config import get_settings
from core.dependencies import get_current_user, require_role
from domain.roles import Role


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.story("SCRUM-27")
def test_missing_token_is_unauthenticated() -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_user(None)

    assert exc.value.status_code == 401


@pytest.mark.story("SCRUM-27")
def test_tampered_token_is_unauthenticated() -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_user(_credentials("tampered"))

    assert exc.value.status_code == 401


@pytest.mark.story("SCRUM-27")
def test_expired_token_is_unauthenticated() -> None:
    # Signed with the real secret, so the only thing wrong with it is the clock.
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    expired = jwt.encode(
        {"sub": "user-id", "roles": ["organiser"], "iat": an_hour_ago, "exp": an_hour_ago},
        get_settings().jwt_secret,
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc:
        get_current_user(_credentials(expired))

    assert exc.value.status_code == 401


@pytest.mark.story("SCRUM-27")
def test_require_role_allows_matching_role() -> None:
    token = security.create_access_token("user-id", ["organiser", "coordinator"])
    user = get_current_user(_credentials(token))

    assert require_role(Role.COORDINATOR)(user) == user


@pytest.mark.story("SCRUM-27")
def test_require_role_forbids_missing_role() -> None:
    token = security.create_access_token("user-id", ["attendee"])
    user = get_current_user(_credentials(token))

    with pytest.raises(HTTPException) as exc:
        require_role(Role.ORGANISER)(user)

    assert exc.value.status_code == 403


@pytest.mark.story("SCRUM-27")
def test_require_role_forbids_a_malformed_roles_claim() -> None:
    token = jwt.encode(
        {"sub": "user-id", "roles": "organiser"},  # a string, not a list
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    user = get_current_user(_credentials(token))

    with pytest.raises(HTTPException) as exc:
        require_role(Role.ORGANISER)(user)

    assert exc.value.status_code == 403


@pytest.mark.story("SCRUM-27")
def test_require_role_forbids_a_roles_claim_with_non_string_elements() -> None:
    # A list, so it passes the shape check — but its element is not a role name and is not
    # even hashable. This must be a 403, not a TypeError escaping as a 500.
    token = jwt.encode(
        {"sub": "user-id", "roles": [{}]},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    user = get_current_user(_credentials(token))

    with pytest.raises(HTTPException) as exc:
        require_role(Role.ORGANISER)(user)

    assert exc.value.status_code == 403
