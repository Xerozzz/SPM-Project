"""Event request endpoints for organisers (SCRUM-46). HTTP only: parse, authorise via the
shared dependency, delegate to the service, map its exceptions to status codes."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_user, require_role
from domain.coordinator_assignment import NoAvailableCoordinatorError
from domain.event_status import EventRequestLockedError, InvalidTransitionError
from domain.roles import Role
from schemas.event_requests import EventRequestRead, EventRequestUpdate, FieldProblemRead
from services import event_requests as service

router = APIRouter(prefix="/event-requests", tags=["event-requests"])

Organiser = Annotated[dict[str, object], Depends(require_role(Role.ORGANISER))]
AnyUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]

# Everything the service or the status machine can refuse with, in one tuple so each route
# catches exactly the same set.
_REFUSALS = (
    service.EventRequestError,
    EventRequestLockedError,
    InvalidTransitionError,
    NoAvailableCoordinatorError,
)


def _organiser_id(user: dict[str, object]) -> uuid.UUID:
    """The JWT subject is the user's id (see core/security.py)."""
    return uuid.UUID(str(user["sub"]))


def _roles(user: dict[str, object]) -> list[str]:
    """Role claims from the decoded JWT, defensively typed like `require_role`."""
    roles = user.get("roles", [])
    return [str(role) for role in roles] if isinstance(roles, list) else []


def _http_error(exc: Exception) -> HTTPException:
    """The single mapping from refusals to status codes, shared by every route here."""
    if isinstance(exc, service.EventRequestNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")
    if isinstance(exc, service.NotTheOrganiserError | service.NotAuthorisedError):
        return HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    if isinstance(exc, service.IncompleteEventRequestError):
        problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
        # A literal 422: Starlette renamed its constant between the versions we allow, so
        # neither HTTP_422_UNPROCESSABLE_ENTITY nor _CONTENT exists on all of them.
        return HTTPException(422, [p.model_dump() for p in problems])
    if isinstance(exc, NoAvailableCoordinatorError):
        return HTTPException(
            status.HTTP_409_CONFLICT, "No active coordinator is available for that date"
        )
    # Locked drafts and illegal transitions are conflicts with the request's current state.
    # The message is stable and for the organiser; the exception text is for logs.
    if isinstance(exc, EventRequestLockedError):
        detail = "This request has been submitted and can no longer be edited directly"
    else:
        detail = "This request has already been submitted"
    return HTTPException(status.HTTP_409_CONFLICT, detail)


@router.get("", response_model=list[EventRequestRead])
def list_mine(user: Organiser, db: Db) -> list[EventRequestRead]:
    """The signed-in organiser's own event requests."""
    rows = service.list_for_organiser(db, _organiser_id(user))
    return [EventRequestRead.model_validate(row) for row in rows]


@router.get("/{request_id}", response_model=EventRequestRead)
def read(request_id: uuid.UUID, user: AnyUser, db: Db) -> EventRequestRead:
    """SCRUM-34: its organiser, or any Event Coordinator, may view a request and see
    its coordinator assignment. Nobody else may."""
    try:
        row = service.get(db, request_id, _organiser_id(user), _roles(user))
    except (service.EventRequestNotFoundError, service.NotAuthorisedError) as exc:
        raise _http_error(exc) from exc
    return EventRequestRead.model_validate(row)


@router.patch("/{request_id}", response_model=EventRequestRead)
def update_draft(
    request_id: uuid.UUID, body: EventRequestUpdate, user: Organiser, db: Db
) -> EventRequestRead:
    """Edit a draft. Refused with 409 once the request has been submitted (AC3)."""
    try:
        changes = body.model_dump(exclude_unset=True)
        row = service.update_draft(db, request_id, _organiser_id(user), changes)
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return EventRequestRead.model_validate(row)


@router.post("/{request_id}/submit", response_model=EventRequestRead)
def submit(request_id: uuid.UUID, user: Organiser, db: Db) -> EventRequestRead:
    """Submit a complete draft for coordinator review (AC1); 422 names missing fields (AC2)."""
    try:
        row = service.submit(db, request_id, _organiser_id(user), datetime.now(UTC))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return EventRequestRead.model_validate(row)
