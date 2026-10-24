"""Database access for attendee registration records and their immutable history."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.registration import LIVE_STATUSES, RegistrationStatus
from models.event_registration import EventRegistration, EventRegistrationHistory


def get_live_for_attendee(
    db: Session, event_request_id: uuid.UUID, attendee_id: uuid.UUID
) -> EventRegistration | None:
    statement = select(EventRegistration).where(
        EventRegistration.event_request_id == event_request_id,
        EventRegistration.attendee_id == attendee_id,
        EventRegistration.status.in_(LIVE_STATUSES),
    )
    return db.scalars(statement).first()


def get_for_attendee(
    db: Session, event_request_id: uuid.UUID, attendee_id: uuid.UUID
) -> EventRegistration | None:
    statement = (
        select(EventRegistration)
        .where(
            EventRegistration.event_request_id == event_request_id,
            EventRegistration.attendee_id == attendee_id,
        )
        .order_by(EventRegistration.submission_order.desc())
    )
    return db.scalars(statement).first()


def get_for_update(
    db: Session, registration_id: uuid.UUID, event_request_id: uuid.UUID
) -> EventRegistration | None:
    """Lock one registration after its event lock has serialised its lifecycle changes."""
    statement = (
        select(EventRegistration)
        .where(
            EventRegistration.id == registration_id,
            EventRegistration.event_request_id == event_request_id,
        )
        .with_for_update()
    )
    return db.scalars(statement).first()


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventRegistration]:
    """Return every lifecycle in fair submission order, including withdrawn records."""
    statement = (
        select(EventRegistration)
        .where(EventRegistration.event_request_id == event_request_id)
        .order_by(EventRegistration.submitted_at.asc(), EventRegistration.submission_order.asc())
    )
    return list(db.scalars(statement))


def next_submission_order(db: Session, event_request_id: uuid.UUID) -> int:
    statement = select(func.coalesce(func.max(EventRegistration.submission_order), 0)).where(
        EventRegistration.event_request_id == event_request_id
    )
    return int(db.scalar(statement) or 0) + 1


def add_submission(
    db: Session,
    event_request_id: uuid.UUID,
    attendee_id: uuid.UUID,
    submitted_at: datetime,
    submission_order: int,
    full_name: str,
    age: int,
    phone_number: str,
    dietary_accessibility_notes: str | None,
) -> EventRegistration:
    registration = EventRegistration(
        event_request_id=event_request_id,
        attendee_id=attendee_id,
        status=RegistrationStatus.PENDING,
        submitted_at=submitted_at,
        submission_order=submission_order,
        full_name=full_name,
        age=age,
        phone_number=phone_number,
        dietary_accessibility_notes=dietary_accessibility_notes,
    )
    db.add(registration)
    db.flush()
    db.add(
        EventRegistrationHistory(
            registration_id=registration.id,
            actor_id=attendee_id,
            previous_status=None,
            status=RegistrationStatus.PENDING,
            occurred_at=submitted_at,
        )
    )
    return registration


def withdraw(
    db: Session, registration: EventRegistration, actor_id: uuid.UUID, occurred_at: datetime
) -> EventRegistration:
    """Append the attendee's withdrawal source action and stage its new current state."""
    previous_status = registration.status
    registration.status = RegistrationStatus.WITHDRAWN
    db.add(
        EventRegistrationHistory(
            registration_id=registration.id,
            actor_id=actor_id,
            previous_status=previous_status,
            status=RegistrationStatus.WITHDRAWN,
            occurred_at=occurred_at,
        )
    )
    return registration


def decide(
    db: Session,
    registration: EventRegistration,
    actor_id: uuid.UUID,
    target: RegistrationStatus,
    occurred_at: datetime,
    note: str | None,
) -> EventRegistration:
    """Stage one manual status outcome and its immutable source action together."""
    previous_status = registration.status
    registration.status = target
    db.add(
        EventRegistrationHistory(
            registration_id=registration.id,
            actor_id=actor_id,
            previous_status=previous_status,
            status=target,
            occurred_at=occurred_at,
            note=note,
        )
    )
    return registration


def has_decision_action(
    db: Session,
    registration_id: uuid.UUID,
    actor_id: uuid.UUID,
    previous_status: RegistrationStatus,
    status: RegistrationStatus,
    note: str | None,
) -> bool:
    """Identify an exact committed retry without treating another decision as one."""
    statement = (
        select(EventRegistrationHistory)
        .where(EventRegistrationHistory.registration_id == registration_id)
        .order_by(EventRegistrationHistory.occurred_at.desc(), EventRegistrationHistory.id.desc())
        .limit(1)
    )
    latest = db.scalars(statement).first()
    return latest is not None and (
        latest.actor_id,
        latest.previous_status,
        latest.status,
        latest.note,
    ) == (actor_id, previous_status, status, note)


def list_history(db: Session, registration_id: uuid.UUID) -> list[EventRegistrationHistory]:
    statement = (
        select(EventRegistrationHistory)
        .where(EventRegistrationHistory.registration_id == registration_id)
        .order_by(EventRegistrationHistory.occurred_at.asc(), EventRegistrationHistory.id.asc())
    )
    return list(db.scalars(statement))
