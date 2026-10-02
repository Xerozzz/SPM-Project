"""SCRUM-74: the venue booking approve transition, and how the repository reports a
constraint violation. Database-free: the real constraint is exercised in
tests/integration/test_approve_venue_booking.py."""

from typing import cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus, InvalidBookingTransitionError, approve
from models.venue_booking import VenueBooking
from repositories import venue_availability as booking_repo


@pytest.mark.story("SCRUM-74")
def test_a_pending_request_is_confirmed() -> None:
    assert approve(BookingStatus.PENDING) is BookingStatus.CONFIRMED


@pytest.mark.story("SCRUM-74")
@pytest.mark.parametrize(
    "status", [status for status in BookingStatus if status is not BookingStatus.PENDING]
)
def test_only_a_pending_request_can_be_approved(status: BookingStatus) -> None:
    with pytest.raises(InvalidBookingTransitionError) as raised:
        approve(status)

    assert (raised.value.current, raised.value.target) == (status, BookingStatus.CONFIRMED)


@pytest.mark.story("SCRUM-74")
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
