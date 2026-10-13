"""Re-assess a venue's bookings after its buffers change (SCRUM-89).

Two jobs, and the difference between them is the whole design of this story.

`review` answers a question: which bookings at this venue cannot stand under the buffers
it has *now*. It stores nothing, so there is no marker to clear when a buffer is reduced
or a clashing booking is cancelled (AC3, AC7), and the answer is correct the moment it is
asked. Every read surface calls this.

`record_change` writes the one thing that is stored: a note that someone changed the
buffers, what they changed them from and to, and which bookings that caught out at the
time (AC8). That row never changes afterwards, which is what makes it an audit record
rather than a second, staler copy of the review.

Nothing here writes to a booking. A buffer change leaves every booking, hold and event
exactly as it was (AC5), which is why it can never be refused.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from domain.booking_conflict import BookedPeriod, UnavailablePeriod
from domain.venue_buffer import VenueBuffers
from domain.venue_buffer_review import ProblematicBooking, problematic_bookings
from models.venue import Venue
from models.venue_buffer_change import VenueBufferChange
from repositories import venue_availability as booking_repo
from repositories import venue_unavailabilities as closure_repo


@dataclass(frozen=True)
class BufferChangeResult:
    """What a saved buffer change did, for telling Venue Staff (AC6)."""

    changed: bool
    problems: list[ProblematicBooking]

    @property
    def flagged_booking_ids(self) -> list[uuid.UUID]:
        return [problem.booking.id for problem in self.problems]


def buffers_of(venue: Venue) -> VenueBuffers:
    """A venue's current buffers, as the pure rules take them."""
    return VenueBuffers(
        setup_minutes=venue.setup_minutes, turnaround_minutes=venue.turnaround_minutes
    )


def review(db: Session, venue: Venue, now: datetime) -> list[ProblematicBooking]:
    """AC1 and AC2: the venue's future confirmed bookings that now clash, in start order.

    One query for the bookings and one for the closures, then the comparison happens in
    the domain. Deliberately not a query per booking: every booking at a venue has to be
    compared with every other, so loading them once is both fewer round trips and the
    only way the pure rule can see the whole picture.
    """
    bookings = booking_repo.confirmed_bookings_from(db, venue.id, now)
    closures = closure_repo.list_for_venue(db, venue.id)
    return problematic_bookings(
        [
            BookedPeriod(id=row.id, status=row.status, start_at=row.start_at, end_at=row.end_at)
            for row in bookings
        ],
        [
            UnavailablePeriod(id=row.id, starts_at=row.starts_at, ends_at=row.ends_at)
            for row in closures
        ],
        buffers_of(venue),
    )


def record_change(
    db: Session,
    venue: Venue,
    previous: VenueBuffers,
    changed_by_id: uuid.UUID,
    now: datetime,
) -> BufferChangeResult:
    """AC8: note who changed the buffers, from what, to what, and what it caught out.

    Added to the session without committing, so the caller's own commit saves the venue
    and this record together. A change that is rolled back must not leave an audit row
    saying it happened.

    `previous` is read before the change is applied; when it matches the venue's current
    buffers nothing is recorded, because re-saving a venue without touching its buffers
    is not a buffer change.
    """
    if previous == buffers_of(venue):
        return BufferChangeResult(changed=False, problems=[])

    problems = review(db, venue, now)
    db.add(
        VenueBufferChange(
            venue_id=venue.id,
            changed_by_id=changed_by_id,
            changed_at=now,
            old_setup_minutes=previous.setup_minutes,
            old_turnaround_minutes=previous.turnaround_minutes,
            new_setup_minutes=venue.setup_minutes,
            new_turnaround_minutes=venue.turnaround_minutes,
            flagged_booking_ids=[problem.booking.id for problem in problems],
        )
    )
    return BufferChangeResult(changed=True, problems=problems)
