"""Event request orchestration for SCRUM-46 (list, edit a draft, submit for review) and
SCRUM-101 (unassigned queue for manual Coordinator Lead assignment).

Each function loads the request, checks the caller owns it, asks the domain layer whether
the action is allowed, and persists the outcome. Every failure is a typed exception so the
router can map it to a status code without knowing any of the rules.
"""

import uuid
from datetime import datetime
from typing import cast

from core.database import Session
from domain import event_status
from domain.event_request import (
    EventRequestFields,
    FieldProblem,
    field_names,
    validate_catalogue_requirements,
    validate_event_request,
)
from domain.roles import Role
from models.event_request import EventRequest
from models.user import User
from repositories import event_requests as repo
from repositories import users as users_repo


class EventRequestError(Exception):
    """Base for every failure this service reports."""


class EventRequestNotFoundError(EventRequestError):
    """No request has that id."""


class NotTheOrganiserError(EventRequestError):
    """The request exists but belongs to a different organiser."""


class NotAuthorisedError(EventRequestError):
    """The actor does not hold the request-specific permission."""


class IncompleteEventRequestError(EventRequestError):
    """AC2: the request cannot be submitted until these fields are fixed."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("event request is not complete")
        self.problems = problems


class AlreadyAssignedError(EventRequestError):
    """SCRUM-98: the request already has an owner, so initial assignment is refused."""


class InvalidAssigneeError(EventRequestError):
    """SCRUM-98: the chosen owner is not an active Event Coordinator."""


def list_for_organiser(db: Session, organiser_id: uuid.UUID) -> list[EventRequest]:
    """The organiser's own requests, newest first."""
    return repo.list_for_organiser(db, organiser_id)


def list_for_review(db: Session) -> list[EventRequest]:
    """Submitted requests visible to coordinators for review and planning."""
    return repo.list_submitted(db)


def list_bookable_for_coordinator(db: Session, coordinator_id: uuid.UUID) -> list[EventRequest]:
    """Approved requests assigned to this coordinator for venue booking."""
    return repo.list_bookable_for_coordinator(db, coordinator_id)


def create(
    db: Session, organiser_id: uuid.UUID, fields: EventRequestFields, now: datetime
) -> EventRequest:
    """Create a new request without submitting or allocating anything."""
    problems = validate_event_request(fields, now)
    if problems:
        raise IncompleteEventRequestError(problems)
    request = EventRequest(organiser_id=organiser_id, **fields.__dict__)
    return repo.save(db, repo.add(db, request))


def list_visible_drafts_for_organiser(db: Session, organiser_id: uuid.UUID) -> list[EventRequest]:
    """Drafts visible to this organiser through their organisation membership."""
    organiser = _user_or_forbidden(db, organiser_id)
    return repo.list_drafts_for_organisation(db, organiser.organisation_id)


def create_draft(db: Session, organiser_id: uuid.UUID, fields: dict[str, object]) -> EventRequest:
    """SCRUM-29: save a new incomplete draft for the current organiser.

    Draft creation deliberately does not call `validate_for_submission`; completeness is
    checked only when the organiser submits the request for review.
    """
    request = EventRequest(organiser_id=organiser_id, **fields)
    return repo.save(db, request)


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

    SCRUM-101 (Week 7 manual-assignment policy): submission leaves the request
    unassigned. A Coordinator Lead assigns it later (SCRUM-98). See ADR-0020.
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
    return repo.save(db, request)


def list_unassigned_for_lead(db: Session) -> list[repo.UnassignedRow]:
    """SCRUM-101: unassigned Submitted requests for the Coordinator Lead queue."""
    return repo.list_unassigned_submitted(db)


def list_active_for_lead(db: Session) -> list[repo.ActiveRow]:
    """SCRUM-100: every active request with its current coordinator for the Lead overview."""
    return repo.list_active_for_lead(db)


def list_assignable_coordinators(db: Session) -> list[User]:
    """SCRUM-98: active Event Coordinators the Lead may pick as the owner."""
    return users_repo.list_active_coordinators(db)


def assign_coordinator(
    db: Session, request_id: uuid.UUID, coordinator_id: uuid.UUID, now: datetime
) -> EventRequest:
    """SCRUM-98: a Lead assigns an unassigned Submitted request to an active coordinator.

    The row is locked before checking `coordinator_id is None`, so two Leads assigning
    the same request serialise here: the winner commits first and the loser then sees
    an owner and receives AlreadyAssignedError rather than silently overwriting.
    """
    request = repo.get_for_update(db, request_id)
    if request is None:
        raise EventRequestNotFoundError
    if request.status is not event_status.EventStatus.SUBMITTED:
        raise AlreadyAssignedError
    if request.coordinator_id is not None:
        raise AlreadyAssignedError
    candidate = users_repo.get(db, coordinator_id)
    if (
        candidate is None
        or not candidate.is_active
        or Role.COORDINATOR.value not in list(candidate.roles)
    ):
        raise InvalidAssigneeError
    request.coordinator_id = candidate.id
    request.assigned_at = now
    return repo.save(db, request)


def approve(
    db: Session, request_id: uuid.UUID, coordinator_id: uuid.UUID, now: datetime
) -> EventRequest:
    """Record an approval. This deliberately allocates no venue, equipment or registration."""
    request = _for_decision(db, request_id, coordinator_id)
    request.status = event_status.approve(request.status)
    request.decided_by_id = coordinator_id
    request.decided_at = now
    request.rejection_reason = None
    return repo.save(db, request)


def reject(
    db: Session, request_id: uuid.UUID, coordinator_id: uuid.UUID, reason: str, now: datetime
) -> EventRequest:
    """Record a rejection and its mandatory coordinator-supplied reason."""
    request = _for_decision(db, request_id, coordinator_id)
    request.status = event_status.reject(request.status)
    request.decided_by_id = coordinator_id
    request.decided_at = now
    request.rejection_reason = reason.strip()
    return repo.save(db, request)


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


def _user_or_forbidden(db: Session, user_id: uuid.UUID) -> User:
    user = users_repo.get(db, user_id)
    if user is None:
        raise NotTheOrganiserError
    return user


def _for_decision(db: Session, request_id: uuid.UUID, coordinator_id: uuid.UUID) -> EventRequest:
    """Lock a request before applying a coordinator decision."""
    request = repo.get_for_update(db, request_id)
    if request is None:
        raise EventRequestNotFoundError
    if request.coordinator_id != coordinator_id:
        raise NotAuthorisedError
    return request


def _fields_of(request: EventRequest) -> EventRequestFields:
    """Copy the ORM row's content into the domain's plain value object."""
    return EventRequestFields(**{name: getattr(request, name) for name in field_names()})
