"""Cancel an event and release its arrangements (SCRUM-115, ADR-0061).

The owning Organiser may ask for a cancellation. The current assigned Coordinator applies
or declines that request, or cancels on their own with a reason. Applying a cancellation
does all of this in one transaction under the event's lock, so either all of it lands or
none of it does (AC8):

- intake that was opened is closed through SCRUM-113's staged close, and every Pending,
  Waitlisted and Accepted registration becomes Cancelled through SCRUM-134's staged
  decision write, which keeps its history (AC6),
- every live venue request, active hold and Confirmed booking is cancelled through
  SCRUM-109's `stage_booking_cancellation` (AC4),
- every live equipment reservation is released, keeping its row (AC5),
- the status moves to Cancelled through the shared machine, with who, when and why (AC3),
- the staff notifications are staged (AC9).
"""

import uuid
from datetime import datetime

from core.database import Session
from domain import event_status
from domain.event_cancellation import (
    CancellationRefusal,
    RequestStatus,
    cancellation_refusal,
    text_problems,
)
from domain.registration import LIVE_STATUSES, RegistrationStatus
from domain.validation import FieldProblem
from domain.venue_booking import InvalidBookingTransitionError
from models.event_cancellation_request import EventCancellationRequest
from models.event_request import EventRequest
from repositories import equipment_reservations as reservation_repo
from repositories import event_cancellations as repo
from repositories import event_registrations as registration_repo
from repositories import event_requests as event_repo
from repositories import venue_availability as booking_repo
from services import lifecycle_notifications as lifecycle
from services import registration_intake
from services.venue_bookings import stage_booking_cancellation


class CancellationError(Exception):
    """Base class for every refusal this service raises."""


class NotCancellableError(CancellationError):
    """AC2: the event is already Cancelled, Completed, or not active."""

    def __init__(self, refusal: CancellationRefusal) -> None:
        super().__init__(f"the event cannot be cancelled: {refusal}")
        self.refusal = refusal


