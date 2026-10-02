"""SCRUM-74: venue staff approve a pending booking request; overlapping approvals cannot
both succeed, even when they race, and only venue staff may approve.

SCRUM-74 absorbs SCRUM-40's approve action (ADR-0017), so this is the first HTTP route
that confirms a booking. Real PostgreSQL throughout: the guarantee under test is the
ADR-0002 exclusion constraint from migration 0012, which SQLite could not express.
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.security import hash_password
from domain.booking_conflict import BookingConflictError, ConcurrentBookingConflictError
from domain.venue_booking import BookingStatus, InvalidBookingTransitionError
from models.event_request import EventRequest
from models.organisation import Organisation
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from services import venue_bookings as service
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import make_venue

_START = datetime(2026, 11, 10, 2, 0, tzinfo=UTC)
_END = _START + timedelta(hours=3)
_HOUR = timedelta(hours=1)


def _booking(
    db: Session,
    coordinator: User,
    venue: Venue,
    start_at: datetime = _START,
    end_at: datetime = _END,
    status: BookingStatus = BookingStatus.PENDING,
) -> VenueBooking:
    """A booking row for its own approved event; the coordinator doubles as organiser,
    because neither the conflict rule nor approval looks at who owns the event."""
    event = approved_event(db, coordinator, coordinator, start_at=start_at, end_at=end_at)
    booking = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        start_at=start_at,
        end_at=end_at,
        status=status,
    )
    db.add(booking)
    db.flush()
    return booking


async def _approve(client: httpx.AsyncClient, booking_id: uuid.UUID) -> httpx.Response:
    return await client.post(f"/api/venue-bookings/{booking_id}/approve")


def _confirmed_count(db: Session) -> int:
    statement = select(func.count()).where(VenueBooking.status == BookingStatus.CONFIRMED)
    return db.scalar(statement) or 0


# ------------------------------------------------------------------ normal and boundary


@pytest.mark.story("SCRUM-74")
async def test_venue_staff_approve_a_pending_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    request = _booking(db, make_user("coordinator"), make_venue(db))

    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    db.refresh(request)
    assert request.status is BookingStatus.CONFIRMED


@pytest.mark.story("SCRUM-74")
async def test_back_to_back_confirmed_bookings_are_allowed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Boundary: the constraint's range is half-open '[)', like intervals_overlap, so a
    booking ending exactly when this one starts does not trip it."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    _booking(db, coordinator, venue, _START - _HOUR, _START, BookingStatus.CONFIRMED)
    request = _booking(db, coordinator, venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 200
    assert _confirmed_count(db) == 2


# ------------------------------------------------------------------ conflict and status


@pytest.mark.story("SCRUM-74")
async def test_approving_over_a_confirmed_overlap_is_a_named_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator, venue = make_user("coordinator"), make_venue(db)
    blocking = _booking(db, coordinator, venue, _START + _HOUR, _END, BookingStatus.CONFIRMED)
    request = _booking(db, coordinator, venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 409
    assert str(blocking.id) in response.json()["detail"]
    db.refresh(request)
    assert request.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-74")
@pytest.mark.parametrize("status", [BookingStatus.CONFIRMED, BookingStatus.REJECTED])
async def test_only_a_pending_request_can_be_approved(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: BookingStatus
) -> None:
    request = _booking(db, make_user("coordinator"), make_venue(db), status=status)

    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 409
    assert response.json()["detail"] == f"cannot move a venue booking from {status} to confirmed"


@pytest.mark.story("SCRUM-74")
async def test_approving_an_unknown_booking_is_404(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, uuid.uuid4())

    assert response.status_code == 404


@pytest.mark.story("SCRUM-74")
def test_constraint_refuses_an_overlap_the_friendly_check_missed(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic version of the race: disable the SCRUM-73 check, as if it had read
    the venue before the other approval committed. The database still refuses, and the
    repository reports it as a domain conflict rather than a raw IntegrityError."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    first = _booking(db, coordinator, venue)
    second = _booking(db, coordinator, venue, _START + _HOUR, _END + _HOUR)
    monkeypatch.setattr(service, "_ensure_no_conflict", lambda db, booking: None)

    service.approve(db, first.id)
    with pytest.raises(ConcurrentBookingConflictError):
        service.approve(db, second.id)

    assert _confirmed_count(db) == 1


# ------------------------------------------------------------------ AC2: authorisation


@pytest.mark.story("SCRUM-74")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "tech_support", "attendee"])
async def test_non_venue_staff_cannot_approve_a_conflicting_request(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    """AC2: refused with 403 before any conflict logic runs, and no booking is confirmed."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    _booking(db, coordinator, venue, _START + _HOUR, _END, BookingStatus.CONFIRMED)
    request = _booking(db, coordinator, venue)

    async with make_client(make_user(role)) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 403
    db.refresh(request)
    assert request.status is BookingStatus.PENDING
    assert _confirmed_count(db) == 1


