"""Event request orchestration for SCRUM-46: list, edit a draft, submit for review.

Each function loads the request, checks the caller owns it, asks the domain layer whether
the action is allowed, and persists the outcome. Every failure is a typed exception so the
router can map it to a status code without knowing any of the rules.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from domain import event_status
from domain.event_request import (
    EventRequestFields,
    FieldProblem,
    field_names,
    validate_for_submission,
)
from models.event_request import EventRequest
from repositories import event_requests as repo


class EventRequestError(Exception):
    """Base for every failure this service reports."""


class EventRequestNotFoundError(EventRequestError):
    """No request has that id."""


class NotTheOrganiserError(EventRequestError):
    """The request exists but belongs to a different organiser."""


class IncompleteEventRequestError(EventRequestError):
    """AC2: the request cannot be submitted until these fields are fixed."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("event request is not complete")
        self.problems = problems


def list_for_organiser(db: Session, organiser_id: uuid.UUID) -> list[EventRequest]:
    """The organiser's own requests, newest first."""
    return repo.list_for_organiser(db, organiser_id)


def update_draft(
    db: Session, request_id: uuid.UUID, organiser_id: uuid.UUID, changes: dict[str, object]
) -> EventRequest:
    """AC3: apply field changes to a request, which must still be a draft."""
    request = _owned_by(db, request_id, organiser_id, lock=True)
    event_status.ensure_editable(request.status)
    for name in field_names():
        if name in changes:
            setattr(request, name, changes[name])
    return repo.save(db, request)


def submit(
    db: Session, request_id: uuid.UUID, organiser_id: uuid.UUID, now: datetime
) -> EventRequest:
    """AC1/AC2: move a complete draft to SUBMITTED; refuse an incomplete one, naming the
    fields. AC4 holds by construction — nothing here touches venues, equipment or
    registration, and no other code runs on submission."""
    # Locked read: two organisers' browsers double-clicking "Submit" at the same instant
    # serialise here, and the second sees SUBMITTED and gets a 409 rather than a second
    # success. See repositories.event_requests.get_for_update.
    request = _owned_by(db, request_id, organiser_id, lock=True)
    problems = validate_for_submission(_fields_of(request), now)
    if problems:
        raise IncompleteEventRequestError(problems)
    # The only place status changes, and the value comes from the state machine
    # (AGENTS.md §3). InvalidTransitionError propagates if the request is not a draft.
    request.status = event_status.submit(request.status)
    request.submitted_at = now
    return repo.save(db, request)


def _owned_by(
    db: Session, request_id: uuid.UUID, organiser_id: uuid.UUID, *, lock: bool = False
) -> EventRequest:
    request = repo.get_for_update(db, request_id) if lock else repo.get(db, request_id)
    if request is None:
        raise EventRequestNotFoundError
    if request.organiser_id != organiser_id:
        raise NotTheOrganiserError
    return request


def _fields_of(request: EventRequest) -> EventRequestFields:
    """Copy the ORM row's content into the domain's plain value object."""
    return EventRequestFields(**{name: getattr(request, name) for name in field_names()})
