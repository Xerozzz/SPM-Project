"""Venue Staff review and decide venue booking requests (SCRUM-40)."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from domain import venue_booking_decision as decision
from repositories import venue_availability as booking_repo
from repositories import venue_booking_decisions as repo
from repositories.venue_booking_decisions import BookingContext


class BookingRequestNotFoundError(Exception):
    pass


def list_requests(db: Session) -> list[BookingContext]:
    """AC1 and AC3: every request with its event, venue and any decision."""
    return repo.list_with_context(db)


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