@pytest.mark.story("SCRUM-74")
async def test_anonymous_user_cannot_approve(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    request = _booking(db, make_user("coordinator"), make_venue(db))

    async with make_client(None) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 401
    db.refresh(request)
    assert request.status is BookingStatus.PENDING


# ------------------------------------------------------------------ AC1: concurrency
#
# These need two real transactions racing, which the rolled-back `db` fixture cannot
# express, so they commit their own data and clean it up (as SCRUM-46's race test does).


@dataclass(frozen=True)
class _Committed:
    """Everything one race commits, so it can be deleted afterwards."""

    booking_ids: list[uuid.UUID]
    event_ids: list[uuid.UUID]
    venue_id: uuid.UUID
    user_id: uuid.UUID
    organisation_id: uuid.UUID


def _committed_requests(count: int) -> _Committed:
    """Commit `count` pending requests for the same venue and the same period."""
    session = SessionLocal()
    try:
        organisation = Organisation(name=f"Race organisation {uuid.uuid4()}")
        session.add(organisation)
        session.flush()
        coordinator = User(
            email=f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            roles=["coordinator"],
            organisation_id=organisation.id,
        )
        session.add(coordinator)
        session.flush()
        venue = make_venue(session)
        bookings = [_booking(session, coordinator, venue) for _ in range(count)]
        session.commit()
        return _Committed(
            booking_ids=[b.id for b in bookings],
            event_ids=[b.event_request_id for b in bookings],
            venue_id=venue.id,
            user_id=coordinator.id,
            organisation_id=organisation.id,
        )
    finally:
        session.close()


def _delete_committed(committed: _Committed) -> None:
    """Delete children before parents, flushing between levels for the foreign keys."""
    session = SessionLocal()
    try:
        levels: list[list[object]] = [
            [session.get(VenueBooking, i) for i in committed.booking_ids],
            [session.get(EventRequest, i) for i in committed.event_ids],
            [session.get(Venue, committed.venue_id)],
            [session.get(User, committed.user_id)],
            [session.get(Organisation, committed.organisation_id)],
        ]
        for rows in levels:
            for row in rows:
                session.delete(row)
            session.flush()
        session.commit()
    finally:
        session.close()


def _race(booking_ids: list[uuid.UUID]) -> tuple[list[str], int]:
    """Approve each booking on its own thread and session, released together."""
    start_together = threading.Barrier(len(booking_ids))
    outcomes: list[str] = []

    def approve_once(booking_id: uuid.UUID) -> None:
        session = SessionLocal()
        try:
            start_together.wait()
            service.approve(session, booking_id)
            outcomes.append("approved")
        except BookingConflictError:
            outcomes.append("conflict")
        except InvalidBookingTransitionError:
            outcomes.append("already decided")
        finally:
            session.close()

    threads = [threading.Thread(target=approve_once, args=(b,)) for b in booking_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    session = SessionLocal()
    try:
        statement = select(func.count()).where(
            VenueBooking.id.in_(booking_ids), VenueBooking.status == BookingStatus.CONFIRMED
        )
        confirmed = session.scalar(statement) or 0
    finally:
        session.close()
    return outcomes, confirmed


@pytest.mark.story("SCRUM-74")
@pytest.mark.parametrize("attempt", range(5))
def test_simultaneous_overlapping_approvals_yield_exactly_one_success(attempt: int) -> None:
    """AC1: two venue staff approve two different, overlapping requests at the same
    instant. Each locks only its own booking row, so both may pass the friendly check;
    the exclusion constraint lets exactly one commit, and the other is a conflict."""
    del attempt  # the run number only exists to repeat the race
    committed = _committed_requests(2)
    try:
        outcomes, confirmed = _race(committed.booking_ids)

        assert sorted(outcomes) == ["approved", "conflict"]
        assert confirmed == 1
    finally:
        _delete_committed(committed)


@pytest.mark.story("SCRUM-74")
@pytest.mark.parametrize("attempt", range(3))
def test_simultaneous_approvals_of_the_same_request_yield_exactly_one_success(
    attempt: int,
) -> None:
    """Two staff click Approve on the same request at once. The booking-row lock makes
    the second wait, then see CONFIRMED and be refused, not report a second success."""
    del attempt
    committed = _committed_requests(1)
    try:
        outcomes, confirmed = _race(committed.booking_ids * 2)

        assert sorted(outcomes) == ["already decided", "approved"]
        assert confirmed == 1
    finally:
        _delete_committed(committed)
