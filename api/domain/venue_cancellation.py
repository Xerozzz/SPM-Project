"""Cancelling one venue arrangement of an event (SCRUM-109). Pure, no database.

The assigned Coordinator may cancel one pending request, active tentative hold or
confirmed booking while the event is being planned, without touching its other
arrangements (ADR-0056). The transition sits here with the event and reason rules it
is always checked with, in the style of `approve`, `hold` and `expire`.
"""

from datetime import datetime
from enum import StrEnum

from domain.event_status import EventStatus
from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus, InvalidBookingTransitionError


class EventRefusal(StrEnum):
    """Why an event's status does not allow cancelling one of its arrangements."""

    # AC9: a confirmed event changes venue through the controlled flow (SCRUM-118).
    CONFIRMED_NEEDS_VENUE_CHANGE = "confirmed_needs_venue_change"
    # AC7: anything that is not planning, including statuses added later.
    NOT_IN_PLANNING = "not_in_planning"
    # SCRUM-118: a venue change is only for a Confirmed event; in planning, cancel instead.
    NOT_CONFIRMED = "not_confirmed"


def event_refusal(status: EventStatus, venue_change: bool = False) -> EventRefusal | None:
    """None when an event in `status` allows a cancellation; otherwise why it does not.

    Only Approved — the planning phase (see ACTIVE_STATUSES) — allows it. Allowing one
    status rather than forbidding a list means a status added later, such as Cancelled
    or Completed, is refused without anyone having to remember this rule (AC7).

    SCRUM-118: a cancellation the Coordinator has confirmed as a venue change is the
    reverse: only a Confirmed event allows it, because the change is what sends the event
    back to planning (ADR-0066). The same one-status rule refuses everything else.
    """
    if venue_change:
        return None if status is EventStatus.CONFIRMED else EventRefusal.NOT_CONFIRMED
    if status is EventStatus.APPROVED:
        return None
    if status is EventStatus.CONFIRMED:
        return EventRefusal.CONFIRMED_NEEDS_VENUE_CHANGE
    return EventRefusal.NOT_IN_PLANNING


def reason_problems(reason: str | None) -> list[FieldProblem]:
    """AC4: a reason is required, and blank or whitespace-only does not count."""
    if reason is None or not reason.strip():
        return [FieldProblem("reason", "is required")]
    return []


def venue_change_problems(confirmed: bool, reason: str | None) -> list[FieldProblem]:
    """SCRUM-118 AC1: a venue change needs the Coordinator's explicit confirmation that
    it sends the event back to planning, and a reason, as any cancellation does."""
    problems = [] if confirmed else [FieldProblem("confirm_venue_change", "must be confirmed")]
    return problems + reason_problems(reason)


def cancel(status: BookingStatus, expires_at: datetime | None, now: datetime) -> BookingStatus:
    """AC1, AC5, AC10: Pending, Confirmed and an active Tentative hold become Cancelled.

    Cancelled, Rejected and Expired are refused. So is a Tentative hold whose expiry has
    been reached but which the minute timer has not marked Expired yet: at its deadline a
    hold has expired, so it is never both expired and cancelled. "Active" is
    `domain.venue_hold.ensure_active`'s rule — an expiry that exists and is after `now` —
    so cancelling and updating a hold agree on which holds are live.
    """
    if status in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
        return BookingStatus.CANCELLED
    active_hold = status is BookingStatus.TENTATIVE and expires_at is not None and expires_at > now
    if active_hold:
        return BookingStatus.CANCELLED
    raise InvalidBookingTransitionError(status, BookingStatus.CANCELLED)
