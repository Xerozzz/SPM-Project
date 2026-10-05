"""Venue Staff review and decide venue booking requests (SCRUM-40, SCRUM-75).

Approving is `services.venue_bookings.approve` (SCRUM-74). This module lists requests
and rejects them, and shows what would block approving each pending one."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from domain import venue_booking_decision as decision
from domain.booking_conflict import BookingConflictError
from domain.venue_booking import BookingStatus
from models.venue_booking import VenueBooking
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
    """AC2: reject a pending request and record who, when and why (AC3)."""
    booking = booking_repo.get_booking_for_update(db, booking_id)
    if booking is None:
        raise BookingRequestNotFoundError
    booking.status = decision.reject(booking.status)
    booking.decided_by_id = decider_id
    booking.decided_at = now
    booking.decision_reason = decision.clean_reason(reason)
    booking_repo.save_booking(db, booking)
    context = repo.get_with_context(db, booking_id)
    assert context is not None
    return context


def _conflict(db: Session, booking: VenueBooking) -> BookingConflictError | None:
    """What would block approving `booking`, if anything. Decided requests have none."""
    if booking.status is not BookingStatus.PENDING:
        return None
    try:
        venue_bookings.check_approvable(db, booking.id)
    except BookingConflictError as exc:
        return exc
    return None
