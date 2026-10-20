"""Rules for starting a replacement venue request (SCRUM-116). Pure, no database.

When a closure or buffer change leaves a live booking or hold needing attention
(SCRUM-81, SCRUM-89), the assigned Coordinator can ask for another venue for the same
session. The replacement is an ordinary Pending venue request (SCRUM-78) that also names
the arrangement it would replace, so the two stay linked (AC1, AC2, AC3).

Adopting the replacement and retiring the original is SCRUM-133, not this module.
"""

from dataclasses import dataclass
from datetime import datetime

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
