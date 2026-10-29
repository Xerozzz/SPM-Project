"""SCRUM-109 AC10 and the no-commit operation SCRUM-115 and SCRUM-116 will reuse.

Two sessions race for one booking row. Each test fixes the order instead of leaving it to
a barrier: the first session takes the lock and keeps its transaction open, a thread
runs the other action, the test waits until Postgres reports that thread waiting for a
lock, and only then does the first session commit. The rows must be committed for a
second connection to see them, so these tests make and remove their own.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as clock_time

import pytest
from sqlalchemy import text

from core.database import Session, SessionLocal
from core.security import hash_password
from domain import venue_hold
from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus, InvalidBookingTransitionError
from models.event_request import EventRequest
from models.notification import Notification
from models.organisation import Organisation
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from repositories import venue_availability as booking_repo
from services import venue_bookings, venue_hold_expiry
from tests.integration.test_venue_search import effective_for

_START = datetime(2031, 6, 10, 2, 0, tzinfo=UTC)
_END = _START + timedelta(hours=2)
_REASON = "Venue no longer needed"


@dataclass(frozen=True)
class Committed:
    event_id: uuid.UUID
    coordinator_id: uuid.UUID
    staff_id: uuid.UUID
    booking_ids: tuple[uuid.UUID, ...]


def _commit_planning(statuses: tuple[BookingStatus, ...], expires_at: datetime) -> Committed:
    """An Approved event with one committed arrangement per status, each at its own
    venue so no two overlap. Built directly, without catalogue rows, so the clean-up can
    remove everything this made."""
    session = SessionLocal()
    try:
        organisation = Organisation(name=f"Cancel race organisation {uuid.uuid4()}")
        session.add(organisation)
        session.flush()

        def user(role: str) -> User:
            row = User(
                email=f"{uuid.uuid4()}@example.com",
                password_hash=hash_password("password123"),
                roles=[role],
                organisation_id=organisation.id,
            )
            session.add(row)
            session.flush()
            return row

        organiser, coordinator, staff = user("organiser"), user("coordinator"), user("venue_staff")
        event = EventRequest(
            organiser_id=organiser.id,
            name="Cancel race event",
            start_at=_START,
            end_at=_END,
            status=EventStatus.APPROVED,
            coordinator_id=coordinator.id,
        )
        session.add(event)
        session.flush()
        booking_ids = []
        for status in statuses:
            tag = uuid.uuid4().hex[:8]
            hall = Venue(
                name=f"Cancel race hall {tag}",
                location=f"Cancel race {tag}",
                maximum_capacity=200,
                facilities=[],
                supported_layouts=[],
                accessibility_features=[],
                opens_at=clock_time(8, 0),
                closes_at=clock_time(22, 0),
            )
            session.add(hall)
            session.flush()
            effective_start, effective_end = effective_for(hall, _START, _END)
            held = status is BookingStatus.TENTATIVE
            booking = VenueBooking(
                venue_id=hall.id,
                event_request_id=event.id,
                requested_by_id=coordinator.id,
                session_label="Opening keynote",
                start_at=_START,
                end_at=_END,
                effective_start_at=effective_start,
                effective_end_at=effective_end,
                status=status,
                expires_at=expires_at if held else None,
                held_by_id=staff.id if held else None,
                held_at=datetime.now(UTC) if held else None,
                decided_by_id=staff.id if status is BookingStatus.REJECTED else None,
                decided_at=datetime.now(UTC) if status is BookingStatus.REJECTED else None,
            )
            session.add(booking)
            session.flush()
            booking_ids.append(booking.id)
        session.commit()
        return Committed(event.id, coordinator.id, staff.id, tuple(booking_ids))
    finally:
        session.close()


def _remove(committed: Committed) -> None:
    """Everything `_commit_planning` made, plus the notifications the actions staged."""
    session = SessionLocal()
    try:
        event = session.get(EventRequest, committed.event_id)
        assert event is not None
        bookings = session.query(VenueBooking).filter_by(event_request_id=event.id).all()
        venue_ids = {booking.venue_id for booking in bookings}
        user_ids = {event.organiser_id, committed.coordinator_id, committed.staff_id}
        organiser = session.get(User, event.organiser_id)
        assert organiser is not None
        organisation_id = organiser.organisation_id
        session.query(Notification).filter_by(event_request_id=event.id).delete()
        for booking in bookings:
            session.delete(booking)
        session.flush()
        session.delete(event)
        session.flush()
        for venue_id in venue_ids:
            session.delete(session.get(Venue, venue_id))
        for user_id in user_ids:
            session.delete(session.get(User, user_id))
        session.flush()
        session.delete(session.get(Organisation, organisation_id))
        session.commit()
    finally:
        session.close()


@pytest.fixture
def committed_factory() -> Iterator[Callable[..., Committed]]:
    made: list[Committed] = []

    def make(*statuses: BookingStatus, expires_at: datetime | None = None) -> Committed:
        committed = _commit_planning(statuses, expires_at or datetime.now(UTC) + timedelta(days=1))
        made.append(committed)
        return committed

    yield make
    for committed in made:
        _remove(committed)


def _status_of(booking_id: uuid.UUID) -> VenueBooking:
    session = SessionLocal()
    try:
        booking = session.get(VenueBooking, booking_id)
        assert booking is not None
        session.expunge(booking)
        return booking
    finally:
        session.close()


def _wait_until_a_session_waits_for_a_lock(timeout: float = 10.0) -> None:
    """Return once another connection is blocked on a row lock, or fail."""
    deadline = time.monotonic() + timeout
    session = SessionLocal()
    try:
        while time.monotonic() < deadline:
            waiting = session.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                )
            )
            if waiting:
                return
            session.rollback()  # a fresh snapshot for the next poll
            time.sleep(0.02)
        pytest.fail("the competing session never waited for the lock")
    finally:
        session.close()


def _in_thread(action: Callable[[Session], object]) -> tuple[threading.Thread, list[object]]:
    """Run `action` with its own session in a thread; the outcome or the exception."""
    outcome: list[object] = []

    def run() -> None:
        session = SessionLocal()
        try:
            outcome.append(action(session))
        except Exception as exc:  # recorded for the test to assert on
            outcome.append(exc)
        finally:
            session.close()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _finish(thread: threading.Thread) -> None:
    thread.join(timeout=30)
    assert not thread.is_alive()


# ------------------------------------------------------------------ AC10


@pytest.mark.story("SCRUM-109")
def test_when_the_expiry_timer_holds_the_row_the_cancel_is_refused(
    committed_factory: Callable[..., Committed],
) -> None:
    """The timer locks a due hold first; the cancel waits, then reads it as Expired.
    The cancel's own clock is a second earlier, so only the lock can make it refuse."""
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    made = committed_factory(BookingStatus.TENTATIVE, expires_at=expires_at)
    (booking_id,) = made.booking_ids
    timer = SessionLocal()
    try:
        [(booking, _event)] = booking_repo.due_holds_for_update(timer, expires_at)
        booking.status = venue_hold.expire(booking.status, booking.expires_at, expires_at)
        thread, outcome = _in_thread(
            lambda session: venue_bookings.cancel_arrangement(
                session,
                made.event_id,
                booking_id,
                made.coordinator_id,
                _REASON,
                expires_at - timedelta(seconds=1),
            )
        )
        _wait_until_a_session_waits_for_a_lock()
        timer.commit()
        _finish(thread)
    finally:
        timer.close()

    [refused] = outcome
    assert isinstance(refused, InvalidBookingTransitionError)
    assert refused.current is BookingStatus.EXPIRED
    final = _status_of(booking_id)
    assert (final.status, final.cancelled_at, final.cancellation_reason) == (
        BookingStatus.EXPIRED,
        None,
        None,
    )


