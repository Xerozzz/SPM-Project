"""Venue availability calendar rules (SCRUM-54, SCRUM-76). Pure, no database.

The calendar shows what is holding a venue across a date range: confirmed bookings,
pending requests and recorded unavailability blocks. Rejected and cancelled requests
no longer hold anything, so they are left out.
"""

from datetime import datetime, timedelta
from typing import Literal

from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus
from domain.venue_search import booking_blocks_availability

# Longest range one request may ask for, about three months. Keeps one response small.
MAX_RANGE = timedelta(days=93)

# AC1: the booking statuses that appear on the calendar.
SHOWN_BOOKING_STATUSES = frozenset({BookingStatus.CONFIRMED, BookingStatus.PENDING})

# The closed vocabularies of a calendar entry, the same Literals the API schema uses.
EntryKind = Literal["booking", "unavailability"]
EntryStatus = Literal["confirmed", "pending", "unavailable"]

# AC1: the label each shown booking status gets on the calendar.
BOOKING_LABELS: dict[BookingStatus, EntryStatus] = {
    BookingStatus.CONFIRMED: "confirmed",
    BookingStatus.PENDING: "pending",
}

# SCRUM-77: one entry opened in full can be any booking, rejected and cancelled included.
DetailsStatus = Literal["confirmed", "pending", "rejected", "cancelled", "unavailable"]
DETAILS_LABELS: dict[BookingStatus, DetailsStatus] = {
    BookingStatus.CONFIRMED: "confirmed",
    BookingStatus.PENDING: "pending",
    BookingStatus.REJECTED: "rejected",
    BookingStatus.CANCELLED: "cancelled",
}


def range_problems(start_at: datetime, end_at: datetime) -> list[FieldProblem]:
    """What is wrong with a requested calendar range, if anything.

    Unlike venue search, a range in the past is allowed: looking back at what held a
    venue is still useful.
    """
    problems = [
        FieldProblem(field, "must include a time zone")
        for field, value in (("start_at", start_at), ("end_at", end_at))
        if value.tzinfo is None
    ]
    if problems:
        return problems
    if end_at <= start_at:
        return [FieldProblem("end_at", "must be after the start")]
    if end_at - start_at > MAX_RANGE:
        return [FieldProblem("end_at", f"must be within {MAX_RANGE.days} days of the start")]
    return []


def entry_blocks(kind: EntryKind, status: EntryStatus) -> bool:
    """SCRUM-76: does this calendar entry make the venue unavailable?

    A closure always does. A booking does only if it is confirmed (AC1), never while
    pending (AC2). The booking status rule is venue search's booking_blocks_availability,
    so the two agree on which bookings block. Opening hours are not part of this:
    venue search also checks them, the availability check does not.
    """
    if kind == "unavailability":
        return True
    return booking_blocks_availability(BookingStatus(status))
