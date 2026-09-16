"""Shared authorisation dependencies. Routers use these; never inline role checks."""

import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import decode_access_token
from domain.event_status import EventStatus
from domain.roles import Role
from models.event_request import EventRequest
from repositories import event_requests as event_request_repo
from repositories import users as users_repo

_bearer = HTTPBearer(auto_error=False)


class EventAccess(StrEnum):
    """The event-request access modes routes may ask for."""

    VIEW = "view"
    EDIT = "edit"


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, object]:
    """Return the JWT claims, or 401 when missing or invalid."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return decode_access_token(credentials.credentials)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        ) from exc


def require_role(*allowed: Role) -> Callable[[dict[str, object]], dict[str, object]]:
    """Dependency factory: allow only tokens carrying one of the given roles.

    Takes `Role` members, not strings, so a misspelt role fails at import time rather than
    as a 403 nobody can explain.
    """
    allowed_values = {role.value for role in allowed}

    def check(
        user: Annotated[dict[str, object], Depends(get_current_user)],
    ) -> dict[str, object]:
        if not allowed_values & _granted_roles(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return check


def require_event_access(permission: EventAccess) -> Callable[..., EventRequest]:
    """Dependency factory for reading or editing one event request.

    Draft visibility is deliberately narrower than submitted visibility:
    coordinators may see submitted requests, but not drafts before submission.
    """

    def check(
        request_id: uuid.UUID,
        user: Annotated[dict[str, object], Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> EventRequest:
        request = event_request_repo.get(db, request_id)
        if request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Event request not found"
            )

        roles = _granted_roles(user)
        viewer_id = _user_id(user)

        if permission is EventAccess.EDIT:
            if Role.ORGANISER.value in roles and request.organiser_id == viewer_id:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if Role.ORGANISER.value in roles and request.organiser_id == viewer_id:
            return request

        if request.status is EventStatus.DRAFT:
            if Role.ORGANISER.value in roles and _same_organisation(
                db, viewer_id, request.organiser_id
            ):
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if Role.COORDINATOR.value in roles:
            return request

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return check


def _granted_roles(user: dict[str, object]) -> set[str]:
    # Only string elements count as roles. The claim is ours and signed, but a malformed
    # one (say, `roles: [{}]`) must still be a 403, not a TypeError from set arithmetic.
    claimed = user.get("roles")
    return (
        {role for role in claimed if isinstance(role, str)} if isinstance(claimed, list) else set()
    )


def _user_id(user: dict[str, object]) -> uuid.UUID:
    try:
        return uuid.UUID(str(user["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc


def _same_organisation(db: Session, viewer_id: uuid.UUID, organiser_id: uuid.UUID) -> bool:
    viewer = users_repo.get(db, viewer_id)
    organiser = users_repo.get(db, organiser_id)
    return (
        viewer is not None
        and organiser is not None
        and viewer.organisation_id == organiser.organisation_id
    )
