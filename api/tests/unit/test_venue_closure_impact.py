"""SCRUM-81: which live arrangements a venue closure affects."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from domain.booking_conflict import BookedPeriod
from domain.venue_booking import BookingStatus
from domain.venue_buffer import VenueBuffers
from domain.venue_closure_impact import affected_by_closure, impact_key

START = datetime(2030, 3, 1, 9, tzinfo=UTC)
H = timedelta(hours=1)
NO_BUFFERS = VenueBuffers(setup_minutes=0, turnaround_minutes=0)


def _booking(start: datetime, hours: int = 2) -> BookedPeriod:
    return BookedPeriod(
        id=uuid.uuid4(), status=BookingStatus.CONFIRMED, start_at=start, end_at=start + hours * H
    )


@pytest.mark.story("SCRUM-81")
def test_only_bookings_the_closure_runs_into_are_affected() -> None:
    inside = _booking(START)
    after = _booking(START + 5 * H)
    touching = _booking(START + 3 * H)

    affected = affected_by_closure([inside, after, touching], START + H, START + 3 * H, NO_BUFFERS)

    assert affected == [inside]


@pytest.mark.story("SCRUM-81")
def test_setup_and_turnaround_time_count() -> None:
    booking = _booking(START + 3 * H)
    buffers = VenueBuffers(setup_minutes=60, turnaround_minutes=0)

    assert affected_by_closure([booking], START + H, START + 2 * H + 30 * (H / 60), buffers) == [
        booking
    ]
    assert affected_by_closure([booking], START + H, START + 2 * H, buffers) == []


@pytest.mark.story("SCRUM-81")
def test_the_impact_key_is_stable_for_a_period_and_new_when_it_moves() -> None:
    closure, booking = uuid.uuid4(), uuid.uuid4()
    first = impact_key(closure, START, START + H, booking)

    assert impact_key(closure, START, START + H, booking) == first
    assert impact_key(closure, START, START + 2 * H, booking) != first
    assert impact_key(closure, START, START + H, uuid.uuid4()) != first
    assert len(first) <= 100
