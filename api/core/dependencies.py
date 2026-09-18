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

_bearer = HTTPBearer(auto_error=False)


class EventAccess(StrEnum):
    """The event-request access modes routes may ask for."""

    VIEW_CLARIFICATIONS = "view_clarifications"
    REQUEST_CLARIFICATION = "request_clarification"
    RESPOND_TO_CLARIFICATION = "respond_to_clarification"


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
        # Only string elements count as roles. The claim is ours and signed, but a malformed
        # one (say, `roles: [{}]`) must still be a 403, not a TypeError from set arithmetic.
        claimed = user.get("roles")
        granted = (
            {role for role in claimed if isinstance(role, str)}
            if isinstance(claimed, list)
            else set()
        )
        if not allowed_values & granted:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return check


def require_event_access(permission: EventAccess) -> Callable[..., EventRequest]:
    """Authorize one participant's access to an event-review clarification thread.

    Coordinator assignment is not present on this branch. Until it lands, coordinators
    may review any submitted request; drafts remain private to their organiser. Once
    assignment is merged, clarification creation must be restricted to the assigned
    coordinator. Other coordinators may retain read-only visibility.
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
        user_id = _user_id(user)
        is_owner = Role.ORGANISER.value in roles and request.organiser_id == user_id
        is_coordinator = Role.COORDINATOR.value in roles
        is_submitted = request.status is EventStatus.SUBMITTED

        if permission is EventAccess.REQUEST_CLARIFICATION:
            allowed = is_coordinator and is_submitted
        elif permission is EventAccess.RESPOND_TO_CLARIFICATION:
            allowed = is_owner and is_submitted
        else:
            allowed = is_owner or (is_coordinator and is_submitted)

        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return request

    return check


def _granted_roles(user: dict[str, object]) -> set[str]:
    claimed = user.get("roles")
    return (
        {role for role in claimed if isinstance(role, str)} if isinstance(claimed, list) else set()
    )


def _user_id(user: dict[str, object]) -> uuid.UUID:
    try:
        return uuid.UUID(str(user["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
