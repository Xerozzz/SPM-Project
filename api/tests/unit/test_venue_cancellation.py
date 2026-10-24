"""SCRUM-109: cancelling one venue arrangement, without a database."""

from datetime import UTC, datetime, timedelta

import pytest

from domain.event_status import EventStatus
from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus, InvalidBookingTransitionError
from domain.venue_cancellation import EventRefusal, cancel, event_refusal, reason_problems
from domain.venue_search import BLOCKING_STATUSES, booking_blocks_availability

_NOW = datetime(2030, 3, 1, 9, 0, tzinfo=UTC)
_LATER = _NOW + timedelta(days=2)


# ------------------------------------------------------------------ AC1: what may be cancelled


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize("status", [BookingStatus.PENDING, BookingStatus.CONFIRMED])
def test_a_pending_request_or_confirmed_booking_is_cancelled(status: BookingStatus) -> None:
    assert cancel(status, None, _NOW) is BookingStatus.CANCELLED


@pytest.mark.story("SCRUM-109")
def test_an_active_hold_is_cancelled() -> None:
    assert cancel(BookingStatus.TENTATIVE, _LATER, _NOW) is BookingStatus.CANCELLED


@pytest.mark.story("SCRUM-109")
def test_a_hold_one_microsecond_before_its_expiry_is_still_active() -> None:
    expires_at = _NOW + timedelta(microseconds=1)
    assert cancel(BookingStatus.TENTATIVE, expires_at, _NOW) is BookingStatus.CANCELLED


# ------------------------------------------------------------------ AC5 and AC10: refused


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize(
    "status", [BookingStatus.CANCELLED, BookingStatus.REJECTED, BookingStatus.EXPIRED]
)
def test_a_cancelled_rejected_or_expired_arrangement_cannot_be_cancelled(
    status: BookingStatus,
) -> None:
    with pytest.raises(InvalidBookingTransitionError) as refused:
        cancel(status, _LATER, _NOW)
    assert (refused.value.current, refused.value.target) == (status, BookingStatus.CANCELLED)


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize(
    "expires_at", [_NOW, _NOW - timedelta(microseconds=1)], ids=["at expiry", "after"]
)
def test_a_hold_at_or_past_its_expiry_is_expired_not_cancellable(expires_at: datetime) -> None:
    """AC10: the timer may not have run yet, but at its deadline the hold has expired, so
    it can never be both expired and cancelled."""
    with pytest.raises(InvalidBookingTransitionError):
        cancel(BookingStatus.TENTATIVE, expires_at, _NOW)


@pytest.mark.story("SCRUM-109")
def test_a_hold_without_an_expiry_is_not_treated_as_active() -> None:
    """The same rule as domain.venue_hold.ensure_active. The database refuses such a row
    (venue_bookings_tentative_has_hold); this keeps the two rules from disagreeing."""
    with pytest.raises(InvalidBookingTransitionError):
        cancel(BookingStatus.TENTATIVE, None, _NOW)


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize("status", list(BookingStatus))
def test_every_status_is_either_cancellable_or_refused(status: BookingStatus) -> None:
    """The rule covers the whole closed list, so a status added later must be decided."""
    cancellable = {BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.TENTATIVE}
    if status in cancellable:
        assert cancel(status, _LATER, _NOW) is BookingStatus.CANCELLED
    else:
        with pytest.raises(InvalidBookingTransitionError):
            cancel(status, _LATER, _NOW)


# ------------------------------------------------------------------ AC3: stops blocking


@pytest.mark.story("SCRUM-109")
def test_a_cancelled_arrangement_never_blocks_the_venue() -> None:
    """The rule search, availability, the calendar and conflict checks share."""
    assert BookingStatus.CANCELLED not in BLOCKING_STATUSES
    assert booking_blocks_availability(BookingStatus.CANCELLED) is False


# ------------------------------------------------------------------ AC7 and AC9: the event


@pytest.mark.story("SCRUM-109")
def test_an_approved_event_allows_cancelling() -> None:
    assert event_refusal(EventStatus.APPROVED) is None


@pytest.mark.story("SCRUM-109")
def test_a_confirmed_event_needs_the_venue_change_flow() -> None:
    assert event_refusal(EventStatus.CONFIRMED) is EventRefusal.CONFIRMED_NEEDS_VENUE_CHANGE


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize(
    "status",
    [s for s in EventStatus if s not in (EventStatus.APPROVED, EventStatus.CONFIRMED)],
)
def test_every_other_event_status_is_not_in_planning(status: EventStatus) -> None:
    """AC7: only Approved is allowed, so any status — including one added later, such as
    Cancelled or Completed — falls here without changing this rule."""
    assert event_refusal(status) is EventRefusal.NOT_IN_PLANNING


# ------------------------------------------------------------------ AC4: the reason


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize("reason", [None, "", " ", "\t\n  "], ids=["none", "empty", "space", "ws"])
def test_a_blank_reason_is_a_field_error(reason: str | None) -> None:
    assert reason_problems(reason) == [FieldProblem("reason", "is required")]


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize("reason", ["Venue no longer needed", "  x  "])
def test_a_reason_with_any_text_is_accepted(reason: str) -> None:
    assert reason_problems(reason) == []
