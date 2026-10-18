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
from domain.event_request import accepts_ordinary_update
from domain.event_status import EventStatus
from domain.roles import Role
from models.event_request import EventRequest
from repositories import event_requests as event_request_repo
from repositories import users as users_repo

_bearer = HTTPBearer(auto_error=False)


class EventAccess(StrEnum):
    """The event-request access modes routes may ask for.

    VIEW and EDIT cover the request itself (SCRUM-29). The two clarification modes
    (SCRUM-30) are narrower: only the assigned coordinator may ask, only the owning
    organiser may answer, and both only while the request is under review. Reading the
    clarification history uses VIEW, so whoever may see the request may see its thread.
    """

    VIEW = "view"
    EDIT = "edit"
    DECIDE = "decide"
    SUBMIT_VENUE_BOOKING = "submit_venue_booking"
    MAINTAIN_EQUIPMENT = "maintain_equipment"
    CHECK_EQUIPMENT_AVAILABILITY = "check_equipment_availability"
    REQUEST_CLARIFICATION = "request_clarification"
    RESPOND_TO_CLARIFICATION = "respond_to_clarification"
    UPDATE_PLANNING_INFO = "update_planning_info"


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
    """Dependency factory for one event request: view it, edit it, or take part in its
    clarification exchange.

    Draft visibility is deliberately narrower than submitted visibility: coordinators may
    see submitted requests, but not drafts before submission. Organisers in the same
    organisation may see each other's requests in any status.
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

        is_owner = Role.ORGANISER.value in roles and request.organiser_id == viewer_id

        if permission is EventAccess.EDIT:
            if is_owner:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # Clarification is part of review (clarification sheet row 101), so both sides of
        # the exchange are pinned to SUBMITTED. Reading the history is not: it uses VIEW.
        if permission is EventAccess.REQUEST_CLARIFICATION:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned and request.status is EventStatus.SUBMITTED:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if permission is EventAccess.RESPOND_TO_CLARIFICATION:
            if is_owner and request.status is EventStatus.SUBMITTED:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if permission is EventAccess.DECIDE:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned and request.status is EventStatus.SUBMITTED:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-36: after submission the organiser asks the coordinator for changes, so the
        # ordinary update belongs to the assigned coordinator while the request is Submitted
        # or Approved. A Confirmed event is changed through change control instead.
        if permission is EventAccess.UPDATE_PLANNING_INFO:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned and accepts_ordinary_update(request.status):
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # Two separate permissions that happen to ask the same question today: the
        # assigned coordinator, while the event is being planned. The codebase calls that
        # phase APPROVED (see the note on ACTIVE_STATUSES), which is the "Approved or
        # Planning" SCRUM-43 AC10 describes. SUBMITTED is too early and CONFIRMED too
        # late, since AC11 sends a post-confirmation change through the significant-change
        # process instead.
        #
        # Kept as two members rather than one, because they mean different things and
        # either could be widened on its own. The rule is written once so that widening
        # one is a deliberate edit rather than two branches silently drifting apart.
        if permission in (EventAccess.MAINTAIN_EQUIPMENT, EventAccess.SUBMIT_VENUE_BOOKING):
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned and request.status is EventStatus.APPROVED:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-52 AC5: Technical Support Staff, who assess every event's equipment, and
        # the event's assigned coordinator. No status here: outside planning the service
        # answers 409, which says more than a 403 to someone who may see the event.
        if permission is EventAccess.CHECK_EQUIPMENT_AVAILABILITY:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned or Role.TECH_SUPPORT.value in roles:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if is_owner:
            return request

        if Role.ORGANISER.value in roles and _same_organisation(
            db, viewer_id, request.organiser_id
        ):
            return request

        if request.status is EventStatus.DRAFT:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-104: an ordinary Coordinator sees only the event currently assigned to
        # them. A Lead keeps allocation visibility for every event, including through a
        # dual Lead+Coordinator account, so the Lead check comes first.
        if Role.COORDINATOR_LEAD.value in roles:
            return request

        if Role.COORDINATOR.value in roles and request.coordinator_id != viewer_id:
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
