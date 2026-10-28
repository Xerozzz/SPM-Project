"""Venue Staff review and decide venue booking requests (SCRUM-40, SCRUM-75).

Approving is `services.venue_bookings.approve` (SCRUM-74). This module lists requests
and rejects them, and shows what would block approving each pending one."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from domain import venue_booking_decision as decision
from domain.booking_conflict import BookingConflictError
from domain.notifications import NotificationSource, NotificationType
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.venue_booking import VenueBooking
from repositories import event_requests as event_repo
from repositories import notifications as notifications_repo
from repositories import venue_availability as booking_repo
from repositories import venue_booking_decisions as repo
from repositories.venue_booking_decisions import BookingContext
from services import venue_bookings

# A booking request with its event and venue, and what would block approving it.
ReviewItem = tuple[BookingContext, BookingConflictError | None]


class BookingRequestNotFoundError(Exception):
    pass


def list_requests(db: Session) -> list[ReviewItem]:
    """SCRUM-40 AC1 and AC3: every request with its event, venue and any decision.
    SCRUM-75 AC1: a pending request also carries what the SCRUM-73 check reports."""
    return [(row, _conflict(db, row[0])) for row in repo.list_with_context(db)]


def reject(
    db: Session, booking_id: uuid.UUID, decider_id: uuid.UUID, reason: str | None, now: datetime
) -> BookingContext:
    """AC2: reject a pending request and record who, when and why (AC3).

    SCRUM-122 AC1/AC2: the current Coordinator hears of the rejection. Staged before
    the commit so the rejection and its notification land or roll back together; the
    occurrence time is the decision time, not a second clock read. The source_id
    carries the decision time because a booking id alone cannot tell a retry of one
    rejection from a later distinct decision on the same row.
    """
    booking = booking_repo.get_booking_for_update(db, booking_id)
    if booking is None:
        raise BookingRequestNotFoundError
    # SCRUM-122: read the event before mutating, so no later read autoflushes the
    # pending UPDATE outside the save below.
    event = event_repo.get(db, booking.event_request_id)
    assert event is not None
    booking.status = decision.reject(booking.status)
    booking.decided_by_id = decider_id
    booking.decided_at = now
    booking.decision_reason = decision.clean_reason(reason)
    _stage_venue_rejection(db, event, booking, now)
    booking_repo.save_booking(db, booking)
    context = repo.get_with_context(db, booking_id)
    assert context is not None
    return context


def get(db: Session, booking_id: uuid.UUID) -> BookingContext:
    """One request with its event and venue, for answering after a hold (SCRUM-83)."""
    context = repo.get_with_context(db, booking_id)
    if context is None:
        raise BookingRequestNotFoundError
    return context


def _conflict(db: Session, booking: VenueBooking) -> BookingConflictError | None:
    """What would block approving `booking`, if anything. Decided requests have none.
    SCRUM-107: a tentative hold can be approved too, so it is checked as well."""
    if booking.status not in (BookingStatus.PENDING, BookingStatus.TENTATIVE):
        return None
    try:
        venue_bookings.check_approvable(db, booking.id)
    except BookingConflictError as exc:
        return exc
    return None


def _stage_venue_rejection(
    db: Session, event: EventRequest, booking: VenueBooking, now: datetime
) -> None:
    """SCRUM-122 AC1/AC2: notify the current Coordinator of a rejection.

    No commit here: the caller's save commits the rejection and this row together,
    so a rolled-back rejection notifies nobody. With no Coordinator assigned nothing
    is staged and the rejection still commits. The insert runs without autoflush so
    the pending UPDATE is only flushed by the save below.
    """
    if event.coordinator_id is None:
        return
    with db.no_autoflush:
        notifications_repo.stage(
            db,
            recipient_id=event.coordinator_id,
            event_request_id=event.id,
            type=NotificationType.VENUE_BOOKING_REJECTED,
            source_type=NotificationSource.VENUE_DECISION,
            source_id=f"{booking.id}:{now.isoformat()}",
            occurred_at=now,
        )
