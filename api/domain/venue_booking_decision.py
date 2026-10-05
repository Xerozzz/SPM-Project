"""Venue Staff rejecting a venue booking request (SCRUM-40).

Only a pending request can be rejected. A decided request keeps its outcome, so a second
decision is refused rather than overwriting the first (AC5). This uses the same
`InvalidBookingTransitionError` as approve in `domain/venue_booking.py` (SCRUM-74), so
both decisions are refused the same way.
"""

from domain.venue_booking import BookingStatus, InvalidBookingTransitionError

# Longest rejection reason we store. Enough for a short explanation to the Coordinator.
MAX_REASON_LENGTH = 1000


def reject(current: BookingStatus) -> BookingStatus:
    """AC2: a pending request becomes rejected. AC5: anything else is refused."""
    if current is not BookingStatus.PENDING:
        raise InvalidBookingTransitionError(current, BookingStatus.REJECTED)
    return BookingStatus.REJECTED


def clean_reason(reason: str | None) -> str | None:
    """AC2: the reason is optional. Trim it, and treat a blank reason as no reason."""
    if reason is None:
        return None
    return reason.strip() or None
