"""SCRUM-110: Venue Staff approval of a pending request creates a time-limited
Tentative hold (TC-110-02), never a confirmation (TC-110-03). Overlapping approvals
cannot both succeed, even when they race, and only venue staff may approve (TC-110-04).

Supersedes the SCRUM-74 direct-confirmation expectations on this route: approval IS the
SCRUM-83 hold, so the row lock, buffered conflict check, exclusion constraint and
SCRUM-108 expiry processing are the hold's. Real PostgreSQL throughout: the guarantee
under test is the ADR-0002 exclusion constraint, which SQLite could not express.
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from psycopg.errors import DeadlockDetected, QueryCanceled
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.security import hash_password
from domain.booking_conflict import BookingConflictError, ConcurrentBookingConflictError
from domain.venue_booking import BookingStatus, InvalidBookingTransitionError
from models.event_request import EventRequest
from models.notification import Notification
from models.organisation import Organisation
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from repositories import venue_availability
from services import venue_bookings as service
from services.venue_bookings import InvalidHoldError
from tests.integration.test_submit_event_request import _VENUE_NAME, MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import effective_for, make_venue

_START = datetime(2026, 11, 10, 2, 0, tzinfo=UTC)
_END = _START + timedelta(hours=3)
_HOUR = timedelta(hours=1)
# A valid approval expiry: after now, no later than the booking start (AC1).
_EXPIRY = _START - timedelta(days=1)


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
    effective_start, effective_end = effective_for(venue, start_at, end_at)
    hold_fields = (
        {"expires_at": _EXPIRY, "held_by_id": coordinator.id, "held_at": datetime.now(UTC)}
        if status is BookingStatus.TENTATIVE
        else {}
    )
    booking = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        session_label="Opening keynote",
        start_at=start_at,
        end_at=end_at,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=status,
        **hold_fields,
    )
    db.add(booking)
    db.flush()
    return booking


async def _approve(
    client: httpx.AsyncClient, booking_id: uuid.UUID, expires_at: object = None
) -> httpx.Response:
    return await client.post(
        f"/api/venue-bookings/{booking_id}/approve",
        json={"expires_at": _EXPIRY.isoformat() if expires_at is None else expires_at},
    )


def _held_count(db: Session) -> int:
    statement = select(func.count()).where(VenueBooking.status == BookingStatus.TENTATIVE)
    return db.scalar(statement) or 0


# ------------------------------------------------------------------ normal and boundary


@pytest.mark.story("SCRUM-110")
async def test_venue_staff_approve_a_pending_request_creates_a_hold(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-110-02: the same row becomes Tentative, keeping its venue, event and period,
    and recording the approving staff and UTC action time."""
    staff = make_user("venue_staff")
    request = _booking(db, make_user("coordinator"), make_venue(db))
    venue_id, event_id, start_at, end_at = (
        request.venue_id,
        request.event_request_id,
        request.start_at,
        request.end_at,
    )
    before = datetime.now(UTC)

    async with make_client(staff) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 200
    assert response.json()["status"] == "tentative"
    db.refresh(request)
    assert request.status is BookingStatus.TENTATIVE
    assert (request.venue_id, request.event_request_id) == (venue_id, event_id)
    assert (request.start_at, request.end_at) == (start_at, end_at)
    assert request.expires_at == _EXPIRY
    assert request.held_by_id == staff.id
    assert request.held_at is not None and before <= request.held_at <= datetime.now(UTC)


