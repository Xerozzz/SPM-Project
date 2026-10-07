"""SCRUM-82 AC3 to AC7: the effective occupied interval, without a database.

The domain is pure, so every rule gets its own fast test (AGENTS.md section 4). The two
comparisons are tested separately because they differ: a booking against another booking
widens both sides, a booking against a closure widens only the booking.
"""

from datetime import UTC, datetime, timedelta

import pytest

from domain.venue_buffer import (
    NO_BUFFERS,
    VenueBuffers,
    booking_clashes_with_closure,
    bookings_clash,
    effective_interval,
)

# The worked example on the ticket: 10:00 to 12:00 at a venue with 30 and 45 minutes.
_DAY = datetime(2030, 3, 4, tzinfo=UTC)
_HOUR = timedelta(hours=1)
_MINUTE = timedelta(minutes=1)
_EXAMPLE = VenueBuffers(setup_minutes=30, turnaround_minutes=45)


def at(hours: float) -> datetime:
    return _DAY + timedelta(hours=hours)


# ------------------------------------------------------------------- AC3, the interval


@pytest.mark.story("SCRUM-82")
def test_the_worked_example_from_the_customer() -> None:
    # An event from 10:00 to 12:00, 30 minutes setup, 45 minutes turnaround, occupies the
    # venue from 09:30 to 12:45.
    assert effective_interval(at(10), at(12), _EXAMPLE) == (at(9.5), at(12.75))


@pytest.mark.story("SCRUM-82")
def test_each_buffer_widens_only_its_own_end() -> None:
    assert effective_interval(at(10), at(12), VenueBuffers(setup_minutes=30)) == (at(9.5), at(12))
    assert effective_interval(at(10), at(12), VenueBuffers(turnaround_minutes=45)) == (
        at(10),
        at(12.75),
    )


@pytest.mark.story("SCRUM-82")
def test_no_buffers_leaves_the_event_times_untouched() -> None:
    # AC7: this is why nothing downstream needs a "does this venue have buffers?" branch.
    assert effective_interval(at(10), at(12), NO_BUFFERS) == (at(10), at(12))
    assert effective_interval(at(10), at(12), VenueBuffers(0, 0)) == (at(10), at(12))


# ------------------------------------------------- AC6, booking against booking


@pytest.mark.story("SCRUM-82")
@pytest.mark.parametrize(
    ("second_start", "clashes"),
    [
        # First event 10:00 to 12:00, so it occupies 09:30 to 12:45. A second event needs
        # to start late enough that its own 09:30-style setup clears 12:45, which means
        # starting at or after 13:15.
        (at(13) - _MINUTE, True),
        (at(13), True),
        (at(13.25) - _MINUTE, True),
        (at(13.25), False),
        (at(13.25) + _MINUTE, False),
    ],
)
def test_two_bookings_need_setup_and_turnaround_of_clear_time_between_them(
    second_start: datetime, clashes: bool
) -> None:
    # AC6 at the boundary, including the exact instant where the two effective intervals
    # touch: ending exactly when another begins is not a conflict (half-open).
    assert bookings_clash(at(10), at(12), second_start, second_start + _HOUR, _EXAMPLE) is clashes


@pytest.mark.story("SCRUM-82")
def test_back_to_back_events_clash_once_the_venue_needs_turnaround() -> None:
    # The behaviour the story exists for. Without buffers, 12:00 to 13:00 straight after a
    # 10:00 to 12:00 event is fine. With 30 and 45 minutes it is not, because the first
    # event's reset and the second's setup overlap.
    assert bookings_clash(at(10), at(12), at(12), at(13), NO_BUFFERS) is False
    assert bookings_clash(at(10), at(12), at(12), at(13), _EXAMPLE) is True


@pytest.mark.story("SCRUM-82")
@pytest.mark.parametrize(
    ("setup", "turnaround"),
    [(0, 0), (30, 45), (45, 30), (15, 15), (0, 90), (90, 0), (5, 7)],
)
def test_widening_both_sides_equals_one_combined_gap(setup: int, turnaround: int) -> None:
    """The identity the docstring on `bookings_clash` claims, checked rather than asserted.

    Widening both intervals by setup at the front and turnaround at the back is the same
    condition as requiring `setup + turnaround` of clear time between the raw intervals,
    because the same shift appears on both sides of the comparison. Worth pinning: if the
    obvious implementation is ever replaced by the cheap one, this says whether it is safe.
    """
    buffers = VenueBuffers(setup, turnaround)
    first_start, first_end = at(10), at(12)

    for minutes in range(0, 360, 5):
        second_start = first_end + minutes * _MINUTE
        second_end = second_start + _HOUR
        combined_gap_is_clear = second_start - first_end >= buffers.combined

        assert bookings_clash(first_start, first_end, second_start, second_end, buffers) is (
            not combined_gap_is_clear
        )


@pytest.mark.story("SCRUM-82")
def test_a_clash_does_not_depend_on_which_booking_is_named_first() -> None:
    early, late = (at(10), at(12)), (at(12.5), at(13))

    assert bookings_clash(*early, *late, _EXAMPLE) is bookings_clash(*late, *early, _EXAMPLE)


# ------------------------------------------------- AC5, booking against a closure


@pytest.mark.story("SCRUM-82")
@pytest.mark.parametrize(
    ("closure_start", "closure_end", "clashes"),
    [
        # Event 10:00 to 12:00 occupies 09:30 to 12:45.
        (at(9), at(9.5), False),  # ends exactly when setup begins
        (at(9), at(9.5) + _MINUTE, True),  # runs one minute into setup
        (at(12.75), at(13), False),  # begins exactly when turnaround ends
        (at(12.75) - _MINUTE, at(13), True),  # begins one minute before it ends
        (at(10.5), at(11), True),  # inside the event itself
    ],
)
def test_a_closure_blocks_the_whole_effective_interval(
    closure_start: datetime, closure_end: datetime, clashes: bool
) -> None:
    # AC5: preparation and reset time may not run into a recorded closure, and the
    # half-open rule applies at both ends.
    assert (
        booking_clashes_with_closure(at(10), at(12), closure_start, closure_end, _EXAMPLE)
        is clashes
    )


@pytest.mark.story("SCRUM-82")
def test_a_closure_is_never_widened() -> None:
    """The closure keeps its own bounds, so a gap of exactly the buffer is still clear.

    If closures were widened too, this 45-minute gap would be treated as a clash. The
    asymmetry is deliberate: a closure already describes the whole unusable period.
    """
    # Closure ends 09:30, the event's setup starts 09:30. Touching, so no clash.
    assert booking_clashes_with_closure(at(10), at(12), at(8), at(9.5), _EXAMPLE) is False


@pytest.mark.story("SCRUM-82")
def test_with_no_buffers_a_closure_check_is_the_event_period() -> None:
    # AC7: identical to the SCRUM-73 behaviour that shipped before buffers existed.
    assert booking_clashes_with_closure(at(10), at(12), at(12), at(13), NO_BUFFERS) is False
    assert booking_clashes_with_closure(at(10), at(12), at(11), at(13), NO_BUFFERS) is True
