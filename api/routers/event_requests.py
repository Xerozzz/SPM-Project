"""Event request endpoints for organisers (SCRUM-46). HTTP only: parse, authorise via the
shared dependency, delegate to the service, map its exceptions to status codes."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, require_event_access, require_role
from domain.event_request import EventRequestFields
from domain.event_status import EventRequestLockedError, InvalidTransitionError
from domain.roles import Role
from models.event_request import EventRequest
from schemas.event_requests import (
    ActiveAssignmentRead,
    AssignableCoordinatorRead,
    AssignmentHistoryRead,
    CancelledEventRead,
    EventCalendarEntryRead,
    EventRequestAssign,
    EventRequestCreate,
    EventRequestDraftCreate,
    EventRequestPlanningUpdate,
    EventRequestRead,
    EventRequestReassign,
    EventRequestRejection,
    EventRequestUpdate,
    FieldProblemRead,
    UnassignedEventRequestRead,
)
from services import equipment as equipment_service
from services import event_requests as service
from services import venues as venues_service

router = APIRouter(prefix="/event-requests", tags=["event-requests"])

Organiser = Annotated[dict[str, object], Depends(require_role(Role.ORGANISER))]
ViewableEventRequest = Annotated[EventRequest, Depends(require_event_access(EventAccess.VIEW))]
EditableEventRequest = Annotated[EventRequest, Depends(require_event_access(EventAccess.EDIT))]
DecidableEventRequest = Annotated[EventRequest, Depends(require_event_access(EventAccess.DECIDE))]
PlanningUpdatableEventRequest = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.UPDATE_PLANNING_INFO))
]
HistoryReadableEventRequest = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.READ_ASSIGNMENT_HISTORY))
]
Coordinator = Annotated[dict[str, object], Depends(require_role(Role.COORDINATOR))]
CoordinatorLead = Annotated[dict[str, object], Depends(require_role(Role.COORDINATOR_LEAD))]
Db = Annotated[Session, Depends(get_db)]

# Everything the service or the status machine can refuse with, in one tuple so each route
# catches exactly the same set.
_REFUSALS = (
    service.EventRequestError,
    EventRequestLockedError,
    InvalidTransitionError,
)


def _organiser_id(user: dict[str, object]) -> uuid.UUID:
    """The JWT subject is the user's id (see core/security.py)."""
    return uuid.UUID(str(user["sub"]))


def _coordinator_id(user: dict[str, object]) -> uuid.UUID:
    """The coordinator's signed JWT subject is the decision record's actor."""
    return uuid.UUID(str(user["sub"]))


def _http_error(exc: Exception) -> HTTPException:
    """The single mapping from refusals to status codes, shared by every route here."""
    if isinstance(exc, service.EventRequestNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")
    if isinstance(exc, service.NotTheOrganiserError | service.NotAuthorisedError):
        return HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    if isinstance(exc, service.InvalidAssigneeError):
        return HTTPException(422, [{"field": "coordinator_id", "reason": "is not valid"}])
    if isinstance(exc, service.StaleAssignmentError):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            "This request was reassigned by someone else — refresh and try again",
        )
    if isinstance(exc, service.AlreadyAssignedError):
        return HTTPException(status.HTTP_409_CONFLICT, "This request already has an owner")
    if isinstance(exc, service.IncompleteEventRequestError):
        problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
        # A literal 422: Starlette renamed its constant between the versions we allow, so
        # neither HTTP_422_UNPROCESSABLE_ENTITY nor _CONTENT exists on all of them.
        return HTTPException(422, [p.model_dump() for p in problems])
    # Locked drafts and illegal transitions are conflicts with the request's current state.
    # The message is stable and for the organiser; the exception text is for logs.
    if isinstance(exc, EventRequestLockedError):
        detail = "This request has been submitted and can no longer be edited directly"
    else:
        detail = "This request has already been submitted"
    return HTTPException(status.HTTP_409_CONFLICT, detail)


@router.get("/unassigned", response_model=list[UnassignedEventRequestRead])
def list_unassigned_queue(_user: CoordinatorLead, db: Db) -> list[UnassignedEventRequestRead]:
    """SCRUM-101: unassigned Submitted requests, oldest submission first.

    Static route declared above `/{request_id}` so FastAPI matches it literally.
    """
    rows = service.list_unassigned_for_lead(db)
    return [UnassignedEventRequestRead.from_row(request, email) for request, email in rows]


