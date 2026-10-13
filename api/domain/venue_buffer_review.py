"""Which bookings a venue's buffers have made problematic (SCRUM-89). Pure, no database.

Changing a venue's setup or turnaround time changes how much of the venue every booking
there occupies, so two bookings that were compatible can stop being compatible without
either of them changing. SCRUM-82 made every live rule read the venue's current buffers,
so the new reading takes effect at once; this module is how Venue Staff are told which
existing bookings it caught out.

The rule is not restated here. Each booking is put through
`domain.booking_conflict.ensure_no_conflict` against the others, which is the same check
booking approval runs, so a booking reported here is exactly a booking that could not be
approved today. Reusing it also means the answer carries *what* it clashes with, because
that check raises an error naming the booking or closure in the way.

Both sides of a clashing pair are reported. If A and B now overlap, both need attention
and either could be the one that moves, so naming only the later one would be a guess.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from domain.booking_conflict import (
    BookedPeriod,
    ConflictingBookingError,
    UnavailablePeriod,
    VenueUnavailableError,
    ensure_no_conflict,
)
from domain.venue_buffer import VenueBuffers


@dataclass(frozen=True)
class ProblematicBooking:
    """One booking that cannot stand under the venue's buffers, and what is in its way."""

    booking: BookedPeriod
    # The two the check can actually raise, rather than their base class. Narrow on
    # purpose: callers turn this into a response and should not have to widen it back,
    # and a third kind appearing here would be a type error rather than a surprise at
    # runtime. `ConcurrentBookingConflictError` is not one of them: that comes from the
    # database constraint on commit, never from this read-only comparison.
    conflict: ConflictingBookingError | VenueUnavailableError


def problematic_bookings(
    bookings: Iterable[BookedPeriod],
    closures: Iterable[UnavailablePeriod],
    buffers: VenueBuffers,
) -> list[ProblematicBooking]:
    """AC1 and AC2: every booking whose effective interval now clashes, in the given order.

    `bookings` is every booking at one venue that the caller wants assessed, and
    `closures` every recorded unavailability there. Caller-ordered rather than sorted
    here, so the caller decides what "first" means and this stays a pure comparison.

    AC7 falls out of this being a question rather than a record: reducing a buffer simply
    produces a shorter list next time it is asked, and there is no stored marker to clear.
    """
    all_bookings = list(bookings)
    all_closures = list(closures)
    found: list[ProblematicBooking] = []

    for booking in all_bookings:
        others = [other for other in all_bookings if other.id != booking.id]
        try:
            ensure_no_conflict(booking.start_at, booking.end_at, others, all_closures, buffers)
        except (ConflictingBookingError, VenueUnavailableError) as conflict:
            found.append(ProblematicBooking(booking, conflict))

    return found
