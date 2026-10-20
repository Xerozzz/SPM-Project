"""Which live arrangements a venue closure affects (SCRUM-81). Pure, no database.

A closure is recorded even when it lands on a confirmed booking or an unexpired hold
(AC1): the venue really is shut, and refusing to record it would hide the problem rather
than solve it. What this module answers is which of those arrangements the closure hits,
using the same buffered comparison booking approval uses (SCRUM-82 AC5): the booking is
widened by the venue's setup and turnaround, the closure is not.

The answer is a question, not a stored marker. The existing problem displays (SCRUM-89)
already ask it on every read, so a closure that is moved or removed changes what they
show with nothing to clear (AC6).
"""

import uuid
from collections.abc import Iterable
from datetime import datetime

from domain.booking_conflict import BookedPeriod
from domain.venue_buffer import VenueBuffers, booking_clashes_with_closure

# Fixed namespace for impact notification keys. Changing it would make every retry of an
# old save look like a new action, so it is a constant, not a setting.
_IMPACT_NAMESPACE = uuid.UUID("6f1d3a4e-81c0-4b7e-9a51-0c2b1f8d8181")


def affected_by_closure(
    bookings: Iterable[BookedPeriod],
    closure_start: datetime,
    closure_end: datetime,
    buffers: VenueBuffers,
) -> list[BookedPeriod]:
    """AC2: the live bookings and holds this closure runs into, in the given order."""
    return [
        booking
        for booking in bookings
        if booking_clashes_with_closure(
            booking.start_at, booking.end_at, closure_start, closure_end, buffers
        )
    ]


def impact_key(
    closure_id: uuid.UUID,
    closure_start: datetime,
    closure_end: datetime,
    booking_id: uuid.UUID,
) -> str:
    """AC4 and AC8: one stable key per closure period and affected arrangement.

    Saving the same closure again with the same period gives the same key, so a retry
    does not notify twice. Moving the closure gives a new key, because the Coordinator
    needs to hear about the new period (AC6).
    """
    name = f"{closure_id}|{closure_start.isoformat()}|{closure_end.isoformat()}|{booking_id}"
    return str(uuid.uuid5(_IMPACT_NAMESPACE, name))
