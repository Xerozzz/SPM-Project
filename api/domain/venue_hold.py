"""Tentative venue hold rules (SCRUM-83). Pure, no database.

A hold keeps a pending request's venue for its event while the Coordinator finalises
arrangements, but only until its expiry, so it can never hold a venue indefinitely
(Week 7 change 4). ADR-0029 records why a hold is placed on a pending request.
"""

from datetime import datetime

from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus, InvalidBookingTransitionError


def expiry_problems(
    expires_at: datetime, now: datetime, event_start: datetime
) -> list[FieldProblem]:
    """What is wrong with a hold's expiry, if anything. Empty means it is valid.

    The expiry must carry a time zone (AGENTS.md section 3) and lie in the future, or the
    hold would end as soon as it was placed. It may not be after the event starts: the
    hold is for finalising arrangements before the event, not for the event itself, which
    needs an approved booking.
    """
    if expires_at.tzinfo is None or expires_at.tzinfo.utcoffset(expires_at) is None:
        return [FieldProblem("expires_at", "must include a time zone")]
    if expires_at <= now:
        return [FieldProblem("expires_at", "must be in the future")]
    if expires_at > event_start:
        return [FieldProblem("expires_at", "must not be after the event starts")]
    return []


def confirm() -> BookingStatus:
    """SCRUM-110: removed. Venue Staff approval creates a tentative hold (AC4); no
    Pending or Tentative row may become Confirmed through staff approval. SCRUM-80 owns
    the later event-confirmation step. Kept as a refused transition so any leftover
    caller fails loudly instead of confirming."""
    raise InvalidBookingTransitionError(BookingStatus.TENTATIVE, BookingStatus.CONFIRMED)


def is_due(status: BookingStatus, expires_at: datetime | None, now: datetime) -> bool:
    """SCRUM-108 AC1: a tentative hold whose expiry has been reached. The repository's
    query for due holds selects exactly these rows."""
    return status is BookingStatus.TENTATIVE and expires_at is not None and expires_at <= now


def expire(status: BookingStatus, expires_at: datetime | None, now: datetime) -> BookingStatus:
    """SCRUM-108 AC1: a hold that reached its expiry becomes Expired. Anything else is
    refused, so a hold that was confirmed or is still running is never expired."""
    if not is_due(status, expires_at, now):
        raise InvalidBookingTransitionError(status, BookingStatus.EXPIRED)
    return BookingStatus.EXPIRED
