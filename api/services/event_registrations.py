"""Attendee registration orchestration; intake and confirmation remain upstream rules."""

import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.registration import RegistrationStatus
from domain.registration_decision import RegistrationDecisionError
from domain.registration_decision import decide as permitted_decision
from domain.registration_intake import RegistrationIntakeError
from models.event_registration import EventRegistration
from models.event_request import EventRequest
from repositories import event_registrations as repo
from repositories import event_requests as event_repo
from services import registration_intake, registration_notifications


class RegistrationError(Exception):
    """Base registration refusal."""


class EventNotFoundError(RegistrationError):
    pass


class DuplicateRegistrationError(RegistrationError):
    def __init__(self, registration: EventRegistration):
        self.registration = registration


class RegistrationNotFoundError(RegistrationError):
    pass


class WithdrawalNotAllowedError(RegistrationError):
    pass


class RegistrationDecisionNotAllowedError(RegistrationError):
    pass


class StaleRegistrationDecisionError(RegistrationError):
    pass


def list_for_event(db: Session, event_id: uuid.UUID) -> list[EventRegistration]:
    """Read registrations without consulting or changing the intake state."""
    return repo.list_for_event(db, event_id)


def list_events_for_attendee(
    db: Session, attendee_id: uuid.UUID, now: datetime
) -> list[tuple[EventRequest, bool]]:
    """Open events plus confirmed events where this attendee has a lifecycle to manage."""
    events: list[tuple[EventRequest, bool]] = []
    for event in event_repo.list_confirmed(db):
        intake_open = _intake_open(event, now)
        if intake_open or repo.get_for_attendee(db, event.id, attendee_id) is not None:
            events.append((event, intake_open))
    return events


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
    registration_notifications.status_changed(
        db, event, registration, repo.latest_history(db, registration.id)
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


def withdraw(
    db: Session, event_id: uuid.UUID, attendee_id: uuid.UUID, now: datetime
) -> tuple[EventRegistration, bool]:
    """Withdraw the attendee's newest lifecycle, once, while its event remains active.

    Locking the event serialises this with submissions and other withdrawal attempts.
    The second return value says whether the lifecycle was already withdrawn.
    """
    event = event_repo.get_for_update(db, event_id)
    if event is None:
        raise EventNotFoundError
    if event.status is not EventStatus.CONFIRMED:
        raise WithdrawalNotAllowedError(
            "registration may be withdrawn only while the event is active"
        )
    registration = repo.get_for_attendee(db, event.id, attendee_id)
    if registration is None:
        raise RegistrationNotFoundError
    if registration.status is RegistrationStatus.WITHDRAWN:
        return registration, True
    if registration.status not in {
        RegistrationStatus.PENDING,
        RegistrationStatus.WAITLISTED,
        RegistrationStatus.ACCEPTED,
    }:
        raise WithdrawalNotAllowedError("registration cannot be withdrawn in its current status")
    repo.withdraw(db, registration, attendee_id, now)
    registration_notifications.status_changed(
        db, event, registration, repo.latest_history(db, registration.id)
    )
    db.commit()
    db.refresh(registration)
    return registration, False


def decide(
    db: Session,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
    actor_id: uuid.UUID,
    expected_status: RegistrationStatus,
    target: RegistrationStatus,
    note: str | None,
    now: datetime,
) -> tuple[EventRegistration, bool]:
    """Record one authorised outcome, or recognise its exact safe retry.

    The event lock is deliberately shared with attendee withdrawal and submission. Once it is
    held, the locked registration read sees any earlier lifecycle transition before deciding.
    """
    event = event_repo.get_for_update(db, event_id)
    if event is None:
        raise EventNotFoundError
    if event.status is not EventStatus.CONFIRMED:
        raise RegistrationDecisionNotAllowedError("registration decisions require an active event")
    registration = repo.get_for_update(db, registration_id, event.id)
    if registration is None:
        raise RegistrationNotFoundError
    if registration.status is not expected_status:
        if registration.status is target and repo.has_decision_action(
            db, registration.id, actor_id, expected_status, target, note
        ):
            return registration, True
        raise StaleRegistrationDecisionError("registration changed before this decision was saved")
    try:
        permitted_decision(registration.status, target)
    except RegistrationDecisionError as exc:
        raise RegistrationDecisionNotAllowedError(str(exc)) from exc
    repo.decide(db, registration, actor_id, target, now, note)
    registration_notifications.status_changed(
        db, event, registration, repo.latest_history(db, registration.id)
    )
    db.commit()
    db.refresh(registration)
    return registration, False


def _intake_open(event: EventRequest, now: datetime) -> bool:
    try:
        registration_intake.require_open_intake(event, now)
    except RegistrationIntakeError:
        return False
    return True