@router.get("/assignable-coordinators", response_model=list[AssignableCoordinatorRead])
def list_assignable_coordinators(_user: CoordinatorLead, db: Db) -> list[AssignableCoordinatorRead]:
    """SCRUM-98: active Event Coordinators the Lead may pick as the owner.

    Static route declared above `/{request_id}` so FastAPI matches it literally.
    """
    rows = service.list_assignable_coordinators(db)
    return [AssignableCoordinatorRead.model_validate(row) for row in rows]


@router.get("/active-assignments", response_model=list[ActiveAssignmentRead])
def list_active_assignments(_user: CoordinatorLead, db: Db) -> list[ActiveAssignmentRead]:
    """SCRUM-100: every active request with its current coordinator or Unassigned.

    Static route declared above `/{request_id}` so FastAPI matches it literally.
    """
    rows = service.list_active_for_lead(db)
    return [
        ActiveAssignmentRead.from_row(request, organiser_email, coordinator_email)
        for request, organiser_email, coordinator_email in rows
    ]


@router.get("/cancelled", response_model=list[CancelledEventRead])
def list_cancelled_events(_user: CoordinatorLead, db: Db) -> list[CancelledEventRead]:
    """SCRUM-88 AC6: every cancelled event, so a Lead can open its history.

    Static route declared above `/{request_id}` so FastAPI matches it literally.
    """
    rows = service.list_cancelled_for_lead(db)
    return [CancelledEventRead.model_validate(row) for row in rows]


@router.post("/{request_id}/assign", response_model=EventRequestRead)
def assign_coordinator(
    request_id: uuid.UUID, body: EventRequestAssign, user: CoordinatorLead, db: Db
) -> EventRequestRead:
    """SCRUM-98: a Lead assigns an unassigned Submitted request to an active coordinator."""
    try:
        row = service.assign_coordinator(
            db, request_id, body.coordinator_id, datetime.now(UTC), _coordinator_id(user)
        )
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return EventRequestRead.model_validate(row)


@router.post("/{request_id}/reassign", response_model=EventRequestRead)
def reassign_coordinator(
    request_id: uuid.UUID, body: EventRequestReassign, user: CoordinatorLead, db: Db
) -> EventRequestRead:
    """SCRUM-97: a Lead moves an active assigned request to another active coordinator."""
    try:
        row = service.reassign_coordinator(
            db,
            request_id,
            body.coordinator_id,
            body.expected_current_coordinator_id,
            _coordinator_id(user),
            datetime.now(UTC),
        )
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return EventRequestRead.model_validate(row)


@router.get("/{request_id}/assignment-history", response_model=list[AssignmentHistoryRead])
def list_assignment_history(
    request: HistoryReadableEventRequest, db: Db
) -> list[AssignmentHistoryRead]:
    """SCRUM-97: the request's assignment history, oldest first. SCRUM-105: readable by
    a Lead, the owning Organiser and the current assigned Coordinator (ADR-0047).

    Static suffix route declared above `/{request_id}` so FastAPI matches it literally.
    """
    rows = service.list_assignment_history(db, request)
    return [AssignmentHistoryRead.from_row(*row) for row in rows]


@router.get("", response_model=list[EventRequestRead])
def list_mine(user: Organiser, db: Db) -> list[EventRequestRead]:
    """The signed-in organiser's own event requests."""
    rows = service.list_for_organiser(db, _organiser_id(user))
    return [EventRequestRead.model_validate(row) for row in rows]


@router.post("", response_model=EventRequestRead, status_code=status.HTTP_201_CREATED)
def create_event_request(body: EventRequestCreate, user: Organiser, db: Db) -> EventRequestRead:
    """Create a complete event request without submitting it for review."""
    fields = EventRequestFields(**body.model_dump())
    try:
        row = service.create(db, _organiser_id(user), fields, datetime.now(UTC))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return EventRequestRead.model_validate(row)


@router.post("/drafts", response_model=EventRequestRead, status_code=status.HTTP_201_CREATED)
def create_draft(body: EventRequestDraftCreate, user: Organiser, db: Db) -> EventRequestRead:
    """Save a new draft. Submission-only validation is not run here (SCRUM-29)."""
    row = service.create_draft(db, _organiser_id(user), body.model_dump(exclude_unset=True))
    return EventRequestRead.model_validate(row)


