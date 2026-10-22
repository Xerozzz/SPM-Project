"""Tentative venue hold rules (SCRUM-83). Pure, no database.

A hold keeps a pending request's venue for its event while the Coordinator finalises
arrangements, but only until its expiry, so it can never hold a venue indefinitely
(Week 7 change 4). ADR-0029 records why a hold is placed on a pending request.
"""

from datetime import datetime

from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus, InvalidBookingTransitionError


class InactiveHoldError(Exception):
    """The booking is not an active Tentative hold at the action instant."""


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


def ensure_active(status: BookingStatus, expires_at: datetime | None, now: datetime) -> None:
    """SCRUM-121: expiry may change only while a Tentative hold is still active.

    Comparing the stored expiry with the same supplied action time used to validate the
    replacement prevents an update from reviving a hold at its exact deadline.
    """
    if status is not BookingStatus.TENTATIVE:
        raise InactiveHoldError(f"cannot update a venue hold in {status} status")
    if expires_at is None or expires_at <= now:
        raise InactiveHoldError("cannot update a venue hold whose expiry has been reached")


def confirm(status: BookingStatus, expires_at: datetime | None, now: datetime) -> BookingStatus:
    """SCRUM-80 AC4: a live hold becomes a real booking when its event is confirmed.

    This is the step SCRUM-110 reserved for this story. Venue Staff approval still only
    ever places a hold (AC9: it is not asked a second time), and nothing else may move a
    row to Confirmed — so the only route from Tentative to Confirmed is the Coordinator
    confirming the whole event, with every prerequisite checked first.

    AC8: a hold that reaches its expiry at this very instant is expired, which is the
    comparison `is_due` already makes, so the two cannot disagree about the boundary.
    """
    if status is not BookingStatus.TENTATIVE:
        raise InvalidBookingTransitionError(status, BookingStatus.CONFIRMED)
    # A hold with no expiry is malformed rather than eternal, which is how
    # `ensure_updatable` above already reads one. The database agrees: migration 0021's
    # `venue_bookings_tentative_has_hold` refuses to store such a row.
    if expires_at is None or is_due(status, expires_at, now):
        raise InactiveHoldError("cannot confirm a venue hold whose expiry has been reached")
    return BookingStatus.CONFIRMED


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
