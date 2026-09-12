"""Shared auth dependencies: missing/invalid tokens get 401, wrong roles get 403."""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core import security
from core.dependencies import get_current_user, require_role


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
def test_require_role_allows_matching_role() -> None:
    token = security.create_access_token("user-id", ["organiser", "coordinator"])
    user = get_current_user(_credentials(token))

    assert require_role("coordinator")(user) == user


@pytest.mark.story("SCRUM-27")
def test_require_role_forbids_missing_role() -> None:
    token = security.create_access_token("user-id", ["attendee"])
    user = get_current_user(_credentials(token))

    with pytest.raises(HTTPException) as exc:
        require_role("organiser")(user)

    assert exc.value.status_code == 403