@router.get("/drafts", response_model=list[EventRequestRead])
def list_drafts(user: Organiser, db: Db) -> list[EventRequestRead]:
    """SCRUM-112: the signed-in organiser's own drafts."""
    rows = service.list_drafts_for_organiser(db, _organiser_id(user))
    return [EventRequestRead.model_validate(row) for row in rows]


@router.get("/bookable", response_model=list[EventRequestRead])
def list_bookable_events(user: Coordinator, db: Db) -> list[EventRequestRead]:
    """Approved assigned requests this coordinator may submit for venue booking."""
    rows = service.list_bookable_for_coordinator(db, _coordinator_id(user))
    return [EventRequestRead.model_validate(row) for row in rows]


@router.get("/assigned-confirmed", response_model=list[EventRequestRead])
def list_confirmed_events(user: Coordinator, db: Db) -> list[EventRequestRead]:
    """Confirmed events assigned to this Coordinator for read-only operational settings."""
    rows = service.list_confirmed_for_coordinator(db, _coordinator_id(user))
    return [EventRequestRead.model_validate(row) for row in rows]


@router.get("/assigned-cancelled", response_model=list[CancelledEventRead])
def list_assigned_cancelled_events(user: Coordinator, db: Db) -> list[CancelledEventRead]:
    """SCRUM-88 AC6: cancelled events assigned to this Coordinator, to open their history."""
    rows = service.list_cancelled_for_coordinator(db, _coordinator_id(user))
    return [CancelledEventRead.model_validate(row) for row in rows]


@router.get("/organisation-calendar", response_model=list[EventCalendarEntryRead])
def organisation_calendar(user: Organiser, db: Db) -> list[EventCalendarEntryRead]:
    """SCRUM-87: dated events in the signed-in organiser's organisation."""
    try:
        rows = service.list_organisation_calendar(db, _organiser_id(user))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return [EventCalendarEntryRead.model_validate(row) for row in rows]


@router.get("/equipment-types", response_model=list[str])
def list_equipment_types(_user: Organiser, db: Db) -> list[str]:
    """Catalogue equipment types an organiser may select for a new request."""
    return equipment_service.list_distinct_types(db)


@router.get("/venue-names", response_model=list[str])
def list_venue_names(_user: Organiser, db: Db) -> list[str]:
    """Active catalogue venues an organiser may select for a new request."""
    return venues_service.list_selectable_names(db)


@router.get("/{request_id}", response_model=EventRequestRead)
def get_event_request(request: ViewableEventRequest) -> EventRequestRead:
    """Return an event request visible to the signed-in user."""
    return EventRequestRead.model_validate(request)


@router.patch("/{request_id}", response_model=EventRequestRead)
def update_draft(
    request: EditableEventRequest, body: EventRequestUpdate, user: Organiser, db: Db
) -> EventRequestRead:
    """Edit a draft. Refused with 409 once the request has been submitted (AC3)."""
    try:
        changes = body.model_dump(exclude_unset=True)
        row = service.update_draft(db, request.id, _organiser_id(user), changes)
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return EventRequestRead.model_validate(row)


@router.patch("/{request_id}/planning-info", response_model=EventRequestRead)
def update_planning_info(
    event: PlanningUpdatableEventRequest,
    body: EventRequestPlanningUpdate,
    user: Coordinator,
    db: Db,
) -> EventRequestRead:
    """SCRUM-36: the assigned coordinator updates ordinary planning information (AC2).
    Other fields are refused by the schema (AC3) and other users get 403 (AC4)."""
    try:
        changes = body.model_dump(exclude_unset=True)
        row = service.update_planning_info(db, event.id, _coordinator_id(user), changes)
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


@router.post("/{request_id}/approve", response_model=EventRequestRead)
def approve(event: DecidableEventRequest, user: Coordinator, db: Db) -> EventRequestRead:
    """Approve one submitted request; planning remains a separate later action."""
    try:
        row = service.approve(db, event.id, _coordinator_id(user), datetime.now(UTC))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return EventRequestRead.model_validate(row)


@router.post("/{request_id}/reject", response_model=EventRequestRead)
def reject(
    event: DecidableEventRequest, body: EventRequestRejection, user: Coordinator, db: Db
) -> EventRequestRead:
    """Reject one submitted request with the reason validated by the request schema."""
    try:
        row = service.reject(db, event.id, _coordinator_id(user), body.reason, datetime.now(UTC))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return EventRequestRead.model_validate(row)
