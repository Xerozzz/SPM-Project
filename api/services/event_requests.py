"""Event request orchestration for SCRUM-46 (list, edit a draft, submit for review) and
SCRUM-34 (auto-assign an Event Coordinator on first submission).

Each function loads the request, checks the caller owns it, asks the domain layer whether
the action is allowed, and persists the outcome. Every failure is a typed exception so the
router can map it to a status code without knowing any of the rules.
"""

import uuid
from datetime import datetime
from typing import cast

from core.database import Session
from domain import event_status
from domain.coordinator_assignment import select_next_coordinator
from domain.event_request import (
    EventRequestFields,
    FieldProblem,
    field_names,
    validate_catalogue_requirements,
    validate_event_request,
)
from domain.roles import Role
from models.event_request import EventRequest
from repositories import event_requests as repo
from repositories import users as users_repo


class EventRequestError(Exception):
    """Base for every failure this service reports."""


class EventRequestNotFoundError(EventRequestError):
    """No request has that id."""


class NotTheOrganiserError(EventRequestError):
    """The request exists but belongs to a different organiser."""


class NotAuthorisedError(EventRequestError):
    """SCRUM-34: neither the owning organiser nor a coordinator may view this request."""


class IncompleteEventRequestError(EventRequestError):
    """AC2: the request cannot be submitted until these fields are fixed."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("event request is not complete")
        self.problems = problems


def list_for_organiser(db: Session, organiser_id: uuid.UUID) -> list[EventRequest]:
    """The organiser's own requests, newest first."""
    return repo.list_for_organiser(db, organiser_id)


def get(
    db: Session, request_id: uuid.UUID, actor_id: uuid.UUID, actor_roles: list[str]
) -> EventRequest:
    """SCRUM-34: its organiser, or any Event Coordinator, may view a request — including
    its coordinator assignment. Nobody else may, and nobody but the organiser may edit it
    (see routers/event_requests.py: the edit and submit routes stay organiser-only)."""
    request = repo.get(db, request_id)
    if request is None:
        raise EventRequestNotFoundError
    is_owner = request.organiser_id == actor_id
    if not (is_owner or Role.COORDINATOR.value in actor_roles):
        raise NotAuthorisedError
    return request


def create(
    db: Session, organiser_id: uuid.UUID, fields: EventRequestFields, now: datetime
) -> EventRequest:
    """Create a new request without submitting or allocating anything."""
    problems = validate_event_request(fields, now)
    if problems:
        raise IncompleteEventRequestError(problems)
    request = EventRequest(organiser_id=organiser_id, **fields.__dict__)
    return repo.save(db, repo.add(db, request))


def update_draft(
    db: Session, request_id: uuid.UUID, organiser_id: uuid.UUID, changes: dict[str, object]
) -> EventRequest:
    """AC3: apply field changes to a request, which must still be a draft."""
    request = _owned_by(db, request_id, organiser_id)
    event_status.ensure_editable(request.status)
    catalogue_changes = EventRequestFields(
        venue_requirement=cast(str | None, changes.get("venue_requirement")),
        equipment_requirement=cast(str | None, changes.get("equipment_requirement")),
    )
    problems = validate_catalogue_requirements(catalogue_changes)
    if problems:
        raise IncompleteEventRequestError(problems)
    for name in field_names():
        if name in changes:
            setattr(request, name, changes[name])
    return repo.save(db, request)


def submit(
    db: Session, request_id: uuid.UUID, organiser_id: uuid.UUID, now: datetime
) -> EventRequest:
    """AC1/AC2: move a complete draft to SUBMITTED; refuse an incomplete one, naming the
    fields. AC4 holds by construction — nothing here touches venues, equipment or
    registration, and no other code runs on submission.

    SCRUM-34: this is also the only way a request becomes SUBMITTED, so it is the one
    place that can be "first submission" — a coordinator is assigned here, once. A
    request that already has one (because the transition table let it be submitted more
    than once, e.g. after a future clarification round) is left alone.
    """
    # Locked read: two organisers' browsers double-clicking "Submit" at the same instant
    # serialise here, and the second sees SUBMITTED and gets a 409 rather than a second
    # success. See repositories.event_requests.get_for_update.
    request = _owned_by(db, request_id, organiser_id, lock=True)
    problems = validate_event_request(_fields_of(request), now)
    if problems:
        raise IncompleteEventRequestError(problems)
    # The only place status changes, and the value comes from the state machine
    # (AGENTS.md §3). InvalidTransitionError propagates if the request is not a draft.
    request.status = event_status.submit(request.status)
    request.submitted_at = now
    if request.coordinator_id is None:
        _assign_coordinator(db, request, now)
    return repo.save(db, request)


def _assign_coordinator(db: Session, request: EventRequest, now: datetime) -> None:
    """SCRUM-34: round-robin over active coordinators, skipping anyone already
    confirmed for that date. Raises NoAvailableCoordinatorError if none are free."""
    assert request.start_at is not None
    pool = [coordinator.id for coordinator in users_repo.list_active_coordinators(db)]
    last_assigned = repo.last_assigned_coordinator_id(db)
    unavailable = repo.coordinator_ids_confirmed_on(db, request.start_at)
    request.coordinator_id = select_next_coordinator(pool, last_assigned, unavailable)
    request.assigned_at = now


def _owned_by(
    db: Session, request_id: uuid.UUID, organiser_id: uuid.UUID, *, lock: bool = False
) -> EventRequest:
    """Load the request, or raise if it is missing or not the caller's.

    `lock=True` performs a locked read (SELECT ... FOR UPDATE): both callers that pass it
    change the row, so two browsers double-clicking at the same instant serialise here and
    the second one sees the first one's result. See repositories.event_requests.get_for_update.
    """
    request = repo.get_for_update(db, request_id) if lock else repo.get(db, request_id)
    if request is None:
        raise EventRequestNotFoundError
    if request.organiser_id != organiser_id:
        raise NotTheOrganiserError
    return request


def _fields_of(request: EventRequest) -> EventRequestFields:
    """Copy the ORM row's content into the domain's plain value object."""
    return EventRequestFields(**{name: getattr(request, name) for name in field_names()})