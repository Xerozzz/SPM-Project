"""SCRUM-73: a venue booking request cannot be approved while a confirmed booking or a
recorded unavailability block on the same venue overlaps its [start, end) period.

Driven through `services.venue_bookings.check_approvable` against real PostgreSQL, so
the repository's overlap queries are exercised, not just the domain rule. There is no
HTTP route yet: SCRUM-40 owns the approve action and will call this check first, and
SCRUM-74 owns concurrency (ADR-0016).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.booking_conflict import ConflictingBookingError, VenueUnavailableError
from domain.venue_booking import BookingStatus
from domain.venue_search import BLOCKING_STATUSES
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability
from services import venue_bookings as service
from tests.integration.test_submit_event_request import MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import effective_for, make_venue

_START = datetime(2026, 11, 3, 2, 0, tzinfo=UTC)
_END = _START + timedelta(hours=3)
_HOUR = timedelta(hours=1)

# Every status that must NOT block approval (AC4), derived from the enum.
# SCRUM-83: a tentative hold blocks like a confirmed booking, so it is left out here.
_NOT_CONFIRMED = [status for status in BookingStatus if status not in BLOCKING_STATUSES]


def _booking(
    db: Session,
    coordinator: User,
    venue: Venue,
    start_at: datetime,
    end_at: datetime,
    status: BookingStatus = BookingStatus.CONFIRMED,
) -> VenueBooking:
    """A booking row in `status`, arranged directly for the test — SCRUM-40's approve
    action, which would normally produce a confirmed one, is not built yet. The
    coordinator doubles as the event's organiser: the conflict check never looks at who
    owns the event, so a separate organiser would only add noise."""
    event = approved_event(db, coordinator, coordinator, start_at=start_at, end_at=end_at)
    effective_start, effective_end = effective_for(venue, start_at, end_at)
    booking = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        start_at=start_at,
        end_at=end_at,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=status,
    )
    db.add(booking)
    db.flush()
    return booking


def _closure(
    db: Session, venue: Venue, starts_at: datetime, ends_at: datetime
) -> VenueUnavailability:
    closure = VenueUnavailability(
        venue_id=venue.id, starts_at=starts_at, ends_at=ends_at, reason="Maintenance"
    )
    db.add(closure)
    db.flush()
    return closure


def _request(db: Session, coordinator: User, venue: Venue) -> VenueBooking:
    """The pending request under review, for [_START, _END)."""
    return _booking(db, coordinator, venue, _START, _END, BookingStatus.PENDING)


# ------------------------------------------------------------------ normal case


@pytest.mark.story("SCRUM-73")
def test_request_with_nothing_else_on_the_venue_is_approvable(
    db: Session, make_user: MakeUser
) -> None:
    coordinator = make_user("coordinator")
    request = _request(db, coordinator, make_venue(db))

    assert service.check_approvable(db, request.id) == request


@pytest.mark.story("SCRUM-73")
def test_confirmed_booking_on_a_different_venue_does_not_block(
    db: Session, make_user: MakeUser
) -> None:
    coordinator = make_user("coordinator")
    request = _request(db, coordinator, make_venue(db))
    _booking(db, coordinator, make_venue(db, name="Hall B"), _START, _END)
    _closure(db, make_venue(db, name="Hall C"), _START, _END)

    assert service.check_approvable(db, request.id) == request


@pytest.mark.story("SCRUM-73")
def test_unknown_booking_id_is_not_found(db: Session) -> None:
    with pytest.raises(service.BookingNotFoundError):
        service.check_approvable(db, uuid.uuid4())


# ------------------------------------------------------------------ AC1 / AC2


@pytest.mark.story("SCRUM-73")
def test_ac1_overlapping_confirmed_booking_refuses_approval_and_names_it(
    db: Session, make_user: MakeUser
) -> None:
    coordinator = make_user("coordinator")
    venue = make_venue(db)
    request = _request(db, coordinator, venue)
    confirmed = _booking(db, coordinator, venue, _START + _HOUR, _END + _HOUR)

    with pytest.raises(ConflictingBookingError) as raised:
        service.check_approvable(db, request.id)

    assert raised.value.booking.id == confirmed.id
    assert str(confirmed.id) in str(raised.value)


@pytest.mark.story("SCRUM-73")
def test_ac2_confirmed_booking_ending_exactly_when_the_request_begins_does_not_block(
    db: Session, make_user: MakeUser
) -> None:
    coordinator = make_user("coordinator")
    venue = make_venue(db)
    request = _request(db, coordinator, venue)
    _booking(db, coordinator, venue, _START - _HOUR, _START)

    assert service.check_approvable(db, request.id) == request


@pytest.mark.story("SCRUM-73")
def test_ac2_confirmed_booking_starting_exactly_when_the_request_ends_does_not_block(
    db: Session, make_user: MakeUser
) -> None:
    coordinator = make_user("coordinator")
    venue = make_venue(db)
    request = _request(db, coordinator, venue)
    _booking(db, coordinator, venue, _END, _END + _HOUR)

    assert service.check_approvable(db, request.id) == request


# ------------------------------------------------------------------ AC3 / AC5


@pytest.mark.story("SCRUM-73")
def test_ac3_overlapping_unavailability_refuses_approval_and_names_the_period(
    db: Session, make_user: MakeUser
) -> None:
    coordinator = make_user("coordinator")
    venue = make_venue(db)
    request = _request(db, coordinator, venue)
    closure = _closure(db, venue, _START - _HOUR, _START + _HOUR)

    with pytest.raises(VenueUnavailableError) as raised:
        service.check_approvable(db, request.id)

    assert raised.value.period.id == closure.id
    assert raised.value.period.starts_at == closure.starts_at
    assert raised.value.period.ends_at == closure.ends_at


@pytest.mark.story("SCRUM-73")
def test_ac5_unavailability_ending_exactly_when_the_request_begins_does_not_block(
    db: Session, make_user: MakeUser
) -> None:
    coordinator = make_user("coordinator")
    venue = make_venue(db)
    request = _request(db, coordinator, venue)
    _closure(db, venue, _START - _HOUR, _START)

    assert service.check_approvable(db, request.id) == request


# ------------------------------------------------------------------ AC4


@pytest.mark.story("SCRUM-73")
@pytest.mark.parametrize("status", _NOT_CONFIRMED)
def test_ac4_overlapping_booking_that_is_not_confirmed_does_not_block(
    db: Session, make_user: MakeUser, status: BookingStatus
) -> None:
    coordinator = make_user("coordinator")
    venue = make_venue(db)
    request = _request(db, coordinator, venue)
    _booking(db, coordinator, venue, _START, _END, status)

    assert service.check_approvable(db, request.id) == request


@pytest.mark.story("SCRUM-73")
def test_already_confirmed_booking_does_not_conflict_with_itself(
    db: Session, make_user: MakeUser
) -> None:
    coordinator = make_user("coordinator")
    confirmed = _booking(db, coordinator, make_venue(db), _START, _END)

    assert service.check_approvable(db, confirmed.id) == confirmed
