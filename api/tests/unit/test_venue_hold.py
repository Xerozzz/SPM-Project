"""SCRUM-83: tentative venue hold rules, without a database."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from domain.booking_conflict import BookedPeriod, ConflictingBookingError, ensure_no_conflict
from domain.venue_booking import BookingStatus, InvalidBookingTransitionError, hold
from domain.venue_buffer import NO_BUFFERS
from domain.venue_calendar import BOOKING_LABELS, DETAILS_LABELS, entry_blocks
from domain.venue_hold import HoldExpiredError, confirm, expire, expiry_problems, is_due
from domain.venue_search import BLOCKING_STATUSES, booking_blocks_availability

_NOW = datetime(2030, 3, 1, 9, 0, tzinfo=UTC)
_EVENT_START = _NOW + timedelta(days=10)
_EVENT_END = _EVENT_START + timedelta(hours=3)


# ------------------------------------------------------------------ AC1: placing a hold


@pytest.mark.story("SCRUM-83")
def test_a_pending_request_can_be_held() -> None:
    assert hold(BookingStatus.PENDING) is BookingStatus.TENTATIVE


@pytest.mark.story("SCRUM-83")
@pytest.mark.parametrize("status", [s for s in BookingStatus if s is not BookingStatus.PENDING])
def test_only_a_pending_request_can_be_held(status: BookingStatus) -> None:
    with pytest.raises(InvalidBookingTransitionError):
        hold(status)


@pytest.mark.story("SCRUM-83")
def test_an_expiry_in_the_future_before_the_event_is_valid() -> None:
    assert expiry_problems(_NOW + timedelta(days=2), _NOW, _EVENT_START) == []


@pytest.mark.story("SCRUM-83")
def test_an_expiry_exactly_at_the_event_start_is_valid() -> None:
    assert expiry_problems(_EVENT_START, _NOW, _EVENT_START) == []


@pytest.mark.story("SCRUM-83")
def test_an_expiry_after_the_event_starts_is_refused() -> None:
    problems = expiry_problems(_EVENT_START + timedelta(seconds=1), _NOW, _EVENT_START)

    assert [(p.field, p.reason) for p in problems] == [
        ("expires_at", "must not be after the event starts")
    ]


@pytest.mark.story("SCRUM-83")
@pytest.mark.parametrize("expires_at", [_NOW, _NOW - timedelta(minutes=1)])
def test_an_expiry_that_is_not_in_the_future_is_refused(expires_at: datetime) -> None:
    problems = expiry_problems(expires_at, _NOW, _EVENT_START)

    assert [(p.field, p.reason) for p in problems] == [("expires_at", "must be in the future")]


@pytest.mark.story("SCRUM-83")
def test_an_expiry_without_a_time_zone_is_refused() -> None:
    naive = (_NOW + timedelta(days=1)).replace(tzinfo=None)

    problems = expiry_problems(naive, _NOW, _EVENT_START)

    assert [(p.field, p.reason) for p in problems] == [("expires_at", "must include a time zone")]


# ------------------------------------------------------------------ AC2: shown as Tentative


@pytest.mark.story("SCRUM-83")
def test_a_hold_is_labelled_tentative_not_confirmed() -> None:
    assert BOOKING_LABELS[BookingStatus.TENTATIVE] == "tentative"
    assert DETAILS_LABELS[BookingStatus.TENTATIVE] == "tentative"
    assert BOOKING_LABELS[BookingStatus.CONFIRMED] == "confirmed"


# ------------------------------------------------------------------ AC3: a hold blocks


@pytest.mark.story("SCRUM-83")
def test_a_tentative_hold_blocks_like_a_confirmed_booking() -> None:
    assert {BookingStatus.CONFIRMED, BookingStatus.TENTATIVE} == BLOCKING_STATUSES
    assert booking_blocks_availability(BookingStatus.TENTATIVE)
    assert entry_blocks("booking", "tentative")


@pytest.mark.story("SCRUM-83")
def test_a_pending_request_still_does_not_block() -> None:
    assert not booking_blocks_availability(BookingStatus.PENDING)
    assert not entry_blocks("booking", "pending")


@pytest.mark.story("SCRUM-83")
def test_an_overlapping_hold_blocks_approval_and_is_named_as_a_hold() -> None:
    held = BookedPeriod(uuid4(), BookingStatus.TENTATIVE, _EVENT_START, _EVENT_END)

    with pytest.raises(ConflictingBookingError) as raised:
        ensure_no_conflict(_EVENT_START, _EVENT_END, [held], [], NO_BUFFERS)

    assert raised.value.booking == held
    assert str(raised.value) == f"conflicts with tentative hold {held.id}"


@pytest.mark.story("SCRUM-83")
def test_a_confirmed_clash_is_still_named_as_a_confirmed_booking() -> None:
    confirmed = BookedPeriod(uuid4(), BookingStatus.CONFIRMED, _EVENT_START, _EVENT_END)

    with pytest.raises(ConflictingBookingError) as raised:
        ensure_no_conflict(_EVENT_START, _EVENT_END, [confirmed], [], NO_BUFFERS)

    assert str(raised.value) == f"conflicts with confirmed booking {confirmed.id}"


@pytest.mark.story("SCRUM-83")
def test_a_hold_ending_exactly_when_a_request_starts_does_not_block() -> None:
    held = BookedPeriod(
        uuid4(), BookingStatus.TENTATIVE, _EVENT_START - timedelta(hours=2), _EVENT_START
    )

    ensure_no_conflict(_EVENT_START, _EVENT_END, [held], [], NO_BUFFERS)


# ------------------------------------------------------------------ SCRUM-107: confirming


@pytest.mark.story("SCRUM-107")
def test_an_active_hold_is_confirmed() -> None:
    assert confirm(BookingStatus.TENTATIVE, _NOW + timedelta(hours=1), _NOW) is (
        BookingStatus.CONFIRMED
    )


@pytest.mark.story("SCRUM-107")
@pytest.mark.parametrize("expires_at", [_NOW, _NOW - timedelta(minutes=1), None])
def test_an_expired_hold_cannot_be_confirmed(expires_at: datetime | None) -> None:
    with pytest.raises(HoldExpiredError) as raised:
        confirm(BookingStatus.TENTATIVE, expires_at, _NOW)

    # Reported like any refused decision: a transition from tentative to confirmed.
    assert isinstance(raised.value, InvalidBookingTransitionError)
    assert (raised.value.current, raised.value.target) == (
        BookingStatus.TENTATIVE,
        BookingStatus.CONFIRMED,
    )
    assert str(raised.value) == f"the tentative hold expired at {expires_at}"


@pytest.mark.story("SCRUM-107")
@pytest.mark.parametrize("status", [s for s in BookingStatus if s is not BookingStatus.TENTATIVE])
def test_only_a_tentative_hold_goes_through_hold_confirmation(status: BookingStatus) -> None:
    with pytest.raises(InvalidBookingTransitionError) as raised:
        confirm(status, _NOW + timedelta(hours=1), _NOW)

    assert not isinstance(raised.value, HoldExpiredError)


# ------------------------------------------------------------------ SCRUM-108: expiring


@pytest.mark.story("SCRUM-108")
def test_a_hold_is_due_once_its_expiry_is_reached() -> None:
    assert is_due(BookingStatus.TENTATIVE, _NOW, _NOW)
    assert is_due(BookingStatus.TENTATIVE, _NOW - timedelta(minutes=1), _NOW)
    assert not is_due(BookingStatus.TENTATIVE, _NOW + timedelta(seconds=1), _NOW)


@pytest.mark.story("SCRUM-108")
@pytest.mark.parametrize("status", [s for s in BookingStatus if s is not BookingStatus.TENTATIVE])
def test_only_a_tentative_hold_is_ever_due(status: BookingStatus) -> None:
    assert not is_due(status, _NOW - timedelta(days=1), _NOW)


@pytest.mark.story("SCRUM-108")
def test_a_due_hold_expires() -> None:
    assert expire(BookingStatus.TENTATIVE, _NOW, _NOW) is BookingStatus.EXPIRED


@pytest.mark.story("SCRUM-108")
@pytest.mark.parametrize(
    ("status", "expires_at"),
    [
        (BookingStatus.TENTATIVE, _NOW + timedelta(minutes=1)),
        (BookingStatus.CONFIRMED, _NOW - timedelta(minutes=1)),
        (BookingStatus.TENTATIVE, None),
    ],
)
def test_a_hold_that_is_not_due_cannot_expire(
    status: BookingStatus, expires_at: datetime | None
) -> None:
    with pytest.raises(InvalidBookingTransitionError):
        expire(status, expires_at, _NOW)


@pytest.mark.story("SCRUM-108")
def test_an_expired_hold_no_longer_blocks_and_is_not_on_the_calendar() -> None:
    assert not booking_blocks_availability(BookingStatus.EXPIRED)
    assert BookingStatus.EXPIRED not in BOOKING_LABELS
    assert DETAILS_LABELS[BookingStatus.EXPIRED] == "expired"
