"""SCRUM-54: the rules for a calendar range. Pure, no database."""

from datetime import UTC, datetime, timedelta

import pytest

from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus
from domain.venue_calendar import (
    BOOKING_LABELS,
    DETAILS_LABELS,
    MAX_RANGE,
    SHOWN_BOOKING_STATUSES,
    EntryKind,
    EntryStatus,
    entry_blocks,
    range_problems,
)

_START = datetime(2026, 11, 2, tzinfo=UTC)


@pytest.mark.story("SCRUM-54")
def test_a_normal_range_is_fine() -> None:
    assert range_problems(_START, _START + timedelta(days=7)) == []


@pytest.mark.story("SCRUM-54")
def test_a_range_in_the_past_is_fine() -> None:
    past = datetime(2020, 1, 1, tzinfo=UTC)
    assert range_problems(past, past + timedelta(days=1)) == []


@pytest.mark.story("SCRUM-54")
def test_the_longest_range_is_allowed_and_one_more_second_is_not() -> None:
    assert range_problems(_START, _START + MAX_RANGE) == []
    assert range_problems(_START, _START + MAX_RANGE + timedelta(seconds=1)) == [
        FieldProblem("end_at", f"must be within {MAX_RANGE.days} days of the start")
    ]


@pytest.mark.story("SCRUM-54")
@pytest.mark.parametrize("length", [timedelta(0), timedelta(hours=-1)])
def test_the_end_must_be_after_the_start(length: timedelta) -> None:
    assert range_problems(_START, _START + length) == [
        FieldProblem("end_at", "must be after the start")
    ]


@pytest.mark.story("SCRUM-54")
def test_times_without_a_timezone_are_refused() -> None:
    naive = _START.replace(tzinfo=None)
    assert range_problems(naive, naive + timedelta(days=1)) == [
        FieldProblem("start_at", "must include a time zone"),
        FieldProblem("end_at", "must include a time zone"),
    ]


@pytest.mark.story("SCRUM-54")
def test_only_confirmed_tentative_and_pending_bookings_are_shown() -> None:
    # SCRUM-83 AC2 adds tentative holds. Rejected and cancelled still hold nothing.
    assert {
        BookingStatus.CONFIRMED,
        BookingStatus.TENTATIVE,
        BookingStatus.PENDING,
    } == SHOWN_BOOKING_STATUSES


@pytest.mark.story("SCRUM-76")
def test_every_shown_booking_status_has_a_calendar_label() -> None:
    # entries() looks up BOOKING_LABELS for every shown booking, so the two must match.
    assert set(BOOKING_LABELS) == SHOWN_BOOKING_STATUSES


@pytest.mark.story("SCRUM-77")
def test_every_booking_status_has_a_details_label() -> None:
    # booking_details() looks up DETAILS_LABELS for any booking, so a new BookingStatus
    # needs a label here or opening that booking would fail.
    assert set(DETAILS_LABELS) == set(BookingStatus)


@pytest.mark.story("SCRUM-76")
@pytest.mark.parametrize(
    ("kind", "status", "blocks"),
    [
        ("unavailability", "unavailable", True),
        ("booking", "confirmed", True),
        ("booking", "pending", False),
    ],
)
def test_only_closures_and_confirmed_bookings_make_a_venue_unavailable(
    kind: EntryKind, status: EntryStatus, blocks: bool
) -> None:
    assert entry_blocks(kind, status) is blocks
