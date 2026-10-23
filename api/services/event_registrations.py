"""Attendee registration orchestration; intake and confirmation remain upstream rules."""

import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.registration_intake import RegistrationIntakeError
from models.event_registration import EventRegistration
from models.event_request import EventRequest
from repositories import event_registrations as repo
from repositories import event_requests as event_repo
from services import registration_intake


class RegistrationError(Exception):
    """Base registration refusal."""


class EventNotFoundError(RegistrationError):
    pass


class DuplicateRegistrationError(RegistrationError):
    def __init__(self, registration: EventRegistration):
        self.registration = registration


def list_open_events(db: Session, now: datetime) -> list[EventRequest]:
    """Confirmed events presently available for attendee intake."""
    return [event for event in event_repo.list_confirmed(db) if _intake_open(event, now)]


def event_for_registration(db: Session, event_id: uuid.UUID, now: datetime) -> EventRequest:
    event = event_repo.get(db, event_id)
    if event is None or not _intake_open(event, now):
        raise EventNotFoundError
    return event


def submit(
    db: Session,
    event_id: uuid.UUID,
    attendee_id: uuid.UUID,
    full_name: str,
    age: int,
    phone_number: str,
    dietary_accessibility_notes: str | None,
    now: datetime,
) -> EventRegistration:
    """Create one Pending record or return the pre-existing live record as a conflict."""
    event = event_repo.get_for_update(db, event_id)
    if event is None:
        raise EventNotFoundError
    try:
        registration_intake.require_open_intake(event, now)
    except RegistrationIntakeError as exc:
        raise RegistrationError(str(exc)) from exc
    existing = repo.get_live_for_attendee(db, event.id, attendee_id)
    if existing is not None:
        raise DuplicateRegistrationError(existing)
    registration = repo.add_submission(
        db,
        event.id,
        attendee_id,
        now,
        repo.next_submission_order(db, event.id),
        full_name,
        age,
        phone_number,
        dietary_accessibility_notes,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = repo.get_live_for_attendee(db, event_id, attendee_id)
        if existing is not None:
            raise DuplicateRegistrationError(existing) from exc
        raise
    db.refresh(registration)
    return registration


def get_mine(db: Session, event_id: uuid.UUID, attendee_id: uuid.UUID) -> EventRegistration | None:
    """Current account's newest lifecycle for the event; deliberately ignores intake state."""
    return repo.get_for_attendee(db, event_id, attendee_id)


def _intake_open(event: EventRequest, now: datetime) -> bool:
    try:
        registration_intake.require_open_intake(event, now)
    except RegistrationIntakeError:
        return False
    return True
