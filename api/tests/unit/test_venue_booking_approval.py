"""SCRUM-110 TC-110-01: approval creates a tentative hold, so the approve transition
targets TENTATIVE and the expiry rule is `domain.venue_hold.expiry_problems`. The
constraint-violation mapping is unchanged; the real constraint is exercised in
tests/integration/test_approve_venue_booking.py."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus, InvalidBookingTransitionError, approve
from domain.venue_hold import expiry_problems
from models.venue_booking import VenueBooking
from repositories import venue_availability as booking_repo

_NOW = datetime(2030, 3, 1, 9, 0, tzinfo=UTC)
_EVENT_START = _NOW + timedelta(days=10)


@pytest.mark.story("SCRUM-110")
def test_approving_a_pending_request_creates_a_hold_not_a_confirmation() -> None:
    assert approve(BookingStatus.PENDING) is BookingStatus.TENTATIVE


@pytest.mark.story("SCRUM-110")
@pytest.mark.parametrize(
    "status", [status for status in BookingStatus if status is not BookingStatus.PENDING]
)
def test_only_a_pending_request_can_be_approved(status: BookingStatus) -> None:
    with pytest.raises(InvalidBookingTransitionError) as raised:
        approve(status)

    assert (raised.value.current, raised.value.target) == (status, BookingStatus.TENTATIVE)


@pytest.mark.story("SCRUM-110")
def test_no_pending_or_tentative_row_can_be_confirmed_by_approval() -> None:
    """TC-110-03 at the domain level: the direct-confirmation transition is gone."""
    assert approve(BookingStatus.PENDING) is BookingStatus.TENTATIVE
    with pytest.raises(InvalidBookingTransitionError):
        approve(BookingStatus.TENTATIVE)


@pytest.mark.story("SCRUM-110")
def test_approval_expiry_accepts_one_instant_after_now_and_exactly_booking_start() -> None:
    assert expiry_problems(_NOW + timedelta(seconds=1), _NOW, _EVENT_START) == []
    assert expiry_problems(_EVENT_START, _NOW, _EVENT_START) == []


@pytest.mark.story("SCRUM-110")
@pytest.mark.parametrize("expires_at", [_NOW, _NOW - timedelta(minutes=1)])
def test_approval_expiry_at_or_before_now_is_refused(expires_at: datetime) -> None:
    problems = expiry_problems(expires_at, _NOW, _EVENT_START)

    assert [(p.field, p.reason) for p in problems] == [("expires_at", "must be in the future")]


@pytest.mark.story("SCRUM-110")
def test_approval_expiry_after_booking_start_is_refused() -> None:
    problems = expiry_problems(_EVENT_START + timedelta(seconds=1), _NOW, _EVENT_START)

    assert [(p.field, p.reason) for p in problems] == [
        ("expires_at", "must not be after the event starts")
    ]


@pytest.mark.story("SCRUM-110")
def test_approval_expiry_without_a_time_zone_is_refused() -> None:
    naive = (_NOW + timedelta(days=1)).replace(tzinfo=None)

    problems = expiry_problems(naive, _NOW, _EVENT_START)

    assert [(p.field, p.reason) for p in problems] == [("expires_at", "must include a time zone")]


@pytest.mark.story("SCRUM-110")
def test_an_integrity_error_other_than_the_overlap_constraint_is_not_a_conflict() -> None:
    """Only an exclusion violation means "overlaps another booking". Anything else (a
    broken foreign key, say) is a bug and must surface unchanged, not as a 409."""
    other = IntegrityError("INSERT ...", {}, Exception("foreign key violation"))
    db = MagicMock(spec=Session)
    db.commit.side_effect = other

    with pytest.raises(IntegrityError) as raised:
        booking_repo.save_confirmed_booking(cast(Session, db), VenueBooking())

    assert raised.value is other
    db.rollback.assert_called_once()
