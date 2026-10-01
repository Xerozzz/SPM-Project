"""Venue booking approval conflicts (SCRUM-73): pure, no I/O, no database."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from domain.booking_conflict import (
    BookedPeriod,
    ConflictingBookingError,
    UnavailablePeriod,
    VenueUnavailableError,
    ensure_no_conflict,
)
from domain.venue_booking import BookingStatus

# The shared half-open rule booking_conflict builds on; tested here against the cases
# SCRUM-73 depends on, since approval now relies on it as much as search does.
from domain.venue_search import intervals_overlap

_START = datetime(2026, 11, 3, 2, 0, tzinfo=UTC)
_END = _START + timedelta(hours=3)
_HOUR = timedelta(hours=1)

# Every status that must NOT block approval (AC4). Derived from the enum rather than
# listed, so a status added later is covered here automatically.
_NOT_CONFIRMED = [status for status in BookingStatus if status is not BookingStatus.CONFIRMED]


def _booked(
    start_at: datetime, end_at: datetime, status: BookingStatus = BookingStatus.CONFIRMED
) -> BookedPeriod:
    return BookedPeriod(id=uuid4(), status=status, start_at=start_at, end_at=end_at)


def _closed(starts_at: datetime, ends_at: datetime) -> UnavailablePeriod:
    return UnavailablePeriod(id=uuid4(), starts_at=starts_at, ends_at=ends_at)


# ------------------------------------------------------------------ intervals_overlap


@pytest.mark.story("SCRUM-73")
@pytest.mark.parametrize(
    ("other_start", "other_end", "expected"),
    [
        (_START - _HOUR, _START + _HOUR, True),  # overlaps the start
        (_END - _HOUR, _END + _HOUR, True),  # overlaps the end
        (_START + _HOUR, _END - _HOUR, True),  # inside
        (_START - _HOUR, _END + _HOUR, True),  # contains
        (_START, _END, True),  # identical
        (_START - _HOUR, _START, False),  # ends exactly at our start
        (_END, _END + _HOUR, False),  # starts exactly at our end
        (_END + _HOUR, _END + 2 * _HOUR, False),  # entirely after
    ],
)
def test_intervals_overlap_is_half_open(
    other_start: datetime, other_end: datetime, expected: bool
) -> None:
    assert intervals_overlap(_START, _END, other_start, other_end) is expected
    assert intervals_overlap(other_start, other_end, _START, _END) is expected


@pytest.mark.story("SCRUM-73")
def test_intervals_overlap_refuses_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        intervals_overlap(_START.replace(tzinfo=None), _END, _START, _END)


# ------------------------------------------------------------------ bookings (AC1, AC2, AC4)


@pytest.mark.story("SCRUM-73")
def test_nothing_on_the_venue_means_no_conflict() -> None:
    ensure_no_conflict(_START, _END, [], [])


@pytest.mark.story("SCRUM-73")
def test_overlapping_confirmed_booking_is_a_conflict_naming_that_booking() -> None:
    clash = _booked(_START + _HOUR, _END + _HOUR)

    with pytest.raises(ConflictingBookingError) as raised:
        ensure_no_conflict(_START, _END, [clash], [])

    assert raised.value.booking == clash
    assert str(clash.id) in str(raised.value)


@pytest.mark.story("SCRUM-73")
def test_boundary_confirmed_booking_ending_exactly_at_the_start_does_not_conflict() -> None:
    ensure_no_conflict(_START, _END, [_booked(_START - _HOUR, _START)], [])


@pytest.mark.story("SCRUM-73")
def test_boundary_confirmed_booking_starting_exactly_at_the_end_does_not_conflict() -> None:
    ensure_no_conflict(_START, _END, [_booked(_END, _END + _HOUR)], [])


@pytest.mark.story("SCRUM-73")
@pytest.mark.parametrize("status", _NOT_CONFIRMED)
def test_overlapping_booking_that_is_not_confirmed_does_not_conflict(
    status: BookingStatus,
) -> None:
    ensure_no_conflict(_START, _END, [_booked(_START, _END, status)], [])


@pytest.mark.story("SCRUM-73")
def test_earliest_clashing_booking_is_named_whatever_the_input_order() -> None:
    later = _booked(_START + _HOUR, _END)
    earlier = _booked(_START - _HOUR, _START + _HOUR)

    with pytest.raises(ConflictingBookingError) as raised:
        ensure_no_conflict(_START, _END, [later, earlier], [])

    assert raised.value.booking == earlier


# ------------------------------------------------------------------ closures (AC3, AC5)


@pytest.mark.story("SCRUM-73")
def test_overlapping_unavailability_is_a_conflict_naming_that_period() -> None:
    closure = _closed(_START - _HOUR, _START + _HOUR)

    with pytest.raises(VenueUnavailableError) as raised:
        ensure_no_conflict(_START, _END, [], [closure])

    assert raised.value.period == closure
    assert str(closure.id) in str(raised.value)


@pytest.mark.story("SCRUM-73")
def test_boundary_unavailability_ending_exactly_at_the_start_does_not_conflict() -> None:
    ensure_no_conflict(_START, _END, [], [_closed(_START - _HOUR, _START)])


@pytest.mark.story("SCRUM-73")
def test_earliest_clashing_unavailability_is_named_whatever_the_input_order() -> None:
    later = _closed(_END - _HOUR, _END + _HOUR)
    earlier = _closed(_START, _START + _HOUR)

    with pytest.raises(VenueUnavailableError) as raised:
        ensure_no_conflict(_START, _END, [], [later, earlier])

    assert raised.value.period == earlier


@pytest.mark.story("SCRUM-73")
def test_a_clashing_booking_is_reported_before_a_clashing_unavailability() -> None:
    with pytest.raises(ConflictingBookingError):
        ensure_no_conflict(_START, _END, [_booked(_START, _END)], [_closed(_START, _END)])