class InvalidCancellationError(CancellationError):
    """AC1, AC3: the reason or note is missing or too long."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid cancellation")
        self.problems = problems


class RequestAlreadyPendingError(CancellationError):
    """AC1: the Organiser already has a request waiting for the Coordinator."""


class RequestNotFoundError(CancellationError):
    """No pending request with this id for this event."""


class EventNotFoundError(CancellationError):
    """The event does not exist."""


def request_cancellation(
    db: Session, event_id: uuid.UUID, organiser_id: uuid.UUID, reason: str | None, now: datetime
) -> EventCancellationRequest:
    """AC1: the owning Organiser asks for an active event to be cancelled.

    The caller has already checked the actor (REQUEST_EVENT_CANCELLATION). Nothing about
    the event changes yet. The Coordinator is told in the same commit.
    """
    event = _locked(db, event_id)
    _ensure_cancellable(event)
    _check("reason", reason)
    assert reason is not None
    if repo.pending_for_event(db, event.id) is not None:
        raise RequestAlreadyPendingError
    request = repo.add(
        db,
        EventCancellationRequest(
            event_request_id=event.id,
            status=RequestStatus.PENDING,
            reason=reason.strip(),
            requested_by_id=organiser_id,
            requested_at=now,
        ),
    )
    lifecycle.cancellation_requested(db, event, request, now)
    db.commit()
    db.refresh(request)
    return request


def cancel(
    db: Session,
    event_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str | None,
    request_id: uuid.UUID | None,
    now: datetime,
) -> EventRequest:
    """AC1 to AC9. The caller has already checked the actor (CANCEL_EVENT).

    With a `request_id`, the Organiser's pending request is applied, and its reason is
    used unless the Coordinator gives their own. Without one, a request that is still
    pending is marked applied as well. The event row is locked first, so two
    cancellations queue and the second is told the event is already Cancelled, with
    nothing released or notified twice (AC8).
    """
    event = _locked(db, event_id)
    _ensure_cancellable(event)
    request: EventCancellationRequest | None
    if request_id is not None:
        applied = _pending(db, event.id, request_id)
        if reason is None or not reason.strip():
            reason = applied.reason
        request = applied
    else:
        # A request still waiting is answered by this cancellation too, so none is left
        # pending on a Cancelled event.
        request = repo.pending_for_event(db, event.id)
    _check("reason", reason)
    assert reason is not None
    reason = reason.strip()

    # AC6: intake that was ever opened gets its close marker, suspended intake too, so
    # the record says it ended. Never opened means there is nothing to close.
    if event.registration_opened_at is not None and event.registration_closed_at is None:
        registration_intake.close(event, now)
    _cancel_registrations(db, event, actor_id, now)
    _cancel_bookings(db, event, actor_id, reason, now)
    reservation_repo.release_for_event(db, event.id, actor_id, now)

    event.status = event_status.cancel(event.status)
    event.cancelled_by_id = actor_id
    event.cancelled_at = now
    event.cancellation_reason = reason
    if request is not None:
        request.status = RequestStatus.APPLIED
        request.decided_by_id = actor_id
        request.decided_at = now
    lifecycle.cancelled(db, event, now)
    db.commit()
    db.refresh(event)
    return event


def decline(
    db: Session,
    event_id: uuid.UUID,
    request_id: uuid.UUID,
    actor_id: uuid.UUID,
    note: str | None,
    now: datetime,
) -> EventCancellationRequest:
    """AC1: the Coordinator declines a pending request with a note. The event is not
    touched, and the Organiser is told in the same commit."""
    event = _locked(db, event_id)
    request = _pending(db, event.id, request_id)
    _check("note", note)
    assert note is not None
    request.status = RequestStatus.DECLINED
    request.decided_by_id = actor_id
    request.decided_at = now
    request.decision_note = note.strip()
    lifecycle.cancellation_declined(db, event, request, now)
    db.commit()
    db.refresh(request)
    return request


def requests_of(db: Session, event: EventRequest) -> list[EventCancellationRequest]:
    """AC1: every request for this event and its outcome, oldest first."""
    return repo.requests_for_event(db, event.id)


def _cancel_registrations(
    db: Session, event: EventRequest, actor_id: uuid.UUID, now: datetime
) -> None:
    """AC6: live registrations become Cancelled, each with its own history row.

    Withdrawn ones are left exactly as they are. Submission, withdrawal and decisions all
    lock the event first, so holding its lock here means none of them runs in between.
    """
    for registration in registration_repo.list_for_event(db, event.id):
        if registration.status in LIVE_STATUSES:
            registration_repo.decide(
                db, registration, actor_id, RegistrationStatus.CANCELLED, now, None
            )


def _cancel_bookings(
    db: Session, event: EventRequest, actor_id: uuid.UUID, reason: str, now: datetime
) -> None:
    """AC4: every live request, active hold and Confirmed booking becomes Cancelled.

    The bookings are locked after the event, the order SCRUM-109 uses, so the hold
    expiry sweep and a cancellation never wait on each other in reverse. A booking that is
    already Rejected, Expired or Cancelled is left as it is: SCRUM-109's own rule says
    which are live, so this list never drifts from it.
    """
    for booking in booking_repo.lock_bookings_for_event(db, event.id):
        try:
            stage_booking_cancellation(booking, actor_id, reason, now)
        except InvalidBookingTransitionError:
            continue


def _ensure_cancellable(event: EventRequest) -> None:
    refusal = cancellation_refusal(event.status)
    if refusal is not None:
        raise NotCancellableError(refusal)


def _check(field: str, text: str | None) -> None:
    problems = text_problems(field, text)
    if problems:
        raise InvalidCancellationError(problems)


def _pending(db: Session, event_id: uuid.UUID, request_id: uuid.UUID) -> EventCancellationRequest:
    request = repo.pending_for_event(db, event_id)
    if request is None or request.id != request_id:
        raise RequestNotFoundError
    return request


def _locked(db: Session, event_id: uuid.UUID) -> EventRequest:
    event = event_repo.get_for_update(db, event_id)
    if event is None:
        raise EventNotFoundError
    return event
