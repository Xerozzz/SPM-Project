"""Rules for starting a replacement venue request (SCRUM-116). Pure, no database.

When a closure or buffer change leaves a live booking or hold needing attention
(SCRUM-81, SCRUM-89), the assigned Coordinator can ask for another venue for the same
session. The replacement is an ordinary Pending venue request (SCRUM-78) that also names
the arrangement it would replace, so the two stay linked (AC1, AC2, AC3).

Adopting the replacement and retiring the original is SCRUM-133. Its one rule, which
replacement may be adopted, is at the end of this module (ADR-0057).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus

# Only an arrangement the venue is actually committed to can need replacing. A pending
# request can simply be withdrawn or left, and a rejected or expired one holds nothing.
REPLACEABLE_STATUSES = frozenset({BookingStatus.CONFIRMED, BookingStatus.TENTATIVE})

# A replacement still in progress. Rejected and expired ones are history, so another can
# be requested after them (AC6).
LIVE_REPLACEMENT_STATUSES = frozenset(
    {BookingStatus.PENDING, BookingStatus.TENTATIVE, BookingStatus.CONFIRMED}
)


@dataclass(frozen=True)
class Original:
    """The arrangement being replaced, as the rules need it."""

    event_request_id: object
    status: BookingStatus
    session_label: str
    start_at: datetime
    end_at: datetime
    needs_attention: bool
    has_live_replacement: bool


def replacement_problems(
    original: Original | None,
    event_request_id: object,
    session_label: str,
    start_at: datetime,
    end_at: datetime,
) -> list[FieldProblem]:
    """AC1, AC2, AC6: why this request cannot be a replacement, or nothing if it can."""
    field = "replaces_booking_id"
    if original is None or original.event_request_id != event_request_id:
        return [FieldProblem(field, "is not a venue request of this event")]
    if original.status not in REPLACEABLE_STATUSES:
        return [FieldProblem(field, "is not a confirmed booking or a live hold")]
    if not original.needs_attention:
        return [FieldProblem(field, "does not need a replacement")]
    if original.has_live_replacement:
        return [FieldProblem(field, "already has a replacement in progress")]
    # AC1: the replacement is for the same session and period, carried over unchanged.
    problems: list[FieldProblem] = []
    if session_label.strip() != original.session_label:
        problems.append(FieldProblem("session_label", "must match the arrangement replaced"))
    if start_at != original.start_at:
        problems.append(FieldProblem("start_at", "must match the arrangement replaced"))
    if end_at != original.end_at:
        problems.append(FieldProblem("end_at", "must match the arrangement replaced"))
    return problems


class AdoptionRefusal(StrEnum):
    """SCRUM-133 AC2: why this request cannot be adopted."""

    #: It does not replace anything, so there is nothing to retire.
    NOT_A_REPLACEMENT = "not_a_replacement"
    #: Venue Staff have not approved it (SCRUM-110), or its hold has run out.
    NOT_APPROVED = "not_approved"


def adoption_refusal(
    replaces_booking_id: object, status: BookingStatus, expires_at: datetime | None, now: datetime
) -> AdoptionRefusal | None:
    """SCRUM-133 AC2: None when this replacement may be adopted, otherwise why not.

    Approval through SCRUM-110 places a hold, so an active hold or a confirmed booking
    counts. A hold at or past its expiry does not, even before the timer marks it Expired,
    the same "active" rule cancelling uses.
    """
    if replaces_booking_id is None:
        return AdoptionRefusal.NOT_A_REPLACEMENT
    if status is BookingStatus.CONFIRMED:
        return None
    if status is BookingStatus.TENTATIVE and expires_at is not None and expires_at > now:
        return None
    return AdoptionRefusal.NOT_APPROVED
