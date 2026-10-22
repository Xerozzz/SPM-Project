"""SCRUM-109: what a booking row arranged directly in a test needs once it is cancelled.

Since migration 0030 a cancelled row must say who cancelled it, when and why
(`venue_bookings_cancelled_has_record`). Tests that build rows in a chosen status pass
these fields too, so their cancelled rows are the ones a real cancellation would leave.
"""

import uuid
from datetime import UTC, datetime

from domain.venue_booking import BookingStatus


def cancellation_record(status: BookingStatus, cancelled_by_id: uuid.UUID) -> dict[str, object]:
    """The three cancellation columns for a cancelled row, and nothing for any other."""
    if status is not BookingStatus.CANCELLED:
        return {}
    return {
        "cancelled_by_id": cancelled_by_id,
        "cancelled_at": datetime.now(UTC),
        "cancellation_reason": "Arrangement no longer needed",
    }
