"""SCRUM-89 AC1, AC2 and AC7: which bookings a buffer change has made problematic.

Pure, so every case gets a fast test (AGENTS.md section 4). The arrangement throughout is
two bookings at one venue, 10:00 to 12:00 and 12:00 to 13:00, which are compatible with no
buffers and stop being compatible as soon as the venue needs any turnaround.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from domain.booking_conflict import (
    BookedPeriod,
    ConflictingBookingError,
    UnavailablePeriod,
    VenueUnavailableError,
)
from domain.venue_booking import BookingStatus
from domain.venue_buffer import NO_BUFFERS, VenueBuffers
from domain.venue_buffer_review import ProblematicBooking, problematic_bookings

_DAY = datetime(2030, 3, 4, tzinfo=UTC)
_EXAMPLE = VenueBuffers(setup_minutes=30, turnaround_minutes=45)

_FIRST = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SECOND = uuid.UUID("00000000-0000-0000-0000-000000000002")
_CLOSURE = uuid.UUID("00000000-0000-0000-0000-0000000000c1")


def at(hours: float) -> datetime:
    return _DAY + timedelta(hours=hours)


def booked(
    id: uuid.UUID, start: float, end: float, status: BookingStatus = BookingStatus.CONFIRMED
) -> BookedPeriod:
    return BookedPeriod(id=id, status=status, start_at=at(start), end_at=at(end))


def closed(start: float, end: float) -> UnavailablePeriod:
    return UnavailablePeriod(id=_CLOSURE, starts_at=at(start), ends_at=at(end))


def flagged_ids(problems: list[ProblematicBooking]) -> list[uuid.UUID]:
    return [problem.booking.id for problem in problems]


# ------------------------------------------------------------------ AC1 and AC2


@pytest.mark.story("SCRUM-89")
def test_nothing_is_problematic_without_buffers() -> None:
    # Back-to-back bookings are compatible until the venue needs time between them.
    bookings = [booked(_FIRST, 10, 12), booked(_SECOND, 12, 13)]

    assert problematic_bookings(bookings, [], NO_BUFFERS) == []


@pytest.mark.story("SCRUM-89")
def test_a_buffer_that_creates_an_overlap_flags_both_sides() -> None:
    # AC2, and the reason both are reported: either could be the one that moves, so
    # naming only the later one would be a guess about what the Coordinator should do.
    bookings = [booked(_FIRST, 10, 12), booked(_SECOND, 12, 13)]

    problems = problematic_bookings(bookings, [], _EXAMPLE)

    assert flagged_ids(problems) == [_FIRST, _SECOND]
    assert all(isinstance(problem.conflict, ConflictingBookingError) for problem in problems)


@pytest.mark.story("SCRUM-89")
def test_each_side_names_the_other_as_the_clash() -> None:
    # AC3: the answer has to say what is in the way, not just that something is.
    bookings = [booked(_FIRST, 10, 12), booked(_SECOND, 12, 13)]

    first, second = problematic_bookings(bookings, [], _EXAMPLE)

    assert isinstance(first.conflict, ConflictingBookingError)
    assert isinstance(second.conflict, ConflictingBookingError)
    assert first.conflict.booking.id == _SECOND
    assert second.conflict.booking.id == _FIRST


@pytest.mark.story("SCRUM-89")
def test_a_booking_is_never_reported_as_clashing_with_itself() -> None:
    bookings = [booked(_FIRST, 10, 12)]

    assert problematic_bookings(bookings, [], _EXAMPLE) == []


@pytest.mark.story("SCRUM-89")
def test_bookings_far_enough_apart_stay_compatible() -> None:
    # 12:45 turnaround ends, 13:15 setup begins: exactly clear, so not a clash (AC2 uses
    # the same half-open rule as SCRUM-82 AC6).
    bookings = [booked(_FIRST, 10, 12), booked(_SECOND, 13.25, 14)]

    assert problematic_bookings(bookings, [], _EXAMPLE) == []


@pytest.mark.story("SCRUM-89")
def test_setup_running_into_a_closure_is_problematic() -> None:
    # AC2's other half: a closure the booking's own setup now reaches into.
    bookings = [booked(_FIRST, 10, 12)]
    closures = [closed(9, 9.6)]

    problems = problematic_bookings(bookings, closures, _EXAMPLE)

    assert flagged_ids(problems) == [_FIRST]
    assert isinstance(problems[0].conflict, VenueUnavailableError)
    assert problems[0].conflict.period.id == _CLOSURE


@pytest.mark.story("SCRUM-89")
def test_a_closure_that_the_buffers_do_not_reach_is_not_problematic() -> None:
    # Closure ends 09:30, setup begins 09:30: touching, so clear.
    bookings = [booked(_FIRST, 10, 12)]

    assert problematic_bookings(bookings, [closed(8, 9.5)], _EXAMPLE) == []


@pytest.mark.story("SCRUM-89")
@pytest.mark.parametrize("status", [s for s in BookingStatus if s is not BookingStatus.CONFIRMED])
def test_only_confirmed_bookings_get_in_the_way(status: BookingStatus) -> None:
    # AC2 says another *confirmed* booking. A pending, rejected or cancelled request holds
    # nothing, which is the rule venue search and approval already use.
    bookings = [booked(_FIRST, 10, 12), booked(_SECOND, 12, 13, status)]

    problems = problematic_bookings(bookings, [], _EXAMPLE)

    assert _FIRST not in flagged_ids(problems)
    # The other one appears only because this test hands it over to be assessed. AC1 says
    # which bookings are assessed, and the service passes confirmed ones only, so in
    # production a request in any of these statuses never reaches here at all.


# ------------------------------------------------------------------ AC7


@pytest.mark.story("SCRUM-89")
def test_reducing_a_buffer_shortens_the_answer() -> None:
    """AC7: no marker has to be cleared, because nothing was stored to clear.

    The same two bookings, asked twice with different buffers. This is the whole of AC7:
    the answer is a question about the venue as it is now, so it cannot go stale.
    """
    bookings = [booked(_FIRST, 10, 12), booked(_SECOND, 12, 13)]

    assert len(problematic_bookings(bookings, [], VenueBuffers(0, 45))) == 2
    assert problematic_bookings(bookings, [], VenueBuffers(0, 0)) == []


@pytest.mark.story("SCRUM-89")
def test_an_empty_venue_has_nothing_to_report() -> None:
    # AC6's condition: this is what "no bookings were affected" is derived from.
    assert problematic_bookings([], [], _EXAMPLE) == []