@pytest.mark.story("SCRUM-109")
def test_when_the_cancel_holds_the_row_the_expiry_timer_skips_it(
    committed_factory: Callable[..., Committed],
) -> None:
    """The cancel locks the hold first; the timer skips the locked row rather than
    waiting, and afterwards finds it Cancelled, so it is never expired too."""
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    made = committed_factory(BookingStatus.TENTATIVE, expires_at=expires_at)
    (booking_id,) = made.booking_ids
    canceller = SessionLocal()
    try:
        venue_bookings.stage_cancellation(
            canceller,
            made.event_id,
            booking_id,
            made.coordinator_id,
            _REASON,
            expires_at - timedelta(seconds=1),
        )
        thread, outcome = _in_thread(
            lambda session: venue_hold_expiry.expire_due_holds(session, expires_at)
        )
        _finish(thread)  # SKIP LOCKED: it does not wait
        canceller.commit()
    finally:
        canceller.close()

    assert outcome == [[]]
    again = SessionLocal()
    try:
        assert venue_hold_expiry.expire_due_holds(again, expires_at) == []
        expired_notices = (
            again.query(Notification).filter_by(event_request_id=made.event_id).count()
        )
    finally:
        again.close()
    final = _status_of(booking_id)
    assert final.status is BookingStatus.CANCELLED
    assert final.expires_at == expires_at  # its hold history is kept (AC2)
    assert expired_notices == 0


