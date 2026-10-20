"""SCRUM-116: when a venue request may replace an affected arrangement."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus
from domain.venue_replacement import Original, replacement_problems

START = datetime(2030, 3, 1, 9, tzinfo=UTC)
END = START + timedelta(hours=2)
ORIGINAL = Original(
    event_request_id="event-1",
    status=BookingStatus.CONFIRMED,
    session_label="Keynote",
    start_at=START,
    end_at=END,
    needs_attention=True,
    has_live_replacement=False,
)


def _problems(
    original: Original | None,
    label: str = "Keynote",
    start_at: datetime = START,
    end_at: datetime = END,
) -> list[FieldProblem]:
    return replacement_problems(original, "event-1", label, start_at, end_at)


@pytest.mark.story("SCRUM-116")
@pytest.mark.parametrize("status", [BookingStatus.CONFIRMED, BookingStatus.TENTATIVE])
def test_an_affected_booking_or_hold_can_be_replaced(status: BookingStatus) -> None:
    assert _problems(replace(ORIGINAL, status=status)) == []
    assert _problems(ORIGINAL, label="  Keynote ") == []


@pytest.mark.story("SCRUM-116")
def test_only_an_arrangement_of_the_same_event_can_be_replaced() -> None:
    expected = [FieldProblem("replaces_booking_id", "is not a venue request of this event")]

    assert _problems(None) == expected
    assert _problems(replace(ORIGINAL, event_request_id="event-2")) == expected


@pytest.mark.story("SCRUM-116")
@pytest.mark.parametrize(
    "status", [BookingStatus.PENDING, BookingStatus.REJECTED, BookingStatus.EXPIRED]
)
def test_only_a_live_commitment_can_be_replaced(status: BookingStatus) -> None:
    assert _problems(replace(ORIGINAL, status=status)) == [
        FieldProblem("replaces_booking_id", "is not a confirmed booking or a live hold")
    ]


@pytest.mark.story("SCRUM-116")
def test_an_arrangement_that_needs_nothing_cannot_be_replaced() -> None:
    assert _problems(replace(ORIGINAL, needs_attention=False)) == [
        FieldProblem("replaces_booking_id", "does not need a replacement")
    ]


@pytest.mark.story("SCRUM-116")
def test_one_replacement_at_a_time() -> None:
    assert _problems(replace(ORIGINAL, has_live_replacement=True)) == [
        FieldProblem("replaces_booking_id", "already has a replacement in progress")
    ]


@pytest.mark.story("SCRUM-116")
def test_the_session_and_period_are_carried_over_unchanged() -> None:
    later = timedelta(hours=1)

    assert _problems(ORIGINAL, "Workshop", START + later, END + later) == [
        FieldProblem("session_label", "must match the arrangement replaced"),
        FieldProblem("start_at", "must match the arrangement replaced"),
        FieldProblem("end_at", "must match the arrangement replaced"),
    ]
