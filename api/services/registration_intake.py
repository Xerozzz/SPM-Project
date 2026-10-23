"""SCRUM-113 registration intake operations, kept reusable for downstream callers."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.registration_intake import (
    RegistrationIntakeError,
    Settings,
    intake_is_open,
    is_enabled,
    validate_extension,
    validate_open,
)
from models.event_request import EventRequest
from repositories import event_requests as event_repo
from services import event_confirmations


class RegistrationReadinessError(RegistrationIntakeError):
    """The confirmed event's arrangements or safety approval no longer stand."""


def settings_of(event: EventRequest) -> Settings:
    return Settings(
        event.registration_opened_at, event.registration_closes_at, event.registration_suspended_at
    )


def open_intake(
    db: Session, event_id: uuid.UUID, closes_at: datetime | None, now: datetime
) -> EventRequest:
    """Open intake after rechecking the live confirmation prerequisites under a lock."""
    event = _locked(db, event_id)
    if not is_enabled(event.registration_requirement):
        raise RegistrationIntakeError("registration is not enabled for this event")
    if event.status is not EventStatus.CONFIRMED:
        raise RegistrationIntakeError("registration may be opened only for a confirmed event")
    validate_open(closes_at, now)
    if event_confirmations.current_plan_readiness(db, event, now).blocked:
        raise RegistrationReadinessError("current arrangements or safety approval are not valid")
    event.registration_opened_at = now
    event.registration_closes_at = closes_at
    event.registration_suspended_at = None
    return event_repo.save(db, event)


def extend_intake(
    db: Session, event_id: uuid.UUID, closes_at: datetime, now: datetime
) -> EventRequest:
    """Move a configured deadline forward, with no partial change on any refusal."""
    event = _locked(db, event_id)
    if event.status is not EventStatus.CONFIRMED:
        raise RegistrationIntakeError("registration may be extended only for a confirmed event")
    current = settings_of(event)
    validate_extension(current, closes_at, now)
    if not intake_is_open(event.status, current, now):
        raise RegistrationIntakeError("registration intake is not open")
    event.registration_closes_at = closes_at
    return event_repo.save(db, event)


def suspend_intake(db: Session, event_id: uuid.UUID, now: datetime) -> EventRequest:
    """Suspend intake for replanning; reconfirmation never clears this marker."""
    event = _locked(db, event_id)
    event.registration_suspended_at = now
    return event_repo.save(db, event)


def require_open_intake(event: EventRequest, now: datetime) -> None:
    """Reusable backend boundary for future attendee-submission callers."""
    if not intake_is_open(event.status, settings_of(event), now):
        raise RegistrationIntakeError("registration intake is closed")


def _locked(db: Session, event_id: uuid.UUID) -> EventRequest:
    event = event_repo.get_for_update(db, event_id)
    if event is None:
        raise RegistrationIntakeError("event request not found")
    return event