@pytest.mark.story("SCRUM-109")
def test_when_the_cancel_holds_the_row_a_venue_staff_approval_is_refused(
    committed_factory: Callable[..., Committed],
) -> None:
    """A pending request being cancelled is never turned into a hold afterwards."""
    made = committed_factory(BookingStatus.PENDING)
    (booking_id,) = made.booking_ids
    now = datetime.now(UTC)
    canceller = SessionLocal()
    try:
        venue_bookings.stage_cancellation(
            canceller, made.event_id, booking_id, made.coordinator_id, _REASON, now
        )
        thread, outcome = _in_thread(
            lambda session: venue_bookings.approve(
                session, booking_id, made.staff_id, now, now + timedelta(days=1)
            )
        )
        _wait_until_a_session_waits_for_a_lock()
        canceller.commit()
        _finish(thread)
    finally:
        canceller.close()

    [refused] = outcome
    assert isinstance(refused, InvalidBookingTransitionError)
    assert refused.current is BookingStatus.CANCELLED
    final = _status_of(booking_id)
    assert (final.status, final.expires_at, final.held_by_id) == (
        BookingStatus.CANCELLED,
        None,
        None,
    )


@pytest.mark.story("SCRUM-109")
def test_when_the_cancel_holds_the_row_an_expiry_update_is_refused(
    committed_factory: Callable[..., Committed],
) -> None:
    """A hold being cancelled cannot be extended afterwards."""
    made = committed_factory(BookingStatus.TENTATIVE)
    (booking_id,) = made.booking_ids
    original = _status_of(booking_id).expires_at
    assert original is not None
    now = datetime.now(UTC)
    canceller = SessionLocal()
    try:
        venue_bookings.stage_cancellation(
            canceller, made.event_id, booking_id, made.coordinator_id, _REASON, now
        )
        thread, outcome = _in_thread(
            lambda session: venue_bookings.update_hold_expiry(
                session, booking_id, original + timedelta(hours=6), now, made.staff_id
            )
        )
        _wait_until_a_session_waits_for_a_lock()
        canceller.commit()
        _finish(thread)
    finally:
        canceller.close()

    [refused] = outcome
    assert isinstance(refused, venue_hold.InactiveHoldError)
    final = _status_of(booking_id)
    assert (final.status, final.expires_at) == (BookingStatus.CANCELLED, original)


# ------------------------------------------------------------------ reuse without committing


@pytest.mark.story("SCRUM-109")
def test_a_staged_cancellation_is_undone_with_the_callers_transaction(
    committed_factory: Callable[..., Committed],
) -> None:
    """`stage_cancellation` commits nothing: rolling the caller back leaves the row."""
    made = committed_factory(BookingStatus.PENDING)
    (booking_id,) = made.booking_ids
    caller = SessionLocal()
    try:
        staged = venue_bookings.stage_cancellation(
            caller, made.event_id, booking_id, made.coordinator_id, _REASON, datetime.now(UTC)
        )
        assert staged.status is BookingStatus.CANCELLED
        assert _status_of(booking_id).status is BookingStatus.PENDING  # not visible yet
        caller.rollback()
    finally:
        caller.close()

    final = _status_of(booking_id)
    assert (final.status, final.cancelled_by_id, final.cancelled_at) == (
        BookingStatus.PENDING,
        None,
        None,
    )


@pytest.mark.story("SCRUM-109")
def test_several_cancellations_commit_together_or_not_at_all(
    committed_factory: Callable[..., Committed],
) -> None:
    """What SCRUM-115 needs: stage several and commit once; one refusal, then a
    rollback, undoes the ones staged before it."""
    made = committed_factory(BookingStatus.PENDING, BookingStatus.TENTATIVE, BookingStatus.REJECTED)
    pending, hold, rejected = made.booking_ids
    now = datetime.now(UTC)

    caller = SessionLocal()
    try:
        venue_bookings.stage_cancellation(
            caller, made.event_id, pending, made.coordinator_id, _REASON, now
        )
        with pytest.raises(InvalidBookingTransitionError):
            venue_bookings.stage_cancellation(
                caller, made.event_id, rejected, made.coordinator_id, _REASON, now
            )
        caller.rollback()
    finally:
        caller.close()
    assert _status_of(pending).status is BookingStatus.PENDING

    caller = SessionLocal()
    try:
        for booking_id in (pending, hold):
            venue_bookings.stage_cancellation(
                caller, made.event_id, booking_id, made.coordinator_id, _REASON, now
            )
        caller.commit()
    finally:
        caller.close()
    assert [_status_of(b).status for b in (pending, hold, rejected)] == [
        BookingStatus.CANCELLED,
        BookingStatus.CANCELLED,
        BookingStatus.REJECTED,
    ]
