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
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from domain.booking_conflict import BookedPeriod, UnavailablePeriod
from domain.venue_buffer import VenueBuffers
from domain.venue_buffer_review import ProblematicBooking, problematic_bookings
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_buffer_change import VenueBufferChange
from repositories import venue_availability as booking_repo
from repositories import venue_unavailabilities as closure_repo
from repositories import venues as venue_repo


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


@dataclass(frozen=True)
class VenueProblems:
    """One venue and the bookings there that cannot stand under its current buffers."""

    venue: Venue
    problems: list[ProblematicBooking]


def review_every_venue(db: Session, now: datetime) -> list[VenueProblems]:
    """AC4: every venue with something needing attention, by venue name.

    Venues with nothing to report are left out, so an empty list means nothing anywhere
    needs attention rather than "no venues exist".

    Deactivated venues are included. A venue taken out of the catalogue under ADR-0012
    keeps the bookings already made for it, and those are exactly the ones nobody is
    watching, so dropping them here would hide the problems most likely to be missed.
    """
    reviewed = [VenueProblems(venue, review(db, venue, now)) for venue in venue_repo.list_all(db)]
    return [entry for entry in reviewed if entry.problems]


def problems_by_booking(
    db: Session, bookings: Iterable[VenueBooking], now: datetime
) -> dict[uuid.UUID, ProblematicBooking]:
    """AC4: for a set of bookings, which of them need action, keyed by booking id.

    Reviews each venue once rather than each booking, because the answer for one booking
    is a question about every other booking at the same venue. An event with three
    bookings at one venue costs one review, not three.
    """
    by_venue: dict[uuid.UUID, Venue] = {}
    for booking in bookings:
        if booking.venue_id not in by_venue:
            venue = venue_repo.get(db, booking.venue_id)
            assert venue is not None  # a booking cannot exist without its venue.
            by_venue[booking.venue_id] = venue

    found: dict[uuid.UUID, ProblematicBooking] = {}
    for venue in by_venue.values():
        for problem in review(db, venue, now):
            found[problem.booking.id] = problem
    return found
