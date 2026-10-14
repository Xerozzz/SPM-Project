"""Tentative venue hold rules (SCRUM-83). Pure, no database.

A hold keeps a pending request's venue for its event while the Coordinator finalises
arrangements, but only until its expiry, so it can never hold a venue indefinitely
(Week 7 change 4). ADR-0029 records why a hold is placed on a pending request.
"""

from datetime import datetime

from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus, InvalidBookingTransitionError


class HoldExpiredError(InvalidBookingTransitionError):
    """SCRUM-107 AC2: the hold ran out before it was approved, so it cannot be confirmed.
    A transition error like any other refused decision, so it is answered with 409."""

    def __init__(self, expires_at: datetime | None) -> None:
        super().__init__(BookingStatus.TENTATIVE, BookingStatus.CONFIRMED)
        self.args = (f"the tentative hold expired at {expires_at}",)
        self.expires_at = expires_at


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


def confirm(current: BookingStatus, expires_at: datetime | None, now: datetime) -> BookingStatus:
    """SCRUM-107 AC1: approving a tentative hold before it expires confirms it. The rest of
    the approval (row lock, conflict check, overlap constraint) is the normal one in
    services.venue_bookings.approve.

    Only a tentative hold goes through here. A pending request still uses
    domain.venue_booking.approve, so the SCRUM-74 rule for requests is unchanged.
    """
    if current is not BookingStatus.TENTATIVE:
        raise InvalidBookingTransitionError(current, BookingStatus.CONFIRMED)
    if expires_at is None or expires_at <= now:
        raise HoldExpiredError(expires_at)
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
