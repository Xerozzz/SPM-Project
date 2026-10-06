"""SCRUM-40: the rules for rejecting a venue booking request. Pure, no database."""

import pytest

from domain.venue_booking import BookingStatus, InvalidBookingTransitionError
from domain.venue_booking_decision import clean_reason, reject


@pytest.mark.story("SCRUM-40")
def test_a_pending_request_can_be_rejected() -> None:
    assert reject(BookingStatus.PENDING) is BookingStatus.REJECTED


@pytest.mark.story("SCRUM-40")
@pytest.mark.parametrize(
    "decided", [BookingStatus.CONFIRMED, BookingStatus.REJECTED, BookingStatus.CANCELLED]
)
def test_a_decided_request_cannot_be_decided_again(decided: BookingStatus) -> None:
    with pytest.raises(InvalidBookingTransitionError) as raised:
        reject(decided)
    assert raised.value.current is decided
    assert raised.value.target is BookingStatus.REJECTED


@pytest.mark.story("SCRUM-40")
@pytest.mark.parametrize(
    ("given", "stored"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("  Hall closed for works ", "Hall closed for works"),
    ],
)
def test_the_reason_is_optional_and_trimmed(given: str | None, stored: str | None) -> None:
    assert clean_reason(given) == stored
