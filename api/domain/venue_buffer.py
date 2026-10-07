"""The effective occupied interval of a venue booking (SCRUM-82). Pure, no database.

A venue needs preparing before an event and resetting afterwards, so the time it is
really occupied is wider than the event itself. The worked example from the customer: an
event from 10:00 to 12:00 at a venue with 30 minutes setup and 45 minutes turnaround
occupies the venue from 09:30 to 12:45 (AC3).

Every rule that asks "is this venue free?" works on effective intervals rather than event
times (AC4), so this module is the one place the widening happens. The half-open overlap
rule is still `domain.venue_search.intervals_overlap`, reused rather than restated, so
back-to-back effective intervals do not clash (AC6, as in SCRUM-73 and SCRUM-76).

Two different comparisons exist and the difference matters:

* **booking against booking.** Both sides are widened, because both need their own setup
  and reset. They share a venue, so they share its buffers.
* **booking against a recorded closure.** Only the booking is widened. A closure is a
  real closure, and the point of the rule is that preparation may not run into one (AC5).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from domain.venue_search import intervals_overlap


@dataclass(frozen=True)
class VenueBuffers:
    """What a venue needs around a booking, in whole minutes. See domain/venue.py."""

    setup_minutes: int = 0
    turnaround_minutes: int = 0

    @property
    def combined(self) -> timedelta:
        """The gap two bookings at this venue need between them. See `bookings_clash`."""
        return timedelta(minutes=self.setup_minutes + self.turnaround_minutes)


# A venue with no buffers, which is every venue until Venue Staff set one (AC7).
NO_BUFFERS = VenueBuffers()


def effective_interval(
    start_at: datetime, end_at: datetime, buffers: VenueBuffers
) -> tuple[datetime, datetime]:
    """AC3: the period the venue is really occupied by an event over [start_at, end_at).

    With no buffers this returns the event's own times unchanged, which is what makes AC7
    hold without a special case anywhere else.
    """
    return (
        start_at - timedelta(minutes=buffers.setup_minutes),
        end_at + timedelta(minutes=buffers.turnaround_minutes),
    )


def bookings_clash(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
    buffers: VenueBuffers,
) -> bool:
    """AC6: do two bookings at the same venue occupy overlapping effective intervals?

    Both sides are widened. Written the obvious way rather than the clever way: widening
    both is algebraically the same as requiring `buffers.combined` of clear time between
    the raw intervals, and `test_widening_both_sides_equals_one_combined_gap` proves the
    two agree, but the obvious form is the one that stays right if the rule changes.
    """
    first = effective_interval(first_start, first_end, buffers)
    second = effective_interval(second_start, second_end, buffers)
    return intervals_overlap(*first, *second)


def booking_clashes_with_closure(
    start_at: datetime,
    end_at: datetime,
    closure_start: datetime,
    closure_end: datetime,
    buffers: VenueBuffers,
) -> bool:
    """AC5: does a booking's effective interval run into a recorded closure?

    The closure is not widened: it is already the whole period the venue is unusable.
    """
    effective = effective_interval(start_at, end_at, buffers)
    return intervals_overlap(*effective, closure_start, closure_end)