@pytest.mark.story("SCRUM-110")
async def test_an_approved_hold_blocks_a_buffered_overlap(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-110-02: the approved hold occupies the venue like any SCRUM-83 hold."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    staff = make_user("venue_staff")
    first = _booking(db, coordinator, venue)
    second = _booking(db, coordinator, venue, _START + _HOUR, _END + _HOUR)

    async with make_client(staff) as client:
        assert (await _approve(client, first.id)).status_code == 200
        response = await _approve(client, second.id)

    assert response.status_code == 409
    db.refresh(second)
    assert second.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-110")
async def test_back_to_back_holds_are_allowed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Boundary: the constraint's range is half-open '[)', like intervals_overlap, so a
    hold ending exactly when this one starts does not trip it."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    _booking(db, coordinator, venue, _START - _HOUR, _START, BookingStatus.TENTATIVE)
    request = _booking(db, coordinator, venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 200
    assert _held_count(db) == 2


# ------------------------------------------------------------------ conflict and status


@pytest.mark.story("SCRUM-110")
async def test_approving_over_a_held_overlap_is_a_named_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-110-04: the friendly check refuses the overlap before the constraint fires."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    blocking = _booking(db, coordinator, venue, _START + _HOUR, _END, BookingStatus.TENTATIVE)
    request = _booking(db, coordinator, venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 409
    assert str(blocking.id) in response.json()["detail"]
    db.refresh(request)
    assert request.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-110")
@pytest.mark.parametrize(
    "status", [BookingStatus.TENTATIVE, BookingStatus.CONFIRMED, BookingStatus.REJECTED]
)
async def test_only_a_pending_request_can_be_approved(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: BookingStatus
) -> None:
    """TC-110-03/04: anything already decided is refused, never confirmed."""
    request = _booking(db, make_user("coordinator"), make_venue(db), status=status)

    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 409
    assert response.json()["detail"] == f"cannot move a venue booking from {status} to tentative"


@pytest.mark.story("SCRUM-110")
async def test_approval_requires_an_expiry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-110-01 at the route: no expiry, no hold."""
    request = _booking(db, make_user("coordinator"), make_venue(db))

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(f"/api/venue-bookings/{request.id}/approve", json={})

    assert response.status_code == 422
    db.refresh(request)
    assert request.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-110")
async def test_approval_rejects_an_expiry_after_the_booking_start(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-110-01 at the route: an expiry after the booking start is refused."""
    request = _booking(db, make_user("coordinator"), make_venue(db))

    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, request.id, (_START + _HOUR).isoformat())

    assert response.status_code == 422
    db.refresh(request)
    assert request.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-110")
async def test_approval_never_confirms(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-110-03: approving a pending request holds it, and re-approving a hold is
    refused — nothing on this route can produce a confirmation."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    pending = _booking(db, coordinator, venue)
    held = _booking(db, coordinator, venue, _START + timedelta(days=7), _END + timedelta(days=7))
    db.flush()
    service.hold(db, held.id, make_user("venue_staff").id, _EXPIRY, datetime.now(UTC))

    async with make_client(make_user("venue_staff")) as client:
        pending_response = await _approve(client, pending.id)
        held_response = await _approve(client, held.id)

    assert pending_response.json()["status"] == "tentative"
    assert held_response.status_code == 409
    assert _held_count(db) == 2
    assert db.query(VenueBooking).filter_by(status=BookingStatus.CONFIRMED).count() == 0


@pytest.mark.story("SCRUM-110")
async def test_approving_an_unknown_booking_is_404(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, uuid.uuid4())

    assert response.status_code == 404


@pytest.mark.story("SCRUM-110")
def test_constraint_refuses_an_overlap_the_friendly_check_missed(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-110-04: disable the SCRUM-73 check, as if it had read the venue before the
    other approval committed. The database still refuses, and the repository reports it
    as a domain conflict rather than a raw IntegrityError."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    first = _booking(db, coordinator, venue)
    second = _booking(db, coordinator, venue, _START + _HOUR, _END + _HOUR)
    monkeypatch.setattr(service, "_ensure_no_conflict", lambda db, booking: None)

    service.approve(db, first.id, coordinator.id, datetime.now(UTC), _EXPIRY)
    with pytest.raises(ConcurrentBookingConflictError):
        service.approve(db, second.id, coordinator.id, datetime.now(UTC), _EXPIRY)

    assert _held_count(db) == 1


@pytest.mark.story("SCRUM-110")
def test_a_deadlock_between_two_approvals_is_a_conflict(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two overlapping approvals committing together can deadlock on the exclusion
    constraint. Postgres aborts one, and that one is reported as a conflict, not a 500."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    booking = _booking(db, coordinator, venue)

    def deadlock(db: Session, booking: VenueBooking) -> VenueBooking:
        raise OperationalError("UPDATE venue_bookings", {}, DeadlockDetected("deadlock detected"))

    monkeypatch.setattr(venue_availability, "save_booking", deadlock)

    with pytest.raises(ConcurrentBookingConflictError):
        service.approve(db, booking.id, coordinator.id, datetime.now(UTC), _EXPIRY)


@pytest.mark.story("SCRUM-110")
def test_any_other_database_error_on_approve_is_not_hidden(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, venue = make_user("coordinator"), make_venue(db)
    booking = _booking(db, coordinator, venue)

    def cancelled(db: Session, booking: VenueBooking) -> VenueBooking:
        raise OperationalError("UPDATE venue_bookings", {}, QueryCanceled("canceled"))

    monkeypatch.setattr(venue_availability, "save_booking", cancelled)

    with pytest.raises(OperationalError):
        service.approve(db, booking.id, coordinator.id, datetime.now(UTC), _EXPIRY)


# ------------------------------------------------------------------ AC2: authorisation


@pytest.mark.story("SCRUM-110")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "tech_support", "attendee"])
async def test_non_venue_staff_cannot_approve_a_conflicting_request(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    """TC-110-04: refused with 403 before any conflict logic runs, and no hold is made."""
    coordinator, venue = make_user("coordinator"), make_venue(db)
    _booking(db, coordinator, venue, _START + _HOUR, _END, BookingStatus.TENTATIVE)
    request = _booking(db, coordinator, venue)

    async with make_client(make_user(role)) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 403
    db.refresh(request)
    assert request.status is BookingStatus.PENDING
    assert _held_count(db) == 1


@pytest.mark.story("SCRUM-110")
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
        request_form_venue = session.scalar(select(Venue).where(Venue.name == _VENUE_NAME))
        # SCRUM-122: the winning approval stages a notification row referencing the
        # event, so it must go before the events or their delete is FK-blocked and
        # the venue survives to collide with the next test's `Hall A`.
        session.query(Notification).filter(
            Notification.event_request_id.in_(committed.event_ids)
        ).delete(synchronize_session=False)
        session.flush()
        levels: list[list[object]] = [
            [session.get(VenueBooking, i) for i in committed.booking_ids],
            [session.get(EventRequest, i) for i in committed.event_ids],
            [session.get(Venue, committed.venue_id), request_form_venue],
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


def _race(booking_ids: list[uuid.UUID], decided_by_id: uuid.UUID) -> tuple[list[str], int]:
    """Approve each booking on its own thread and session, released together."""
    start_together = threading.Barrier(len(booking_ids))
    outcomes: list[str] = []

    def approve_once(booking_id: uuid.UUID) -> None:
        session = SessionLocal()
        try:
            start_together.wait()
            service.approve(session, booking_id, decided_by_id, datetime.now(UTC), _EXPIRY)
            outcomes.append("approved")
        except BookingConflictError:
            outcomes.append("conflict")
        except InvalidBookingTransitionError:
            outcomes.append("already decided")
        except InvalidHoldError:
            outcomes.append("invalid expiry")
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
            VenueBooking.id.in_(booking_ids), VenueBooking.status == BookingStatus.TENTATIVE
        )
        held = session.scalar(statement) or 0
    finally:
        session.close()
    return outcomes, held


@pytest.mark.story("SCRUM-110")
@pytest.mark.parametrize("attempt", range(5))
def test_simultaneous_overlapping_approvals_yield_exactly_one_success(attempt: int) -> None:
    """TC-110-04: two venue staff approve two different, overlapping requests at the same
    instant. Each locks only its own booking row, so both may pass the friendly check;
    the exclusion constraint lets exactly one hold commit, and the other is a conflict."""
    del attempt  # the run number only exists to repeat the race
    committed = _committed_requests(2)
    try:
        outcomes, held = _race(committed.booking_ids, committed.user_id)

        assert sorted(outcomes) == ["approved", "conflict"]
        assert held == 1
    finally:
        _delete_committed(committed)


@pytest.mark.story("SCRUM-110")
@pytest.mark.parametrize("attempt", range(3))
def test_simultaneous_approvals_of_the_same_request_yield_exactly_one_success(
    attempt: int,
) -> None:
    """TC-110-04: two staff approve the same request at once. The booking-row lock makes
    the second wait, then see TENTATIVE and be refused, not report a second success."""
    del attempt
    committed = _committed_requests(1)
    try:
        outcomes, held = _race(committed.booking_ids * 2, committed.user_id)

        assert sorted(outcomes) == ["already decided", "approved"]
        assert held == 1
    finally:
        _delete_committed(committed)
